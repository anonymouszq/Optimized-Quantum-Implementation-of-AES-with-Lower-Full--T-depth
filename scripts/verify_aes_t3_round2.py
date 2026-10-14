"""Replay round-two certificates and verify the exported dynamic QASM."""
import json
from pathlib import Path
import re
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qsboxopt.quantum_schedule import Op, read_author_qasm, verify_reordering, metrics
from qsboxopt.cnot_resynthesis import verify_substitutions
from aes_t3_gadget_probe import orient
from verify_aes_t3_quantum import qand, unand, step, local_checks, macro_parse, exhaustive_macro_check


def orientation_identity_checks():
    error = 0.0
    for col in range(16):
        init = np.eye(16, dtype=complex)[:, col]
        for kind, outcomes in [('and', [None]), ('unand', [0, 1])]:
            for outcome in outcomes:
                pair = []
                for a, b in [(0, 1), (1, 0)]:
                    gates = qand(a, b, 2, 3) if kind == 'and' else unand(a, b, 2, 0)
                    v = init.copy()
                    for op in gates:
                        v = step(v, op, outcome)
                    pair.append(v)
                error = max(error, float(np.max(np.abs(pair[0] - pair[1]))))
    assert error < 1e-12
    return dict(qand_and_cleanup_control_swap_error=error, basis_vectors=16,
                cleanup_outcomes=[0, 1], full_gadget_maps_compared=True)


def read_dynamic(path):
    rows = [s.strip() for s in path.read_text().splitlines() if s.strip() and not s.strip().startswith('//')]
    ops = []
    i = 0
    while i < len(rows):
        row = rows[i]
        if row.startswith(('OPENQASM', 'include', 'qreg', 'creg')):
            i += 1
            continue
        if row.startswith('measure '):
            measured, m = map(int, re.fullmatch(r'measure q\[(\d+)\]->m(\d+)\[0\];', row).groups())
            assert rows[i + 1].startswith('barrier ')
            wires = tuple(map(int, re.findall(r'q\[(\d+)\]', rows[i + 1])))
            assert wires[0] == measured and len(wires) == 3
            ops.append(Op('mm', wires, measurement=m))
            i += 2
        else:
            condition = None
            guard = re.match(r'if\(m(\d+)==1\) ', row)
            if guard:
                condition = int(guard[1])
                row = row[guard.end():]
            kind = row.split()[0]
            assert kind in {'cx', 'h', 's', 'sdg', 't', 'tdg', 'x', 'y', 'z'}
            ops.append(Op(kind, tuple(map(int, re.findall(r'q\[(\d+)\]', row))), condition=condition))
            i += 1
    return ops


def main():
    out = ROOT/'results/aes_t3_round2'
    result = dict(local=local_checks(), orientation=orientation_identity_checks(), circuits=[])
    comparison = {r['interface']: r for r in json.loads((out/'comparison.json').read_text())}
    for typ in ['C0', 'C1']:
        path = ROOT/f'external/Minimal_T-depth_Width/Resource_Estimator/CliffordT_quantum_circuit/AES_T3_{typ}_CliffordT.qasm'
        width, source = read_author_qasm(path.read_text())
        certificate = json.loads((out/f'AES_T3_{typ}_certificate.json').read_text())
        oriented = orient(source, certificate['orientation_bits'])
        macro = exhaustive_macro_check(macro_parse(oriented), width, typ)
        rewritten, substitutions = verify_substitutions(oriented, certificate['substitutions'])
        stored = [Op(o['kind'], tuple(o['wires']), o['condition'], o['measurement']) for o in certificate['rewritten_operations']]
        assert rewritten == stored
        schedule = verify_reordering(rewritten, certificate['layers'])
        ordered = [rewritten[i] for layer in certificate['layers'] for i in layer]
        dynamic = read_dynamic(out/f'AES_T3_{typ}_round2_dynamic.qasm')
        assert ordered == dynamic
        measured = metrics(dynamic, width)
        for key, value in measured.items():
            assert comparison[typ]['candidate'][key] == value
        result['circuits'].append(dict(interface=typ, macro=macro, substitutions=substitutions,
                                        schedule=schedule, exported_dynamic_operations_match=True,
                                        metrics=measured))
    (out/'verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
