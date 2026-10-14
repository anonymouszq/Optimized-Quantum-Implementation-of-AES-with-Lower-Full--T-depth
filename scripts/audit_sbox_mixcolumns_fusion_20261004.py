"""Reproduce the certified C0-output/MixColumns affine fusion interface.

Default: regenerate structural evidence and stripped event programs. Existing
bounded-search metadata is retained only when the regenerated combined gate
stream is identical. --check-only independently checks the published evidence
without rewriting it or running synthesis. --repeat-bounded-search repeats the
small, previously reported scheduling/peephole/greedy experiment.

No AES implementation or input certificate is modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from scripts import aes_whole_semantic_integrate as base
from scripts.aes128_pipeline_joint_optimize import load_mix
from scripts.aes_whole_commuting_frontier import graph, schedule, verify, Timeline
from scripts.experiment_sbox_20261002 import step
from qsboxopt.quantum_width import truth_patterns, expand_event
from qsboxopt.quantum_schedule import Op, metrics
from qsboxopt.quantum_cancel import cancel_self_inverse, verify_cancellations

SOURCES = [
    ('795', 'results/aes_t3_semantic_third_20260911/best_certificate.json'),
    ('792', 'results/sbox_optimization_20261002/C0_candidate_certificate.json'),
]
SEARCH_FIELDS = ('cancellation_proof', 'cancellation_trace',
                 'commuting_schedule_search', 'bounded_synthesis_experiment')


def gate_dict(op):
    return dict(kind=op.kind, wires=list(op.wires))


def audit_component(name, relative_path):
    path = ROOT / relative_path
    certificate = json.loads(path.read_text())
    all_events = certificate['events']
    base.CERT = path
    # Replays the original cancellation and scheduling certificates and derives
    # the migrating interface from the inverse canonicalization permutation.
    _, inputs, outputs, tail, _ = base.load_new()
    assert len(tail) == 13
    assert all(e.get('canonicalization') for e in all_events[-13:])
    events = all_events[:-13]
    support = set(outputs)
    last_cross = max(i for i,e in enumerate(events)
                     if support.intersection(e['wires']) and not set(e['wires']) <= support)
    selected = [i for i in range(last_cross+1, len(events))
                if support.intersection(events[i]['wires'])]
    assert all(events[i]['kind'] in ('cx', 'x')
               and set(events[i]['wires']) <= support for i in selected)
    selected_set = set(selected)
    assert all(not support.intersection(e['wires'])
               for i,e in enumerate(events) if i > last_cross and i not in selected_set)
    affine = [dict(kind=events[i]['kind'],
                   wires=[outputs.index(q) for q in events[i]['wires']]) for i in selected]
    stripped_events = [e for i,e in enumerate(events) if i not in selected_set]

    ones = (1 << 256) - 1
    initial = list(truth_patterns(8)) + [0] * 64
    original = initial[:]
    stripped = initial[:]
    for e in events:
        step(original, e, ones)
    for e in stripped_events:
        step(stripped, e, ones)
    assert all(original[q] == stripped[q] for q in range(72) if q not in support)
    completed = stripped[:]
    for i in selected:
        step(completed, events[i], ones)
    assert completed == original
    assert all(original[q] == 0 for q in range(72) if q not in set(inputs + outputs))
    last_and = max(i for i,e in enumerate(events) if e['kind'] in ('and3', 'and4'))
    last_cleanup = max(i for i,e in enumerate(events) if e['kind'] == 'cleanup')
    proof = dict(all_remaining_events_after_last_cross_disjoint_from_output=True,
                 full_72_wire_truth_table_equal_after_appending_A=True,
                 nonoutput_signatures_unchanged=True, all_56_scratch_zero=True,
                 basis_inputs=256)
    report = dict(candidate=name, certificate=relative_path,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        canonical_event_count=len(all_events), migrating_event_count=len(events),
        last_and_event=last_and, last_cleanup_event=last_cleanup,
        event_indexing='zero-based in certificate events', input_view=inputs,
        output_view=outputs,
        true_final_linear_cleanup_tail=dict(start=last_cleanup+1,
            count=len(events)-last_cleanup-1,
            kinds=dict(Counter(e['kind'] for e in events[last_cleanup+1:])),
            disjoint_from_output=all(not support.intersection(e['wires'])
                                     for e in events[last_cleanup+1:])),
        last_output_nonoutput_event=dict(index=last_cross,event=events[last_cross]),
        removable_output_affine_event_indices=selected, output_affine_gates=affine,
        removal_proof=proof, migrating_stripped_event_count=len(stripped_events),
        migrating_stripped_cnot=sum(g.kind == 'cx' for e in stripped_events
                                    for g in expand_event(e)))
    artifact = dict(source_certificate=relative_path, source_sha256=report['sha256'],
        events=stripped_events, input_view=inputs, output_view=outputs,
        factored_affine_gates=affine, removed_event_indices=selected,
        verification=proof,
        note='These events have pre-affine S-box output; append A or M after A as specified. No source cancellation indices or schedules are reusable without regeneration.')
    return report, artifact


def affine_form(ops, width):
    rows = [1 << q for q in range(width)]
    constant = 0
    for g in ops:
        if g.kind == 'cx':
            a,b = g.wires
            rows[b] ^= rows[a]
            constant ^= ((constant >> a) & 1) << b
        else:
            assert g.kind == 'x'
            constant ^= 1 << g.wires[0]
    return rows, constant


def verify_affine(ops, rows, constant):
    for value in [0] + [1 << q for q in range(len(rows))]:
        actual = value
        for g in ops:
            if g.kind == 'cx':
                a,b = g.wires
                actual ^= ((actual >> a) & 1) << b
            else:
                actual ^= 1 << g.wires[0]
        expected = constant
        for q,row in enumerate(rows):
            expected ^= ((value & row).bit_count() & 1) << q
        assert actual == expected


def structural_evidence():
    reports, artifacts = [], {}
    for name,source in SOURCES:
        report, artifact = audit_component(name, source)
        reports.append(report)
        artifacts[name] = artifact
    assert reports[0]['output_affine_gates'] == reports[1]['output_affine_gates']
    affine = reports[0]['output_affine_gates']
    layers,_ = load_mix()
    ops = [Op(g['kind'], tuple(8*b+q for q in g['wires']))
           for b in range(4) for g in affine]
    for layer in layers:
        for a,b in layer:
            ops.append(Op('cx', (8*(a//8)+7-a%8, 8*(b//8)+7-b%8)))
    rows, constant = affine_form(ops, 32)
    verify_affine(ops, rows, constant)
    fusion = dict(width=32,
        wire_convention='byte-major; wire8*b+j is MSB-indexed output bit j of byte b',
        output_tail_per_byte=affine,
        mixcolumns_bit_index_conversion='q ->8*(q//8)+7-(q%8)',
        combined_gates=[gate_dict(g) for g in ops], combined_metrics=metrics(ops, 32),
        matrix_rows_hex=[hex(x) for x in rows], constant_hex=hex(constant),
        matrix_checks=33,
        proof='CNOT/X affine form is completely determined by zero and32 basis vectors.',
        placement='For each forward non-final round, strip A from16 C0 calls; after ShiftRows apply M composed with A on each group of4 output bytes. Keep A in round10. Reverse uses ordinary M inverse because stored round values are still standard M(S(x)).',
        caveat='No gate-count or depth improvement claimed: this exports a verified joint affine synthesis target. Existing C0 macro verification must be updated to the stripped event stream; treating it as standard S output would be incorrect.')
    return dict(per_component=reports, fusion=fusion), artifacts


def repeat_bounded_search(fusion):
    from qsboxopt.cnot_resynthesis import candidates, peephole, matrix
    ops = [Op(g['kind'], tuple(g['wires'])) for g in fusion['combined_gates']]
    reduced, trace = cancel_self_inverse(ops)
    checked, proof = verify_cancellations(ops, trace)
    assert checked == reduced
    rows, best = [], None
    for seed in range(32):
        t = Timeline(32)
        order = schedule(reduced, graph(reduced,32), t, seed)
        metric = t.metric_dict()
        rows.append(dict(seed=seed, metrics=metric))
        if best is None or metric['full_depth'] < best['metrics']['full_depth']:
            best = dict(seed=seed, metrics=metric, order=order,
                        gates=[gate_dict(g) for _,g in t.records],
                        verification=verify(reduced,order,32))
    fusion['cancellation_proof'] = proof
    fusion['cancellation_trace'] = trace
    fusion['commuting_schedule_search'] = dict(seeds=32, rows=rows, best=best)
    target = tuple(int(x,16) for x in fusion['matrix_rows_hex'])
    constant = int(fusion['constant_hex'],16)
    linear = [tuple(g['wires']) for g in fusion['combined_gates'] if g['kind']=='cx']
    assert matrix(linear,32) == target
    start = time.monotonic()
    variants = []

    def evaluate(gates):
        assert matrix(gates,32) == target
        candidate = [Op('cx',tuple(g)) for g in gates]
        candidate += [Op('x',(q,)) for q in range(32) if (constant>>q)&1]
        verify_affine(candidate, target, constant)
        t = Timeline(32)
        order = schedule(candidate,graph(candidate,32),t,0)
        return dict(metrics=t.metric_dict(), gates=[gate_dict(g) for _,g in t.records],
                    checks=verify(candidate,order,32))

    for seed in range(4):
        gates, trace = peephole(linear,32,seed=seed,passes=2,allow_equal=True)
        variants.append(dict(method='exact_four_wire_peephole', seed=seed,
                             cnot=len(gates),trace=trace,**evaluate(gates)))
    _, choices = candidates([Op('cx',g) for g in linear], trials=4)
    for entry in choices[:4]:
        variants.append(dict(method='linear_synthesis',
            synthesis={k:v for k,v in entry.items() if k!='gates'},
            **evaluate(entry['gates'])))
    fusion['bounded_synthesis_experiment'] = dict(seconds=time.monotonic()-start,
                                                 variants=variants)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--repeat-bounded-search', action='store_true')
    parser.add_argument('--output-directory', type=Path,
                        default=ROOT/'results/ancilla_liveness_20261004')
    args = parser.parse_args()
    result, artifacts = structural_evidence()
    path = args.output_directory/'sbox_mixcolumns_affine_fusion_interface.json'
    existing = json.loads(path.read_text()) if path.exists() else None
    if args.check_only:
        assert existing is not None, path
        assert existing['per_component'] == result['per_component']
        for key,value in result['fusion'].items():
            assert existing['fusion'][key] == value, key
        for name,artifact in artifacts.items():
            published = json.loads((args.output_directory/f'C0_{name}_stripped_migrating_events.json').read_text())
            assert published == artifact, name
        print('PASS: both full72-wire byte signatures, clean scratch, affine33-point checks, source hashes and published gate/event lists.')
        return
    if args.repeat_bounded_search:
        repeat_bounded_search(result['fusion'])
    elif existing and existing['fusion']['combined_gates'] == result['fusion']['combined_gates']:
        for key in SEARCH_FIELDS:
            if key in existing['fusion']:
                result['fusion'][key] = existing['fusion'][key]
    args.output_directory.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    for name,artifact in artifacts.items():
        (args.output_directory/f'C0_{name}_stripped_migrating_events.json').write_text(
            json.dumps(artifact,indent=2),encoding='utf-8')
    print('Verified and regenerated', path)
    print(result['fusion']['combined_metrics'])


if __name__ == '__main__':
    main()
