"""Exact small-S-box synthesis with Z3 bit-vector semantics.

This is a research backend for 4/5-bit S-boxes. It follows the bitslice gate
model used by Stoffelen: gates are selected from XOR/AND/OR/NOT and NOT counts
as a gate. Outputs are selected from inputs/gate outputs without free inversion.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import z3
except ModuleNotFoundError:  # pragma: no cover - exercised only without z3 installed.
    z3 = None


OPS = ("XOR", "AND", "OR", "NOT")
LAST_STATUS = "not-run"


@dataclass
class ExactCircuit:
    n: int
    m: int
    gates: list[tuple[str, int, int | None]]
    outputs: list[int]

    def metrics(self) -> dict[str, int]:
        counts = {op: 0 for op in OPS}
        depth = [0] * self.n
        and_depth = [0] * self.n
        for op, a, b in self.gates:
            counts[op] += 1
            if op == "NOT":
                depth.append(depth[a] + 1)
                and_depth.append(and_depth[a])
            else:
                assert b is not None
                depth.append(max(depth[a], depth[b]) + 1)
                and_depth.append(max(and_depth[a], and_depth[b]) + (1 if op in {"AND", "OR"} else 0))
        return {
            "gates": len(self.gates),
            "xor": counts["XOR"],
            "and": counts["AND"],
            "or": counts["OR"],
            "not": counts["NOT"],
            "depth": max(depth[o] for o in self.outputs),
            "and_depth": max(and_depth[o] for o in self.outputs),
        }

    def eval(self, x: int) -> int:
        vals = [(x >> i) & 1 for i in range(self.n)]
        for op, a, b in self.gates:
            if op == "XOR":
                vals.append(vals[a] ^ vals[b])
            elif op == "AND":
                vals.append(vals[a] & vals[b])
            elif op == "OR":
                vals.append(vals[a] | vals[b])
            elif op == "NOT":
                vals.append(vals[a] ^ 1)
        y = 0
        for i, src in enumerate(self.outputs):
            y |= vals[src] << i
        return y

    def verify(self, lut: list[int]) -> bool:
        return all(self.eval(x) == y for x, y in enumerate(lut))


def synthesize_exact(
    lut: list[int],
    gates: int,
    timeout_ms: int = 60000,
    max_depth: int | None = None,
    op_counts: dict[str, int] | None = None,
) -> ExactCircuit | None:
    if z3 is None:
        raise RuntimeError("z3 is required for the exact SMT backend")
    global LAST_STATUS
    LAST_STATUS = "running"
    n = (len(lut) - 1).bit_length()
    m = max(1, max(lut).bit_length())
    rows = 1 << n
    mask = (1 << rows) - 1
    width = rows
    input_tt = []
    for i in range(n):
        v = 0
        for x in range(rows):
            v |= ((x >> i) & 1) << x
        input_tt.append(z3.BitVecVal(v, width))
    output_tt = []
    for bit in range(m):
        v = 0
        for x, y in enumerate(lut):
            v |= ((y >> bit) & 1) << x
        output_tt.append(z3.BitVecVal(v, width))

    s = z3.Solver()
    s.set("timeout", timeout_ms)

    op = [z3.Int(f"op_{i}") for i in range(gates)]
    a = [z3.Int(f"a_{i}") for i in range(gates)]
    b = [z3.Int(f"b_{i}") for i in range(gates)]
    vals: list[z3.BitVecRef] = list(input_tt)

    def src_expr(idx: z3.IntNumRef | z3.ArithRef, sources: list[z3.BitVecRef]) -> z3.BitVecRef:
        expr = sources[0]
        for j in range(1, len(sources)):
            expr = z3.If(idx == j, sources[j], expr)
        return expr

    depths: list[z3.ArithRef] = [z3.IntVal(0) for _ in range(n)]
    for i in range(gates):
        sources = vals[: n + i]
        s.add(op[i] >= 0, op[i] <= 3)
        s.add(a[i] >= 0, a[i] < n + i)
        s.add(b[i] >= 0, b[i] < n + i)
        # Symmetry break for commutative binary gates; NOT ignores b.
        s.add(z3.Implies(op[i] != 3, a[i] < b[i]))
        av = src_expr(a[i], sources)
        bv = src_expr(b[i], sources)
        val = z3.If(
            op[i] == 0,
            av ^ bv,
            z3.If(op[i] == 1, av & bv, z3.If(op[i] == 2, av | bv, ~av & z3.BitVecVal(mask, width))),
        )
        vals.append(val)
        da = src_expr_int(a[i], depths)
        db = src_expr_int(b[i], depths)
        depths.append(z3.If(op[i] == 3, da + 1, z3.If(da >= db, da, db) + 1))

    if op_counts:
        for name, count in op_counts.items():
            s.add(z3.Sum([z3.If(op[i] == OPS.index(name), 1, 0) for i in range(gates)]) == count)

    outs = [z3.Int(f"out_{j}") for j in range(m)]
    for j in range(m):
        s.add(outs[j] >= 0, outs[j] < n + gates)
        s.add(src_expr(outs[j], vals) == output_tt[j])
        if max_depth is not None:
            s.add(src_expr_int(outs[j], depths) <= max_depth)

    res = s.check()
    LAST_STATUS = str(res)
    if res != z3.sat:
        return None
    model = s.model()
    rec_gates: list[tuple[str, int, int | None]] = []
    for i in range(gates):
        oi = model.eval(op[i]).as_long()
        ai = model.eval(a[i]).as_long()
        bi = model.eval(b[i]).as_long()
        rec_gates.append((OPS[oi], ai, None if OPS[oi] == "NOT" else bi))
    rec_out = [model.eval(o).as_long() for o in outs]
    circ = ExactCircuit(n, m, rec_gates, rec_out)
    assert circ.verify(lut)
    return circ


def synthesize_truths_exact(
    n: int,
    output_truths: list[int],
    gates: int,
    timeout_ms: int = 10000,
    max_depth: int | None = None,
    op_counts: dict[str, int] | None = None,
) -> ExactCircuit | None:
    lut = []
    for x in range(1 << n):
        y = 0
        for bit, tt in enumerate(output_truths):
            y |= ((tt >> x) & 1) << bit
        lut.append(y)
    return synthesize_exact(lut, gates, timeout_ms=timeout_ms, max_depth=max_depth, op_counts=op_counts)


def src_expr_int(idx: z3.ArithRef, sources: list[z3.ArithRef]) -> z3.ArithRef:
    expr = sources[0]
    for j in range(1, len(sources)):
        expr = z3.If(idx == j, sources[j], expr)
    return expr
