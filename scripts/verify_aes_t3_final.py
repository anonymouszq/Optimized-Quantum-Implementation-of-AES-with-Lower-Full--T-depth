"""Replay the final circuits, substitutions, cancellations and explicit schedules."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qsboxopt.quantum_schedule import metrics,verify_reordering,write_qasm
from qsboxopt.quantum_width import expand_event
from qsboxopt.quantum_cancel import verify_cancellations
from qsboxopt.cnot_resynthesis import verify_substitutions
from verify_aes_t3_quantum import local_checks
from verify_aes_t3_round2 import orientation_identity_checks,read_dynamic
from verify_aes_t3_width import verify_events,verify_three_wire
from aes_t3_final_search import check_variants


def main():
    out=ROOT/'results/aes_t3_final'
    rows=json.loads((out/'comparison.json').read_text())
    assert len(rows)==2
    result=dict(local=local_checks(),three_wire=verify_three_wire(),
                variants=check_variants(),orientation=orientation_identity_checks(),circuits=[])
    for row in rows:
        name,typ,width=row['name'],row['interface'],row['candidate']['width']
        assert width<=(72 if typ=='C0' else 80)
        cert=json.loads((out/f'{name}_certificate.json').read_text())
        logical=verify_events(cert['events'],width,typ)
        ops=[op for e in cert['events'] for op in expand_event(e)]
        ops,cancel1=verify_cancellations(ops,cert['cancel_before'])
        ops,sub=verify_substitutions(ops,cert['substitutions'])
        ops,cancel2=verify_cancellations(ops,cert['cancel_after'])
        schedule=verify_reordering(ops,cert['layers'])
        ordered=[ops[i] for layer in cert['layers'] for i in layer]
        assert read_dynamic(out/f'{name}_dynamic.qasm')==ordered
        for conditional,suffix in [(True,'dynamic'),(False,'resource')]:
            assert (out/f'{name}_{suffix}.qasm').read_text()==write_qasm(ops,width,cert['layers'],conditional)
        m=metrics(ordered,width)
        assert row['candidate']==dict(**m,explicit_schedule_depth=len(cert['layers']))
        assert m['t_count']==168 and m['t_depth']==3
        tcounts=[sum(ops[i].kind in {'t','tdg'} for i in layer) for layer in cert['layers']
                 if any(ops[i].kind in {'t','tdg'} for i in layer)]
        assert tcounts==[61,63,44]
        result['circuits'].append(dict(name=name,logical=logical,first_cancellation=cancel1,
            substitutions=sub,last_cancellation=cancel2,schedule=schedule,
            dynamic_qasm_matches=True,resource_qasm_matches=True,metrics=m,
            explicit_schedule_depth=len(cert['layers']),t_layer_counts=tcounts))
    (out/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
