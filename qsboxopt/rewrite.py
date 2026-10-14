"""Local cone selection and exact rewrite using the CaDiCaL oracle."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .circuit import Circuit, Gate, Signal
from .exact_smt import synthesize_truths_exact
from .local_oracle import call_layered_oracle, call_local_oracle


@dataclass
class Cone:
    roots: list[int]
    gates: set[int]
    boundary: list[int]
    truths: list[int]
    depth: int


@dataclass
class Replacement:
    old_gates: int
    new_gates: int
    old_depth: int
    new_depth: int
    cone: Cone
    gates: list[Gate]
    outputs: list[Signal]


def _gate_inputs(c: Circuit, node: int) -> list[int]:
    g = c.gates[node - c.n_inputs]
    xs = [g.a.idx]
    if g.b is not None:
        xs.append(g.b.idx)
    return xs


def _has_external_fanout(fanouts: dict[int, list[int]], node: int, allowed: set[int], root: int) -> bool:
    for fo in fanouts.get(node, []):
        if fo < 0:
            return node != root
        if fo not in allowed:
            return True
    return False


def extract_cone(c: Circuit, root: int, max_inputs: int = 6, max_gates: int = 12) -> Cone | None:
    fan = c.fanouts()
    cone: set[int] = {root}
    changed = True
    while changed:
        changed = False
        for node in sorted(list(cone)):
            for pred in _gate_inputs(c, node):
                if pred < c.n_inputs or pred in cone:
                    continue
                trial = set(cone)
                trial.add(pred)
                if _has_external_fanout(fan, pred, trial, root):
                    continue
                boundary = _boundary(c, trial)
                if len(boundary) <= max_inputs and len(trial) <= max_gates:
                    cone = trial
                    changed = True
    boundary = _boundary(c, cone)
    if len(boundary) > max_inputs or len(cone) <= 1:
        return None
    if not _safe_cone(c, cone, [root]):
        return None
    if not _valid_insertion(c, cone):
        return None
    return Cone(roots=[root], gates=cone, boundary=boundary, truths=[_cone_truth(c, root, boundary)], depth=_cone_depth(c, cone, [root]))


def extract_shared_cone(
    c: Circuit,
    shared: int,
    max_inputs: int = 6,
    max_gates: int = 14,
    max_outputs: int = 4,
) -> Cone | None:
    fan = c.fanouts()
    roots = sorted([x for x in fan.get(shared, []) if x >= c.n_inputs])[:max_outputs]
    if len(roots) < 2:
        return None
    cone: set[int] = set(roots) | {shared}
    changed = True
    while changed:
        changed = False
        for node in sorted(list(cone)):
            for pred in _gate_inputs(c, node):
                if pred < c.n_inputs or pred in cone:
                    continue
                trial = set(cone)
                trial.add(pred)
                if any(_has_external_fanout(fan, g, trial, g if g in roots else -1) for g in trial if g not in roots):
                    continue
                boundary = _boundary(c, trial)
                if len(boundary) <= max_inputs and len(trial) <= max_gates:
                    cone = trial
                    changed = True
    boundary = _boundary(c, cone)
    if len(boundary) > max_inputs or len(cone) <= len(roots):
        return None
    if not _safe_cone(c, cone, roots):
        return None
    if not _valid_insertion(c, cone):
        return None
    truths = [_cone_truth(c, root, boundary) for root in roots]
    return Cone(roots=roots, gates=cone, boundary=boundary, truths=truths, depth=_cone_depth(c, cone, roots))


def extract_cut_window(
    c: Circuit,
    seed: int,
    max_inputs: int = 6,
    max_gates: int = 16,
    max_outputs: int = 5,
) -> Cone | None:
    selected: set[int] = {seed}

    def valid(sel: set[int]) -> bool:
        if len(sel) > max_gates:
            return False
        if len(_boundary(c, sel)) > max_inputs:
            return False
        if len(_roots(c, sel)) > max_outputs:
            return False
        return _valid_insertion(c, sel)

    changed = True
    while changed:
        changed = False
        candidates: set[int] = set()
        for node in selected:
            for pred in _gate_inputs(c, node):
                if pred >= c.n_inputs and pred not in selected:
                    candidates.add(pred)
            for fo in c.fanouts().get(node, []):
                if fo >= c.n_inputs and fo not in selected:
                    candidates.add(fo)
        best = None
        best_key = None
        for cand in candidates:
            trial = set(selected)
            trial.add(cand)
            if not valid(trial):
                continue
            roots = _roots(c, trial)
            boundary = _boundary(c, trial)
            key = (len(trial) - len(boundary) - len(roots), len(trial), -len(boundary), -len(roots))
            if best_key is None or key > best_key:
                best = cand
                best_key = key
        if best is not None and best_key is not None and best_key[0] >= 0:
            selected.add(best)
            changed = True

    roots = _roots(c, selected)
    boundary = _boundary(c, selected)
    if len(selected) <= len(roots) or len(boundary) > max_inputs or len(roots) > max_outputs:
        return None
    if not _valid_insertion(c, selected):
        return None
    return Cone(
        roots=roots,
        gates=selected,
        boundary=boundary,
        truths=[_cone_truth(c, root, boundary) for root in roots],
        depth=_cone_depth(c, selected, roots),
    )


def _safe_cone(c: Circuit, cone: set[int], roots: list[int]) -> bool:
    fan = c.fanouts()
    root_set = set(roots)
    for node in cone:
        for fo in fan.get(node, []):
            if fo < 0:
                if node not in root_set:
                    return False
            elif fo not in cone and node not in root_set:
                return False
    return True


def _roots(c: Circuit, cone: set[int]) -> list[int]:
    fan = c.fanouts()
    roots = []
    for node in sorted(cone):
        for fo in fan.get(node, []):
            if fo < 0 or fo not in cone:
                roots.append(node)
                break
    return roots


def _insertion_point(c: Circuit, cone: set[int]) -> int:
    boundary = _boundary(c, cone)
    return max(boundary, default=c.n_inputs - 1) + 1


def _valid_insertion(c: Circuit, cone: set[int]) -> bool:
    ip = _insertion_point(c, cone)
    roots = set(_roots(c, cone))
    fan = c.fanouts()
    for root in roots:
        for fo in fan.get(root, []):
            if fo >= 0 and fo not in cone and fo < ip:
                return False
    return True


def _boundary(c: Circuit, cone: set[int]) -> list[int]:
    b = set()
    for node in cone:
        for pred in _gate_inputs(c, node):
            if pred not in cone:
                b.add(pred)
    return sorted(b)


def _cone_truth(c: Circuit, root: int, boundary: list[int]) -> int:
    vals = c.values_for_all_inputs()
    truth = 0
    seen: dict[int, int] = {}
    for row in vals:
        bx = 0
        for i, node in enumerate(boundary):
            bx |= row[node] << i
        rv = row[root]
        if bx in seen and seen[bx] != rv:
            raise ValueError("boundary does not determine cone output")
        seen[bx] = rv
    for bx, rv in seen.items():
        truth |= rv << bx
    return truth


def _cone_depth(c: Circuit, cone: set[int], roots: list[int]) -> int:
    depth: dict[int, int] = {}
    for node in sorted(cone):
        g = c.gates[node - c.n_inputs]
        da = depth.get(g.a.idx, 0) if g.a.idx in cone else 0
        if g.op == "NOT":
            depth[node] = da + 1
        else:
            assert g.b is not None
            db = depth.get(g.b.idx, 0) if g.b.idx in cone else 0
            depth[node] = max(da, db) + 1
    return max(depth[root] for root in roots)


def candidate_cones(c: Circuit, max_inputs: int = 6, max_gates: int = 12) -> list[Cone]:
    cones: list[Cone] = []
    seen: set[tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]] = set()

    def add_cone(cone: Cone | None) -> None:
        if cone is None:
            return
        key = (tuple(cone.roots), tuple(cone.boundary), tuple(sorted(cone.gates)))
        if key not in seen:
            cones.append(cone)
            seen.add(key)

    for root in c.topo_nodes():
        add_cone(extract_cone(c, root, max_inputs=max_inputs, max_gates=max_gates))
    for shared in c.topo_nodes():
        add_cone(extract_shared_cone(c, shared, max_inputs=max_inputs, max_gates=max_gates))
    for seed in c.topo_nodes():
        add_cone(extract_cut_window(c, seed, max_inputs=max_inputs, max_gates=max_gates))
    cones.sort(
        key=lambda x: (
            -x.depth,
            -(len(x.gates) - len(x.boundary)),
            -len(x.roots),
            -len(x.gates),
            len(x.boundary),
            x.roots[0],
        )
    )
    return cones


_GATE_RE = re.compile(r"t(\d+) = (xor|and|or|not)\((x|t)(\d+)(?:, (x|t)(\d+))?\)")
_OUT_RE = re.compile(r"y(\d+) = (?:(not) )?(x|t)(\d+)")


def parse_oracle(stdout: str, n_inputs: int) -> tuple[list[Gate], list[Signal]]:
    gates: list[Gate] = []
    outs: dict[int, Signal] = {}
    for line in stdout.splitlines():
        m = _GATE_RE.fullmatch(line.strip())
        if m:
            op = m.group(2).upper()
            a = _parse_src(m.group(3), int(m.group(4)), n_inputs)
            if op == "NOT":
                gates.append(Gate(op, a, None))
            else:
                b = _parse_src(m.group(5), int(m.group(6)), n_inputs)
                gates.append(Gate(op, a, b))
            continue
        m = _OUT_RE.fullmatch(line.strip())
        if m:
            oi = int(m.group(1))
            out = _parse_src(m.group(3), int(m.group(4)), n_inputs)
            if m.group(2):
                out = Signal(out.idx, not out.inv)
            outs[oi] = out
    return gates, [outs[i] for i in sorted(outs)]


def _parse_src(kind: str, idx: int, n_inputs: int) -> Signal:
    if kind == "x":
        return Signal(idx)
    return Signal(n_inputs + idx)


def find_replacement(
    cone: Cone,
    conflicts: int = 200000,
    allow_same_size: bool = False,
    timeout: float = 5.0,
    max_drop: int | None = None,
    backend: str = "cadical",
    objective: str = "area",
    extra_gates: int = 0,
    max_new_depth: int | None = None,
) -> Replacement | None:
    old = len(cone.gates)
    n = len(cone.boundary)
    old_depth = cone.depth
    if max_new_depth is None and objective == "depth":
        max_new_depth = max(0, old_depth - 1)
    if objective == "depth":
        start = old + max(0, extra_gates)
    else:
        start = old if allow_same_size else old - 1
    stop = 0 if max_drop is None else max(0, old - max_drop)
    budgets = [max(0, start)] if objective == "depth" else list(range(max(0, start), stop - 1, -1))
    for budget in budgets:
        if backend == "z3":
            ec = synthesize_truths_exact(
                n,
                cone.truths,
                budget,
                timeout_ms=int(timeout * 1000),
                max_depth=max_new_depth,
            )
            if ec is not None:
                gates = [
                    Gate(op, Signal(a), None if b is None else Signal(b))
                    for op, a, b in ec.gates
                ]
                outs = [Signal(o) for o in ec.outputs]
                new_depth = ec.metrics()["depth"]
                return Replacement(
                    old_gates=old,
                    new_gates=budget,
                    old_depth=old_depth,
                    new_depth=new_depth,
                    cone=cone,
                    gates=gates,
                    outputs=outs,
                )
            continue
        if backend == "cadical-layered":
            if max_new_depth is None or max_new_depth <= 0:
                continue
            partitions = _layer_partitions(budget, max_new_depth)
            per_timeout = max(0.5, timeout / max(1, len(partitions)))
            for layers in partitions:
                res = call_layered_oracle(n, cone.truths, layers, conflicts=conflicts, timeout=per_timeout)
                if res.status == "SAT":
                    gates, outs = parse_oracle(res.stdout, n)
                    return Replacement(
                        old_gates=old,
                        new_gates=budget,
                        old_depth=old_depth,
                        new_depth=max_new_depth,
                        cone=cone,
                        gates=gates,
                        outputs=outs,
                    )
            continue
        if max_new_depth is not None:
            continue
        res = call_local_oracle(n, cone.truths, budget, conflicts=conflicts, timeout=timeout)
        if res.status == "SAT":
            gates, outs = parse_oracle(res.stdout, n)
            return Replacement(
                old_gates=old,
                new_gates=budget,
                old_depth=old_depth,
                new_depth=-1,
                cone=cone,
                gates=gates,
                outputs=outs,
            )
        if res.status in {"UNKNOWN", "TIMEOUT"}:
            # Try a slightly larger but still improving budget before giving up.
            continue
    return None


def _layer_partitions(total: int, layers: int) -> list[list[int]]:
    if layers == 1:
        return [[total]]
    out: list[list[int]] = []

    def rec(rem: int, k: int, prefix: list[int]) -> None:
        if k == 1:
            out.append(prefix + [rem])
            return
        for x in range(rem + 1):
            rec(rem - x, k - 1, prefix + [x])

    rec(total, layers, [])
    # Useful low-depth circuits often have a wide first layer and narrow last layer.
    out = [xs for xs in out if xs[0] > 0 and xs[-1] > 0]
    out.sort(key=lambda xs: (xs[-1], -xs[0], max(xs) - min(xs), tuple(xs)))
    front = out[:10]
    balanced = sorted(out, key=lambda xs: (max(xs) - min(xs), abs(xs[0] - xs[-1]), tuple(xs)))[:5]
    back_loaded = sorted(out, key=lambda xs: (xs[0], -xs[-1], max(xs) - min(xs), tuple(xs)))[:5]
    picked: list[list[int]] = []
    seen = set()
    for xs in front + balanced + back_loaded:
        key = tuple(xs)
        if key not in seen:
            picked.append(xs)
            seen.add(key)
    return picked[:6]


def apply_replacement(c: Circuit, repl: Replacement) -> Circuit:
    cone = repl.cone
    old_to_new: dict[int, Signal] = {i: Signal(i) for i in range(c.n_inputs)}
    newc = Circuit(c.n_inputs)
    replacement_outputs: dict[int, Signal] = {}
    inserted = False
    insert_at = _insertion_point(c, cone.gates)

    def mapped(s: Signal) -> Signal:
        base = old_to_new[s.idx]
        return Signal(base.idx, base.inv ^ s.inv)

    def insert_replacement() -> None:
        nonlocal inserted
        if inserted:
            return
        local_map: dict[int, Signal] = {
            i: mapped(Signal(boundary_node)) for i, boundary_node in enumerate(cone.boundary)
        }
        local_n = len(cone.boundary)
        for gi, g in enumerate(repl.gates):
            a = local_map[g.a.idx]
            if g.op == "NOT":
                sig = newc.add("NOT", Signal(a.idx, a.inv))
            else:
                assert g.b is not None
                b = local_map[g.b.idx]
                sig = newc.add(g.op, Signal(a.idx, a.inv), Signal(b.idx, b.inv))
            local_map[local_n + gi] = sig
        for root, local_out in zip(cone.roots, repl.outputs):
            out = local_map[local_out.idx]
            replacement_outputs[root] = Signal(out.idx, out.inv ^ local_out.inv)
            old_to_new[root] = replacement_outputs[root]
        inserted = True

    for node in c.topo_nodes():
        if not inserted and node >= insert_at:
            insert_replacement()
        if node in cone.gates:
            if node in cone.roots and node in replacement_outputs:
                old_to_new[node] = replacement_outputs[node]
            continue
        g = c.gates[node - c.n_inputs]
        if g.op == "NOT":
            sig = newc.add("NOT", mapped(g.a))
        else:
            assert g.b is not None
            sig = newc.add(g.op, mapped(g.a), mapped(g.b))
        old_to_new[node] = sig

    if not inserted:
        insert_replacement()
    assert len(replacement_outputs) == len(cone.roots)
    newc.set_outputs([mapped(s) for s in c.outputs])
    return newc
