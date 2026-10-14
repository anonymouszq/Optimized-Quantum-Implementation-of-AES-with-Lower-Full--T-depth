"""Probe exact symmetric QAND orientations; retain T-depth three."""
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qsboxopt.quantum_schedule import *
from verify_aes_t3_quantum import macro_parse, qand, unand


def orient(ops, bits):
    result = []
    i = 0
    k = 0
    while i < len(ops):
        op = ops[i]
        if op.kind in {'cx', 'x'} and op.condition is None:
            result.append(op)
            i += 1
        elif op.kind == 'h' and ops[i + 1].kind == 'cx':
            c = op.wires[0]
            b, d = ops[i + 1].wires
            cc, a = ops[i + 2].wires
            assert cc == c and ops[i:i + 15] == qand(a, b, c, d)
            if bits[k]:
                a, b = b, a
            result.extend(qand(a, b, c, d))
            i += 15
            k += 1
        elif op.kind == 'h' and ops[i + 1].kind == 'h':
            b = op.wires[0]
            c = ops[i + 1].wires[0]
            mm = ops[i + 2]
            a = mm.wires[1]
            assert ops[i:i + 6] == unand(a, b, c, mm.measurement)
            if bits[k]:
                a, b = b, a
            result.extend(unand(a, b, c, mm.measurement))
            i += 6
            k += 1
        else:
            raise AssertionError((i, op))
    assert k == len(bits)
    return result


def main():
    typ = sys.argv[1] if len(sys.argv) > 1 else 'C0'
    p = ROOT/f'external/Minimal_T-depth_Width/Resource_Estimator/CliffordT_quantum_circuit/AES_T3_{typ}_CliffordT.qasm'
    w, ops = read_author_qasm(p.read_text())
    kinds = [k for k, _ in macro_parse(ops) if k in {'and', 'unand'}]
    rng = random.Random(20260904)
    best = 1000
    start = time.time()
    for candidate in range(64):
        if candidate == 0:
            bits = [0] * len(kinds)
        elif candidate == 1:
            bits = [1] * len(kinds)
        elif candidate == 2:
            bits = [int(k == 'unand') for k in kinds]
        elif candidate == 3:
            bits = [int(k == 'and') for k in kinds]
        else:
            bits = [rng.randrange(2) for _ in kinds]
        new = orient(ops, bits)
        assert metrics(new, w)['t_depth'] == 3
        model = SchedulingProblem(new, w)
        for seed in range(48):
            layers = model.schedule(seed, [0, .5, 1.5, 3, 5, 8][seed % 6], bool((seed // 6) % 2))
            if len(layers) < best:
                best = len(layers)
                print(typ, 'candidate', candidate, 'schedule_seed', seed, 'depth', best, 'seconds', round(time.time()-start, 1), flush=True)
                (ROOT/f'results/aes_t3_round2/gadget_probe_{typ}.json').write_text(json.dumps(dict(bits=bits, layers=layers, candidate=candidate, schedule_seed=seed)))
    print('done', typ, best, flush=True)


if __name__ == '__main__':
    main()
