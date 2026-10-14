"""Exact, ancilla-free resynthesis of invertible binary CNOT networks.

These routines preserve the full linear map on arbitrary input states, rather
than only the promised zero-ancilla subspace of the surrounding AES circuit.
"""
from __future__ import annotations

import random
import itertools
from collections import deque
from functools import lru_cache

from qsboxopt.quantum_schedule import Op


def matrix(gates: list[tuple[int, int]], n: int) -> tuple[int, ...]:
    rows = [1 << i for i in range(n)]
    for a, b in gates:
        rows[b] ^= rows[a]
    return tuple(rows)


def depth(gates: list[tuple[int, int]], n: int) -> int:
    times = [0] * n
    for a, b in gates:
        times[a] = times[b] = max(times[a], times[b]) + 1
    return max(times, default=0)


def cancel(gates: list[tuple[int, int]]) -> list[tuple[int, int]]:
    gates = list(gates)
    for i in range(len(gates) - 1, -1, -1):
        if gates[i] is None:
            continue
        a, b = gates[i]
        for j in range(i + 1, len(gates)):
            if gates[j] is None:
                continue
            c, d = gates[j]
            if (a, b) == (c, d):
                gates[i] = gates[j] = None
                break
            if a == d or c == b:
                break
    return [g for g in gates if g is not None]


def gaussian(rows: tuple[int, ...], order: list[int], rng: random.Random) -> list[tuple[int, int]]:
    rows = list(rows)
    elimination = []
    for position, p in enumerate(order):
        if not (rows[p] >> p) & 1:
            choices = [i for i in order[position + 1:] if (rows[i] >> p) & 1]
            # Prefer a sparse result; perturb ties without changing semantics.
            q = min(choices, key=lambda i: ((rows[p] ^ rows[i]).bit_count(), rng.random()))
            rows[p] ^= rows[q]
            elimination.append((q, p))
        for q in order:
            if q != p and (rows[q] >> p) & 1:
                rows[q] ^= rows[p]
                elimination.append((p, q))
    assert rows == [1 << i for i in range(len(rows))]
    return cancel(elimination[::-1])


def greedy_reduce(rows: tuple[int, ...], seed: int, mixed: bool = True) -> list[tuple[int, int]]:
    """Reduce matrix weight by row/column additions, then Gaussian eliminate."""
    rng = random.Random(seed)
    n = len(rows)
    original = rows
    rows = list(rows)
    left, right = [], []
    while True:
        choices = []
        best = 0
        for a in range(n):
            for b in range(n):
                if a == b:
                    continue
                saving = rows[b].bit_count() - (rows[a] ^ rows[b]).bit_count()
                if saving > best:
                    choices, best = [], saving
                if saving and saving == best:
                    choices.append(('row', a, b))
        if mixed:
            columns = [sum(((rows[j] >> i) & 1) << j for j in range(n)) for i in range(n)]
            for a in range(n):
                for b in range(n):
                    if a == b:
                        continue
                    saving = columns[b].bit_count() - (columns[a] ^ columns[b]).bit_count()
                    if saving > best:
                        choices, best = [], saving
                    if saving and saving == best:
                        choices.append(('column', a, b))
        if not choices:
            break
        kind, a, b = rng.choice(choices)
        if kind == 'row':
            rows[b] ^= rows[a]
            left.append((a, b))
        else:
            for i in range(n):
                if (rows[i] >> a) & 1:
                    rows[i] ^= 1 << b
            right.append((b, a))
    order = list(range(n))
    rng.shuffle(order)
    middle = gaussian(tuple(rows), order, rng)
    result = cancel(right + middle + left[::-1])
    assert matrix(result, n) == original
    return result


def cnot_windows(ops: list[Op], minimum: int = 5):
    start = None
    for i in range(len(ops) + 1):
        op = ops[i] if i < len(ops) else None
        eligible = op is not None and op.kind == 'cx' and op.condition is None
        if eligible and start is None:
            start = i
        if not eligible and start is not None:
            if i - start >= minimum:
                yield start, i
            start = None


