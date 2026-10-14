"""Generic S-box synthesis heuristics.

The first research prototype deliberately avoids assuming algebraic structure such as
field inversion. It starts from ANF and shares nonlinear monomials globally.
"""

from __future__ import annotations

from collections import Counter
from .anf import infer_n, infer_m, sbox_anf
from .circuit import Circuit, Signal
from .optimize import cleanup


def _mask_depth(mask: int) -> int:
    return max(0, mask.bit_count() - 1)


def _build_monomial(
    c: Circuit,
    mask: int,
    cache: dict[int, Signal],
    depth_first: bool,
    input_polarity: int = 0,
) -> Signal:
    if mask in cache:
        return cache[mask]
    bits = [i for i in range(c.n_inputs) if (mask >> i) & 1]
    if not bits:
        raise ValueError("constant monomial has no signal")
    if len(bits) == 1:
        sig = Signal(bits[0], bool((input_polarity >> bits[0]) & 1))
    else:
        if depth_first:
            # Balanced tree: lower AND-depth, often at a small total-gate cost penalty.
            sub = [1 << b for b in bits]
            while len(sub) > 1:
                nxt = []
                for i in range(0, len(sub), 2):
                    if i + 1 == len(sub):
                        nxt.append(sub[i])
                    else:
                        a = _build_monomial(c, sub[i], cache, depth_first, input_polarity)
                        b = _build_monomial(c, sub[i + 1], cache, depth_first, input_polarity)
                        comb = sub[i] | sub[i + 1]
                        cache[comb] = c.add("AND", a, b)
                        nxt.append(comb)
                sub = nxt
            sig = cache[mask]
        else:
            # Chain using cached prefixes: fewer gates when many related monomials share.
            acc = 1 << bits[0]
            sig = cache[acc]
            for b in bits[1:]:
                acc2 = acc | (1 << b)
                if acc2 not in cache:
                    cache[acc2] = c.add("AND", sig, Signal(b, bool((input_polarity >> b) & 1)))
                sig = cache[acc2]
                acc = acc2
    cache[mask] = sig
    return sig


def _repolarize_lut(lut: list[int], polarity: int) -> list[int]:
    if polarity == 0:
        return lut
    return [lut[x ^ polarity] for x in range(len(lut))]


def synthesize_anf_shared(lut: list[int], depth_first: bool = False, polarity: int = 0) -> Circuit:
    n = infer_n(lut)
    m = infer_m(lut)
    anfs = sbox_anf(_repolarize_lut(lut, polarity), m)
    c = Circuit(n)
    monomial_cache = {1 << i: Signal(i, bool((polarity >> i) & 1)) for i in range(n)}

    monomial_use = Counter(mask for anf in anfs for mask in anf if mask != 0 and mask.bit_count() > 1)
    ordered = sorted(monomial_use, key=lambda z: (_mask_depth(z), -monomial_use[z], z))
    if depth_first:
        ordered = sorted(monomial_use, key=lambda z: (z.bit_count(), z))
    for mask in ordered:
        _build_monomial(c, mask, monomial_cache, depth_first, polarity)

    outputs = []
    for anf in anfs:
        terms: list[Signal] = []
        const = 0 in anf
        for mask in anf:
            if mask == 0:
                continue
            if mask.bit_count() == 1:
                bit = mask.bit_length() - 1
                terms.append(Signal(bit, bool((polarity >> bit) & 1)))
            else:
                terms.append(monomial_cache[mask])
        if not terms:
            outputs.append(Signal(0, bool(const)))
            continue
        # Pair terms by current structural depth proxy to reduce XOR depth.
        while len(terms) > 1:
            nxt = []
            for i in range(0, len(terms), 2):
                if i + 1 == len(terms):
                    nxt.append(terms[i])
                else:
                    nxt.append(c.add("XOR", terms[i], terms[i + 1]))
            terms = nxt
        outputs.append(Signal(terms[0].idx, terms[0].inv ^ bool(const)))
    c.set_outputs(outputs)
    return c


def synthesize_best_polarity(lut: list[int], depth_first: bool = False) -> tuple[int, Circuit]:
    n = infer_n(lut)
    best_p = 0
    best = synthesize_anf_shared(lut, depth_first=depth_first, polarity=0)
    for p in range(1, 1 << n):
        cand = synthesize_anf_shared(lut, depth_first=depth_first, polarity=p)
        cm = cand.metrics()
        bm = best.metrics()
        key = (cm["and_depth"], cm["and"], cm["gates"], cm["depth"]) if depth_first else (
            cm["gates"],
            cm["and"],
            cm["depth"],
            cm["and_depth"],
        )
        bkey = (bm["and_depth"], bm["and"], bm["gates"], bm["depth"]) if depth_first else (
            bm["gates"],
            bm["and"],
            bm["depth"],
            bm["and_depth"],
        )
        if key < bkey:
            best_p = p
            best = cand
    return best_p, best


