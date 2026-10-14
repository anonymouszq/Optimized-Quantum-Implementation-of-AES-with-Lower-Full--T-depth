"""Exact commuting-gate scheduling for the EC2025 AES resource circuits.

The upstream QASM files encode the all-measurements-one resource path: the
two corrections after each measurement are printed without classical guards.
We recover those guards and keep the measurement's three-wire dependency.
No gate deletion, gate substitution, or ancilla allocation is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
import random
import re


@dataclass(frozen=True)
class Op:
    kind: str
    wires: tuple[int, ...]
    condition: int | None = None
    measurement: int | None = None


def read_author_qasm(text: str) -> tuple[int, list[Op]]:
    width = int(re.search(r'qreg q\[(\d+)\]', text)[1])
    lines = [s.strip() for s in text.splitlines() if s.strip() and not s.strip().startswith('//')]
    ops = []
    i = 0
    while i < len(lines):
        s = lines[i]
        if s.startswith(('OPENQASM', 'include', 'qreg', 'creg')):
            i += 1
            continue
        if s.startswith('measure'):
            m = int(re.search(r'c\[(\d+)\]', s)[1])
            measured = int(re.search(r'q\[(\d+)\]', s)[1])
            assert lines[i + 1].startswith('barrier ')
            wires = tuple(map(int, re.findall(r'q\[(\d+)\]', lines[i + 1])))
            assert len(wires) == 3 and wires[0] == measured
            ops.append(Op('mm', wires, measurement=m))
            # Upstream QAND-dagger: H(b), H(c), measure(c), CX(a,b), X(c), H(b).
            cx = tuple(map(int, re.findall(r'q\[(\d+)\]', lines[i + 2])))
            xx = tuple(map(int, re.findall(r'q\[(\d+)\]', lines[i + 3])))
            assert lines[i + 2].startswith('cx ') and cx == wires[1:]
            assert lines[i + 3].startswith('x ') and xx == wires[:1]
            ops.extend([Op('cx', cx, condition=m), Op('x', xx, condition=m)])
            i += 4
            continue
        kind = s.split()[0]
        assert kind in {'cx', 'h', 's', 'sdg', 't', 'tdg', 'x', 'y', 'z'}, s
        ops.append(Op(kind, tuple(map(int, re.findall(r'q\[(\d+)\]', s)))))
        i += 1
    return width, ops


def commutes(a: Op, b: Op) -> bool:
    # Conservatively retain all feed-forward edges, even for disjoint wires.
    if a.measurement is not None and b.condition == a.measurement:
        return False
    if b.measurement is not None and a.condition == b.measurement:
        return False
    if not set(a.wires).intersection(b.wires):
        return True
    if a.kind == 'mm' or b.kind == 'mm':
        return False
    if a.kind == 'cx' and b.kind == 'cx':
        return a.wires[0] != b.wires[1] and b.wires[0] != a.wires[1]
    diag = {'s', 'sdg', 't', 'tdg', 'z'}
    if a.kind == 'cx' or b.kind == 'cx':
        cx, one = (a, b) if a.kind == 'cx' else (b, a)
        return ((one.wires[0] == cx.wires[0] and one.kind in diag)
                or (one.wires[0] == cx.wires[1] and one.kind == 'x'))
    return a.kind == b.kind or (a.kind in diag and b.kind in diag)


def metrics(ops: list[Op], width: int) -> dict:
    df, dt = [0] * width, [0] * width
    classical = {}
    for op in ops:
        f = max(df[q] for q in op.wires)
        if op.condition is not None:
            f = max(f, classical[op.condition])
        f += 1
        t = max(dt[q] for q in op.wires) + (op.kind in {'t', 'tdg'})
        for q in op.wires:
            df[q], dt[q] = f, t
        if op.measurement is not None:
            classical[op.measurement] = f
    c = Counter(op.kind for op in ops)
    return dict(width=width, full_depth=max(df), t_depth=max(dt),
                t_count=c['t'] + c['tdg'], cnot=c['cx'], measurements=c['mm'],
                one_qubit_clifford=sum(c[k] for k in ['x', 'y', 'z', 'h', 's', 'sdg']),
                gate_count=len(ops))


class SchedulingProblem:
    def __init__(self, ops: list[Op], width: int):
        self.ops, self.width = ops, width
        tlevels = [0] * width
        batches = {}
        self.groups = []
        group_of = []
        for i, op in enumerate(ops):
            t = max(tlevels[q] for q in op.wires) + (op.kind in {'t', 'tdg'})
            for q in op.wires:
                tlevels[q] = t
            if op.kind in {'t', 'tdg'}:
                if t not in batches:
                    batches[t] = len(self.groups)
                    self.groups.append([])
                g = batches[t]
                self.groups[g].append(i)
            else:
                g = len(self.groups)
                self.groups.append([i])
            group_of.append(g)
        self.tgroups = set(batches.values())
        self.support = [sum(1 << q for q in {q for i in g for q in ops[i].wires}) for g in self.groups]
        self.succ = [set() for _ in self.groups]
        self.pred = [set() for _ in self.groups]
        for j, b in enumerate(ops):
            for i in range(j):
                if not commutes(ops[i], b):
                    gi, gj = group_of[i], group_of[j]
                    assert gi != gj
                    self.succ[gi].add(gj)
                    self.pred[gj].add(gi)
        indeg = [len(p) for p in self.pred]
        ready = [i for i, k in enumerate(indeg) if not k]
        topo = []
        while ready:
            i = ready.pop()
            topo.append(i)
            for j in self.succ[i]:
                indeg[j] -= 1
                if not indeg[j]:
                    ready.append(j)
        assert len(topo) == len(self.groups), 'T-batching created a dependency cycle'
        self.height = [1] * len(self.groups)
        for i in reversed(topo):
            self.height[i] = 1 + max((self.height[j] for j in self.succ[i]), default=0)
        self.reverse_height = [1] * len(self.groups)
        for i in topo:
            self.reverse_height[i] = 1 + max((self.reverse_height[j] for j in self.pred[i]), default=0)

    def schedule(self, seed: int, jitter: float = 0.0, reverse: bool = False) -> list[list[int]]:
        rng = random.Random(seed)
        pred, succ = (self.succ, self.pred) if reverse else (self.pred, self.succ)
        height = self.reverse_height if reverse else self.height
        indeg = [len(p) for p in pred]
        ready = {i for i, k in enumerate(indeg) if not k}
        layers = []
        while ready:
            ordered = sorted(ready, key=lambda i: (
                height[i] + jitter * rng.random(), len(succ[i]), -i), reverse=True)
            selected, used = [], 0
            for i in ordered:
                if not used & self.support[i]:
                    selected.append(i)
                    used |= self.support[i]
            layer = []
            for i in selected:
                layer.extend(self.groups[i])
                ready.remove(i)
            for i in selected:
                for j in succ[i]:
                    indeg[j] -= 1
                    if not indeg[j]:
                        ready.add(j)
            layers.append(layer)
        return layers[::-1] if reverse else layers


def verify_reordering(ops: list[Op], layers: list[list[int]]) -> dict:
    order = [i for layer in layers for i in layer]
    assert sorted(order) == list(range(len(ops)))
    pos = {i: p for p, i in enumerate(order)}
    swaps = 0
    for j in range(len(ops)):
        for i in range(j):
            if pos[i] > pos[j]:
                assert commutes(ops[i], ops[j]), (i, j)
                swaps += 1
    measurements = {}
    t_layers = []
    for t, layer in enumerate(layers):
        used = set()
        for i in layer:
            op = ops[i]
            assert not used.intersection(op.wires)
            used.update(op.wires)
            if op.condition is not None:
                assert measurements[op.condition] < t
            if op.measurement is not None:
                measurements[op.measurement] = t
        if any(ops[i].kind in {'t', 'tdg'} for i in layer):
            t_layers.append(t + 1)
    assert len(t_layers) == 3
    return dict(permutation=True, inverted_pairs_checked=swaps,
                all_inverted_pairs_commute_exactly=True,
                wire_exclusivity=True, feed_forward_order=True, t_layer_positions=t_layers)


def write_qasm(ops: list[Op], width: int, layers: list[list[int]], conditional: bool) -> str:
    ms = [op.measurement for op in ops if op.measurement is not None]
    rows = ['OPENQASM 2.0;', 'include "qelib1.inc";', f'qreg q[{width}];']
    if conditional:
        rows += [f'creg m{i}[1];' for i in ms]
    else:
        rows += [f'creg c[{len(ms)}];', '// RESOURCE TRACE ONLY: corrections shown for outcome 1.']
    for k, layer in enumerate(layers):
        rows += ['', f'// Layer {k + 1}']
        for idx in layer:
            op = ops[idx]
            wires = ','.join(f'q[{q}]' for q in op.wires)
            if op.kind == 'mm':
                creg = f'm{op.measurement}[0]' if conditional else f'c[{op.measurement}]'
                rows.extend([f'measure q[{op.wires[0]}]->{creg};', f'barrier {wires};'])
            else:
                prefix = f'if(m{op.condition}==1) ' if conditional and op.condition is not None else ''
                rows.append(f'{prefix}{op.kind} {wires};')
    return '\n'.join(rows) + '\n'
