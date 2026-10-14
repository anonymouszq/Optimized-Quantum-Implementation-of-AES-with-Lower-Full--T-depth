"""Boolean circuit representation over XOR/AND/NOT."""

from dataclasses import dataclass
from collections import defaultdict, deque


@dataclass(frozen=True)
class Signal:
    idx: int
    inv: bool = False


@dataclass
class Gate:
    op: str
    a: Signal
    b: Signal | None = None


class Circuit:
    def __init__(self, n_inputs: int):
        self.n_inputs = n_inputs
        self.gates: list[Gate] = []
        self.outputs: list[Signal] = []

    def add(self, op: str, a: Signal, b: Signal | None = None) -> Signal:
        self.gates.append(Gate(op, a, b))
        return Signal(self.n_inputs + len(self.gates) - 1)

    def set_outputs(self, outputs: list[Signal]) -> None:
        self.outputs = outputs

    def eval(self, x: int) -> int:
        vals = [(x >> i) & 1 for i in range(self.n_inputs)]
        for g in self.gates:
            av = vals[g.a.idx] ^ int(g.a.inv)
            if g.op == "NOT":
                vals.append(av ^ 1)
            else:
                assert g.b is not None
                bv = vals[g.b.idx] ^ int(g.b.inv)
                if g.op == "XOR":
                    vals.append(av ^ bv)
                elif g.op == "AND":
                    vals.append(av & bv)
                elif g.op == "OR":
                    vals.append(av | bv)
                else:
                    raise ValueError(f"unknown gate {g.op}")
        y = 0
        for i, s in enumerate(self.outputs):
            y |= (vals[s.idx] ^ int(s.inv)) << i
        return y

    def metrics(self) -> dict[str, int]:
        depths = [0] * self.n_inputs
        and_depths = [0] * self.n_inputs
        counts = {"XOR": 0, "AND": 0, "OR": 0, "NOT": 0}
        for g in self.gates:
            counts[g.op] += 1
            da = depths[g.a.idx]
            ada = and_depths[g.a.idx]
            if g.op == "NOT":
                depths.append(da + 1)
                and_depths.append(ada)
            else:
                assert g.b is not None
                db = depths[g.b.idx]
                adb = and_depths[g.b.idx]
                depths.append(max(da, db) + 1)
                and_depths.append(max(ada, adb) + (1 if g.op in {"AND", "OR"} else 0))
        out_depth = max((depths[s.idx] for s in self.outputs), default=0)
        out_and_depth = max((and_depths[s.idx] for s in self.outputs), default=0)
        return {
            "gates": len(self.gates),
            "xor": counts["XOR"],
            "and": counts["AND"],
            "or": counts["OR"],
            "not": counts["NOT"],
            "depth": out_depth,
            "and_depth": out_and_depth,
        }

    def verify(self, lut: list[int]) -> bool:
        return all(self.eval(x) == y for x, y in enumerate(lut))

    def values_for_all_inputs(self) -> list[list[int]]:
        rows = 1 << self.n_inputs
        vals = [[(x >> i) & 1 for i in range(self.n_inputs)] for x in range(rows)]
        for x in range(rows):
            for g in self.gates:
                av = vals[x][g.a.idx] ^ int(g.a.inv)
                if g.op == "NOT":
                    vals[x].append(av ^ 1)
                else:
                    assert g.b is not None
                    bv = vals[x][g.b.idx] ^ int(g.b.inv)
                    if g.op == "XOR":
                        vals[x].append(av ^ bv)
                    elif g.op == "AND":
                        vals[x].append(av & bv)
                    elif g.op == "OR":
                        vals[x].append(av | bv)
                    else:
                        raise ValueError(f"unknown gate {g.op}")
        return vals

    def fanouts(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = defaultdict(list)
        for gi, g in enumerate(self.gates):
            node = self.n_inputs + gi
            out[g.a.idx].append(node)
            if g.b is not None:
                out[g.b.idx].append(node)
        for oi, s in enumerate(self.outputs):
            out[s.idx].append(-(oi + 1))
        return out

    def deps(self, node: int) -> set[int]:
        if node < self.n_inputs:
            return {node}
        g = self.gates[node - self.n_inputs]
        d = set(self.deps(g.a.idx))
        if g.b is not None:
            d |= self.deps(g.b.idx)
        return d

    def topo_nodes(self) -> list[int]:
        return list(range(self.n_inputs, self.n_inputs + len(self.gates)))

    def to_verilog(self, module: str = "sbox") -> str:
        lines = [
            f"module {module}(input [{self.n_inputs - 1}:0] x, output [{len(self.outputs) - 1}:0] y);"
        ]
        for i, g in enumerate(self.gates):
            name = f"n{i}"
            a = _sig_verilog(g.a, self.n_inputs)
            if g.op == "NOT":
                expr = f"~{a}"
            else:
                assert g.b is not None
                b = _sig_verilog(g.b, self.n_inputs)
                op = "^" if g.op == "XOR" else ("&" if g.op == "AND" else "|")
                expr = f"{a} {op} {b}"
            lines.append(f"  wire {name} = {expr};")
        for i, s in enumerate(self.outputs):
            lines.append(f"  assign y[{i}] = {_sig_verilog(s, self.n_inputs)};")
        lines.append("endmodule")
        return "\n".join(lines) + "\n"


def _sig_verilog(s: Signal, n_inputs: int) -> str:
    base = f"x[{s.idx}]" if s.idx < n_inputs else f"n{s.idx - n_inputs}"
    return f"~{base}" if s.inv else base