def _linear_xor(c: Circuit, terms: list[Signal], const: bool, zero: Signal | None = None) -> Signal:
    if not terms:
        if zero is None:
            zero = c.add("XOR", Signal(0), Signal(0))
        return Signal(zero.idx, const)
    while len(terms) > 1:
        nxt = []
        for i in range(0, len(terms), 2):
            if i + 1 == len(terms):
                nxt.append(terms[i])
            else:
                nxt.append(c.add("XOR", terms[i], terms[i + 1]))
        terms = nxt
    return Signal(terms[0].idx, terms[0].inv ^ const)


def synthesize_factored(lut: list[int]) -> Circuit:
    """Synthesize by cached recursive ANF factorization.

    This is intentionally generic: it receives only the LUT-derived ANF. The recursive
    step P = R xor x_i * Q tries to share Q across all output coordinates.
    """
    n = infer_n(lut)
    m = infer_m(lut)
    anfs = [frozenset(anf) for anf in sbox_anf(lut, m)]
    c = Circuit(n)
    cache: dict[frozenset[int], Signal] = {}
    zero: Signal | None = None

    def const_signal(value: bool) -> Signal:
        nonlocal zero
        if zero is None:
            zero = c.add("XOR", Signal(0), Signal(0))
        return Signal(zero.idx, value)

    def cost_score(poly: frozenset[int], var: int) -> tuple[int, int, int]:
        bit = 1 << var
        q = frozenset(mask ^ bit for mask in poly if mask & bit)
        r = frozenset(mask for mask in poly if not (mask & bit))
        nonlinear_q = sum(1 for mask in q if mask.bit_count() > 1)
        nonlinear_r = sum(1 for mask in r if mask.bit_count() > 1)
        shared = sum(1 for other in anfs if q and q.issubset(other | {0}))
        return (len(q) + shared * 2, -nonlinear_q, -nonlinear_r)

    def emit(poly: frozenset[int]) -> Signal:
        if poly in cache:
            return cache[poly]
        if not poly:
            sig = const_signal(False)
            cache[poly] = sig
            return sig
        const = 0 in poly
        nonconst = [mask for mask in poly if mask != 0]
        if all(mask.bit_count() <= 1 for mask in nonconst):
            terms = [Signal(mask.bit_length() - 1) for mask in nonconst]
            sig = _linear_xor(c, terms, const, zero)
            cache[poly] = sig
            return sig

        vars_present = [i for i in range(n) if any(mask & (1 << i) for mask in nonconst if mask.bit_count() > 1)]
        var = max(vars_present, key=lambda i: cost_score(poly, i))
        bit = 1 << var
        q = frozenset(mask ^ bit for mask in poly if mask & bit)
        r = frozenset(mask for mask in poly if not (mask & bit))
        if q == frozenset({0}):
            prod = Signal(var)
        elif not q:
            prod = const_signal(False)
        else:
            qsig = emit(q)
            prod = c.add("AND", Signal(var), qsig)
        if r:
            rsig = emit(r)
            sig = c.add("XOR", prod, rsig)
        else:
            sig = prod
        cache[poly] = sig
        return sig

    c.set_outputs([emit(poly) for poly in anfs])
    return c


def synthesize(lut: list[int], mode: str = "pareto") -> list[tuple[str, Circuit]]:
    candidates = [
        ("anf-shared-area", cleanup(synthesize_anf_shared(lut, depth_first=False))),
        ("anf-shared-depth", cleanup(synthesize_anf_shared(lut, depth_first=True))),
        ("recursive-factor", cleanup(synthesize_factored(lut))),
    ]
    p_area, c_area = synthesize_best_polarity(lut, depth_first=False)
    p_depth, c_depth = synthesize_best_polarity(lut, depth_first=True)
    candidates.extend(
        [
            (f"polarity-area-p{p_area:02x}", cleanup(c_area)),
            (f"polarity-depth-p{p_depth:02x}", cleanup(c_depth)),
        ]
    )
    if mode != "pareto":
        return [c for c in candidates if c[0] == mode]
    frontier: list[tuple[str, Circuit]] = []
    for name, circ in candidates:
        met = circ.metrics()
        dominated = False
        for _, other in candidates:
            om = other.metrics()
            if om == met:
                continue
            if all(om[k] <= met[k] for k in ("gates", "depth", "and", "and_depth")) and any(
                om[k] < met[k] for k in ("gates", "depth", "and", "and_depth")
            ):
                dominated = True
                break
        if not dominated:
            frontier.append((name, circ))
    return frontier
