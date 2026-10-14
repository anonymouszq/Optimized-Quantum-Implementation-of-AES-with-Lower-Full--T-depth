"""Compositional quantum and exhaustive allocated-register verification."""
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qsboxopt.quantum_width import and3_body, expand_event, truth_patterns
from qsboxopt.quantum_schedule import Op, verify_reordering, metrics
from qsboxopt.sboxes import SBOXES
from verify_aes_t3_quantum import step, local_checks
from verify_aes_t3_round2 import read_dynamic


def verify_three_wire():
    error=0.0
    for a in [0,1]:
        for b in [0,1]:
            v=np.eye(8,dtype=complex)[:,a+2*b]
            for op in [Op('h',(2,)),Op('t',(2,))]+and3_body(0,1,2):
                v=step(v,op)
            expected=np.eye(8,dtype=complex)[:,a+2*b+4*(a&b)]
            error=max(error,float(np.max(np.abs(v-expected))))
    assert error<1e-12
    return dict(max_isometry_error=error, all_four_control_inputs=True,
                prepared_state='T H |0>', preparation_T_count=1, body_T_count=3,
                preparation_included_in_export=True)


def verify_events(events,width,typ):
    inputs=16 if typ=='C1' else 8
    patterns=truth_patterns(inputs)
    n=1<<inputs
    ones=(1<<n)-1
    wires=[0]*width
    wires[:inputs]=patterns
    counts={k:0 for k in ['prep','and3','and4','cleanup','cx','x']}
    for index,event in enumerate(events):
        k=event['kind'];q=event['wires'];counts[k]+=1
        assert len(q)==len(set(q)) and all(0<=v<width for v in q)
        if k=='prep':
            assert wires[q[0]]==0,(index,'nonzero magic preparation')
            wires[q[0]]='magic'
        elif k in {'and3','and4'}:
            a,b,c=q[:3]
            assert isinstance(wires[a],int) and isinstance(wires[b],int)
            if k=='and3':
                assert wires[c]=='magic',(index,'missing prepared magic state')
            else:
                assert wires[c]==0 and wires[q[3]]==0,(index,'unclean QAND')
            wires[c]=wires[a]&wires[b]
        elif k=='cleanup':
            a,b,c=q
            assert wires[c]==wires[a]&wires[b],(index,'cleanup promise')
            wires[c]=0
        elif k=='cx':
            a,b=q
            assert isinstance(wires[a],int) and isinstance(wires[b],int),(index,'magic state touched before AND')
            wires[b]^=wires[a]
        else:
            assert k=='x' and isinstance(wires[q[0]],int)
            wires[q[0]]^=ones
    for bit in range(8):
        assert wires[bit]==patterns[bit]
        values=bytes(sum(((SBOXES['AES_REV'][(8*i+j)&255]>>bit)&1)<<j for j in range(8)) for i in range(n//8))
        expected=int.from_bytes(values,'little')
        if typ=='C1':expected^=patterns[8+bit]
        assert wires[8+bit]==expected,('wrong AES output',bit)
    assert all(v==0 for v in wires[16:])
    assert counts['prep']==counts['and3']
    assert counts['and3']+counts['and4']==42
    return dict(exhaustive_inputs=n, aes_correct=True, inputs_preserved=True,
                all_work_qubits_zero=True, all_allocation_and_gadget_promises=True,
                all_prepared_states_consumed=True, event_counts=counts)


def main():
    out=ROOT/'results/aes_t3_width'
    comparisons=json.loads((out/'comparison.json').read_text())
    result=dict(local=local_checks(), three_wire=verify_three_wire(), circuits=[])
    for row in comparisons:
        name=row['name'];typ=row['interface']
        cert=json.loads((out/f'{name}_certificate.json').read_text())
        logical=verify_events(cert['events'],row['candidate']['width'],typ)
        ops=[op for e in cert['events'] for op in expand_event(e)]
        schedule=verify_reordering(ops,cert['layers'])
        ordered=[ops[i] for layer in cert['layers'] for i in layer]
        assert read_dynamic(out/f'{name}_dynamic.qasm')==ordered
        measured=metrics(ordered,row['candidate']['width'])
        for key,value in measured.items():assert row['candidate'][key]==value
        result['circuits'].append(dict(name=name,logical=logical,schedule=schedule,
                                       dynamic_export_matches=True,metrics=measured))
    (out/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
