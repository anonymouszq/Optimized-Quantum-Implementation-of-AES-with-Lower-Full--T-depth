"""Semantics-preserving circuit cleanup passes."""

from __future__ import annotations

from .circuit import Circuit, Signal


def cleanup(c: Circuit) -> Circuit:
    """Remove dead gates and merge structurally identical XOR/AND/NOT gates."""
    needed = {s.idx for s in c.outputs if s.idx >= c.n_inputs}
    changed = True
    while changed:
        changed = False
        for node in list(needed):
            g = c.gates[node - c.n_inputs]
            for s in (g.a, g.b):
                if s is not None and s.idx >= c.n_inputs and s.idx not in needed:
                    needed.add(s.idx)
                    changed = True

    out = Circuit(c.n_inputs)
    remap: dict[int, Signal] = {i: Signal(i) for i in range(c.n_inputs)}
    memo: dict[tuple, Signal] = {}

    def mp(s: Signal) -> Signal:
        base = remap[s.idx]
        return Signal(base.idx, base.inv ^ s.inv)

    def canon_signal(s: Signal) -> tuple[int, bool]:
        return (s.idx, s.inv)

    for node in c.topo_nodes():
        if node not in needed:
            continue
        g = c.gates[node - c.n_inputs]
        a = mp(g.a)
        if g.op == "NOT":
            # Keep NOT as an inverted edge; no gate is needed.
            remap[node] = Signal(a.idx, not a.inv)
            continue
        assert g.b is not None
        b = mp(g.b)
        if g.op == "XOR":
            if a.idx == b.idx:
                # a xor a = 0, a xor ~a = 1. Constants are represented as x0^x0
                # plus an inverted edge if needed.
                zero = _const_zero(out, memo)
                remap[node] = Signal(zero.idx, a.inv ^ b.inv)
                continue
            key_inputs = sorted([canon_signal(a), canon_signal(b)])
            key = ("XOR", tuple(key_inputs))
        elif g.op in {"AND", "OR"}:
            key_inputs = sorted([canon_signal(a), canon_signal(b)])
            key = (g.op, tuple(key_inputs))
        else:
            raise ValueError(g.op)
        if key in memo:
            remap[node] = memo[key]
        else:
            ia, ib = key_inputs
            sig = out.add(g.op, Signal(*ia), Signal(*ib))
            memo[key] = sig
            remap[node] = sig

    out.set_outputs([mp(s) for s in c.outputs])
    return out


def materialize_inversions(c: Circuit) -> Circuit:
    """Convert inverted edges to explicit NOT gates for bitslice gate accounting."""
    out = Circuit(c.n_inputs)
    remap: dict[int, Signal] = {i: Signal(i) for i in range(c.n_inputs)}
    not_cache: dict[tuple[int, bool], Signal] = {}

    def mat(s: Signal) -> Signal:
        base = remap[s.idx]
        inv = base.inv ^ s.inv
        plain = Signal(base.idx)
        if not inv:
            return plain
        key = (plain.idx, True)
        if key not in not_cache:
            not_cache[key] = out.add("NOT", plain)
        return not_cache[key]

    for node in c.topo_nodes():
        g = c.gates[node - c.n_inputs]
        if g.op == "NOT":
            remap[node] = out.add("NOT", mat(g.a))
        elif g.op in {"XOR", "AND", "OR"}:
            assert g.b is not None
            remap[node] = out.add(g.op, mat(g.a), mat(g.b))
        else:
            raise ValueError(g.op)
    out.set_outputs([mat(s) for s in c.outputs])
    return out


def balance_xor(c: Circuit, fanout_limit: int = 1, max_terms: int | None = None) -> Circuit:
    """Reassociate single-fanout XOR trees into depth-balanced XOR trees."""
    fan = c.fanouts()
    out = Circuit(c.n_inputs)
    remap: dict[int, Signal] = {i: Signal(i) for i in range(c.n_inputs)}
    expr: dict[int, tuple[list[Signal], bool]] = {}

    def mapped(s: Signal) -> Signal:
        base = remap[s.idx]
        return Signal(base.idx, base.inv ^ s.inv)

    def terms_for(s: Signal) -> tuple[list[Signal], bool]:
        if (
            not s.inv
            and s.idx >= c.n_inputs
            and c.gates[s.idx - c.n_inputs].op == "XOR"
            and len(fan.get(s.idx, [])) <= fanout_limit
            and s.idx in expr
            and (max_terms is None or len(expr[s.idx][0]) <= max_terms)
        ):
            return expr[s.idx]
        ms = mapped(s)
        return [Signal(ms.idx)], ms.inv

    def normalize(terms: list[Signal], const: bool) -> tuple[list[Signal], bool]:
        parity: dict[int, int] = {}
        for s in terms:
            parity[s.idx] = parity.get(s.idx, 0) ^ 1
            const ^= s.inv
        return [Signal(i) for i, p in parity.items() if p], const

    def sig_depths() -> list[int]:
        depths = [0] * out.n_inputs
        for g in out.gates:
            da = depths[g.a.idx]
            if g.op == "NOT":
                depths.append(da + 1)
            else:
                assert g.b is not None
                depths.append(max(da, depths[g.b.idx]) + 1)
        return depths

    def build_balanced(terms: list[Signal], const: bool) -> Signal:
        if not terms:
            z = out.add("XOR", Signal(0), Signal(0))
            return Signal(z.idx, const)
        ds = sig_depths()
        if const:
            best = min(range(len(terms)), key=lambda i: ds[terms[i].idx])
            terms = list(terms)
            old = terms[best]
            terms[best] = out.add("NOT", old)
            const = False
            ds.append(ds[old.idx] + 1)
        work = sorted(terms, key=lambda s: ds[s.idx])
        while len(work) > 1:
            a = work.pop(0)
            b = work.pop(0)
            x = out.add("XOR", a, b)
            ds.append(max(ds[a.idx], ds[b.idx]) + 1)
            insert = 0
            while insert < len(work) and ds[work[insert].idx] <= ds[x.idx]:
                insert += 1
            work.insert(insert, x)
        return Signal(work[0].idx, work[0].inv ^ const)

    for node in c.topo_nodes():
        g = c.gates[node - c.n_inputs]
        if g.op == "XOR":
            assert g.b is not None
            ta, ca = terms_for(g.a)
            tb, cb = terms_for(g.b)
            terms, const = normalize(ta + tb, ca ^ cb)
            sig = build_balanced(terms, const)
            remap[node] = sig
            expr[node] = (terms, const)
        elif g.op == "NOT":
            if (
                not g.a.inv
                and g.a.idx >= c.n_inputs
                and c.gates[g.a.idx - c.n_inputs].op == "XOR"
                and len(fan.get(g.a.idx, [])) <= fanout_limit
                and g.a.idx in expr
                and (max_terms is None or len(expr[g.a.idx][0]) <= max_terms)
            ):
                terms, const = expr[g.a.idx]
                remap[node] = build_balanced(list(terms), not const)
            else:
                remap[node] = out.add("NOT", mapped(g.a))
        else:
            assert g.b is not None
            remap[node] = out.add(g.op, mapped(g.a), mapped(g.b))

    out.set_outputs([mapped(s) for s in c.outputs])
    return out


def _const_zero(c: Circuit, memo: dict[tuple, Signal]) -> Signal:
    key = ("ZERO",)
    if key not in memo:
        memo[key] = c.add("XOR", Signal(0), Signal(0))
    return memo[key]