def localize(ops: list[Op]):
    wires = sorted({q for op in ops for q in op.wires})
    index = {q: i for i, q in enumerate(wires)}
    gates = [(index[op.wires[0]], index[op.wires[1]]) for op in ops]
    return wires, gates


def candidates(ops: list[Op], trials: int = 128):
    wires, original = localize(ops)
    n = len(wires)
    target = matrix(original, n)
    unique = {tuple(original): {'method': 'original'}}
    inverse = matrix(original[::-1], n)
    for seed in range(trials):
        rng = random.Random(seed)
        order = list(range(n))
        if seed:
            rng.shuffle(order)
        for invert in [False, True]:
            result = gaussian(inverse if invert else target, order, rng)
            if invert:
                result.reverse()
            unique.setdefault(tuple(result), {'method': 'gaussian', 'seed': seed, 'inverse': invert})
        if seed < min(trials, 32):
            for mixed in [False, True]:
                result = greedy_reduce(target, seed, mixed)
                unique.setdefault(tuple(result), {'method': 'greedy', 'seed': seed, 'mixed': mixed})
    result = []
    for gates, method in unique.items():
        assert matrix(gates, n) == target
        result.append(dict(gates=list(gates), depth=depth(gates, n), count=len(gates), **method))
    result.sort(key=lambda r: (r['depth'], r['count']))
    return wires, result


@lru_cache(maxsize=2)
def exact_small(n: int = 4):
    """Shortest CNOT-count circuits for every invertible n-bit linear map."""
    identity = tuple(1 << i for i in range(n))
    circuits = {identity: ()}
    queue = deque([identity])
    generators = list(itertools.permutations(range(n), 2))
    while queue:
        rows = queue.popleft()
        for a, b in generators:
            nxt = list(rows)
            nxt[b] ^= nxt[a]
            nxt = tuple(nxt)
            if nxt not in circuits:
                circuits[nxt] = circuits[rows] + ((a, b),)
                queue.append(nxt)
    assert len(circuits) == {3: 168, 4: 20160}[n]
    return circuits


def peephole(gates: list[tuple[int, int]], n: int, seed: int = 0,
             passes: int = 10, allow_equal: bool = False):
    """Extract <=4-wire blocks across disjoint spectators and replace exactly.

    A gate touching both selected and outside wires is a boundary. Moving the
    extracted block to its first position thus only crosses disjoint gates.
    """
    rng = random.Random(seed)
    original = matrix(gates, n)
    trace = []
    gates = list(gates)
    for iteration in range(passes):
        edges = {frozenset(g) for g in gates}
        wire_sets = {a | b for a in edges for b in edges if 3 <= len(a | b) <= 4}
        wire_sets = sorted(wire_sets, key=lambda s: tuple(sorted(s)))
        rng.shuffle(wire_sets)
        changed = False
        for selected in wire_sets:
            wires = sorted(selected)
            index = {q: i for i, q in enumerate(wires)}
            exact = exact_small(len(wires))
            blocks, block = [], []
            for i, gate in enumerate(gates):
                support = set(gate)
                if support <= selected:
                    block.append(i)
                elif support & selected:
                    if len(block) >= 3:
                        blocks.append(block)
                    block = []
            if len(block) >= 3:
                blocks.append(block)
            for positions in reversed(blocks):
                small = [(index[gates[i][0]], index[gates[i][1]]) for i in positions]
                best = exact[matrix(small, len(wires))]
                if len(best) > len(small):
                    continue
                if len(best) == len(small):
                    if not allow_equal or depth(best, len(wires)) >= depth(small, len(wires)):
                        continue
                replacement = [(wires[a], wires[b]) for a, b in best]
                removed = set(positions)
                new = []
                for i, gate in enumerate(gates):
                    if i == positions[0]:
                        new.extend(replacement)
                    if i not in removed:
                        new.append(gate)
                assert matrix(new, n) == original
                trace.append(dict(iteration=iteration, wires=wires,
                                  removed=len(small), inserted=len(best)))
                gates = new
                changed = True
        if not changed:
            break
    assert matrix(gates, n) == original
    return gates, trace


