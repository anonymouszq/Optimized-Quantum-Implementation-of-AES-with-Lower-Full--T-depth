"""Heuristic XOR straight-line synthesis for linear target masks."""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter


@dataclass
class XorProgram:
    basis: int
    targets: list[int]
    steps: list[tuple[int, int, int]]
    output_exprs: list[frozenset[int]]

    @property
    def xor_count(self) -> int:
        return len(self.steps) + sum(max(0, len(e) - 1) for e in self.output_exprs)


def paar_synthesize(n_basis: int, targets: list[int]) -> XorProgram:
    exprs = [frozenset(i for i in range(n_basis) if (t >> i) & 1) for t in targets]
    steps: list[tuple[int, int, int]] = []
    next_id = n_basis

    while True:
        pairs: Counter[tuple[int, int]] = Counter()
        for e in exprs:
            xs = sorted(e)
            for i in range(len(xs)):
                for j in range(i + 1, len(xs)):
                    pairs[(xs[i], xs[j])] += 1
        if not pairs:
            break
        pair, freq = max(pairs.items(), key=lambda kv: (kv[1], -kv[0][0], -kv[0][1]))
        if freq < 2:
            break
        a, b = pair
        new_exprs = []
        changed = False
        for e in exprs:
            if a in e and b in e:
                ne = set(e)
                ne.remove(a)
                ne.remove(b)
                ne.add(next_id)
                new_exprs.append(frozenset(ne))
                changed = True
            else:
                new_exprs.append(e)
        if not changed:
            break
        steps.append((next_id, a, b))
        exprs = new_exprs
        next_id += 1
    return XorProgram(n_basis, targets, steps, exprs)