def circuit_peephole(ops: list[Op], seed: int, passes: int = 2):
    """Exact CNOT substitutions across quantum-disjoint intervening gates."""
    rng = random.Random(seed)
    ops = list(ops)
    trace = []
    for iteration in range(passes):
        eligible = [(i, frozenset(op.wires)) for i, op in enumerate(ops)
                    if op.kind == 'cx' and op.condition is None]
        wire_sets = set()
        for j, (p, a) in enumerate(eligible):
            for q, b in eligible[j + 1:]:
                if q - p > 80:
                    break
                selected = a | b
                if 3 <= len(selected) <= 4:
                    wire_sets.add(selected)
        wire_sets = sorted(wire_sets, key=lambda s: tuple(sorted(s)))
        rng.shuffle(wire_sets)
        changed = False
        for selected in wire_sets:
            wires = sorted(selected)
            rng.shuffle(wires)
            index = {q: i for i, q in enumerate(wires)}
            selected_mask = sum(1 << q for q in wires)
            exact = exact_small(len(wires))
            blocks, block = [], []
            for i, op in enumerate(ops):
                mask = sum(1 << q for q in op.wires)
                if mask & selected_mask == 0:
                    continue
                if mask & selected_mask == mask and op.kind == 'cx' and op.condition is None:
                    block.append(i)
                else:
                    if len(block) >= 3:
                        blocks.append(block)
                    block = []
            if len(block) >= 3:
                blocks.append(block)
            for positions in reversed(blocks):
                small = [(index[ops[i].wires[0]], index[ops[i].wires[1]]) for i in positions]
                target = matrix(small, len(wires))
                invert = rng.randrange(2)
                best = exact[matrix(small[::-1], len(wires))][::-1] if invert else exact[target]
                if len(best) >= len(small):
                    continue
                assert matrix(best, len(wires)) == target
                replacement = [Op('cx', (wires[a], wires[b])) for a, b in best]
                insertion = positions[-1] if rng.randrange(2) else positions[0]
                removed = set(positions)
                new = []
                for i, op in enumerate(ops):
                    if i == insertion:
                        new.extend(replacement)
                    if i not in removed:
                        new.append(op)
                trace.append(dict(iteration=iteration, wires=wires, positions=positions,
                                  insertion=insertion, replacement=[list(o.wires) for o in replacement]))
                ops = new
                changed = True
        if not changed:
            break
    return ops, trace


def verify_substitutions(ops: list[Op], trace: list[dict]):
    """Replay a certificate with exact GF(2) equality on arbitrary states."""
    ops = list(ops)
    removed_count = 0
    for item in trace:
        positions, wires = item['positions'], item['wires']
        selected = set(wires)
        index = {q: i for i, q in enumerate(wires)}
        assert positions == sorted(set(positions))
        assert item['insertion'] in (positions[0], positions[-1])
        old = []
        for i in positions:
            op = ops[i]
            assert op.kind == 'cx' and op.condition is None and set(op.wires) <= selected
            old.append(tuple(index[q] for q in op.wires))
        removed = set(positions)
        for i in range(positions[0], positions[-1] + 1):
            if i not in removed:
                assert not selected.intersection(ops[i].wires)
        replacement = [Op('cx', tuple(qs)) for qs in item['replacement']]
        new_local = [tuple(index[q] for q in op.wires) for op in replacement]
        assert matrix(old, len(wires)) == matrix(new_local, len(wires))
        new = []
        for i, op in enumerate(ops):
            if i == item['insertion']:
                new.extend(replacement)
            if i not in removed:
                new.append(op)
        removed_count += len(positions) - len(replacement)
        ops = new
    return ops, dict(substitutions=len(trace), removed_cnot=removed_count,
                     exact_full_linear_maps=True, intervening_gates_disjoint=True)
