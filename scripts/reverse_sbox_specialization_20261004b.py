"""Specialize Cxor ONLY to the reverse-state promise y=S(x).

Each replaced X/CNOT window preserves every physical-wire signature on all
256 promised basis inputs. Nonlinear gadgets and measurement cleanup events
remain identical. Thus no basis-dependent relative phase is introduced.
"""
from __future__ import annotations
import hashlib,json,random,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from scripts.experiment_sbox_20261002 import step,synth,schedule
from qsboxopt.quantum_width import truth_patterns,expand_event
from qsboxopt.quantum_schedule import metrics,verify_reordering,write_qasm
from qsboxopt.quantum_cancel import cancel_self_inverse,verify_cancellations
from qsboxopt.sboxes import SBOXES
OUT=ROOT/'results/reverse_sbox_specialization_20261004b';OUT.mkdir(exist_ok=True)
ONES=(1<<256)-1

def initial():
    patterns=list(truth_patterns(8))
    outputs=[sum(((SBOXES['AES_REV'][v]>>bit)&1)<<v for v in range(256)) for bit in range(8)]
    return patterns+outputs+[0]*64

def validate(events):
    v=initial()
    for e in events:step(v,e,ONES)
    assert v[:8]==list(truth_patterns(8)) and all(z==0 for z in v[8:])
    return dict(promised_inputs=256,input_preserved=True,target_zero=True,all_64_scratch_zero=True,gadget_promises=True)

def rewrite(events,seed,deadline):
    rng=random.Random(seed);v=initial();out=[];proof=[];i=0
    while i<len(events):
        if time.time()>deadline:raise TimeoutError
        e=events[i]
        if e['kind'] not in ('cx','x'):
            step(v,e,ONES);out.append(e);i+=1;continue
        # A zero-valued control is an identity on the entire promised subspace.
        if e['kind']=='cx' and v[e['wires'][0]]==0:
            proof.append(dict(start=i,end=i+1,before=1,after=0,reason='zero_control',all_80_signatures_equal=True));i+=1;continue
        end=i
        while end<len(events) and events[end]['kind'] in ('cx','x'):end+=1
        lengths=sorted({min(end-i,z) for z in (3,5,7,11,17,24,40,64,128)},reverse=True);rng.shuffle(lengths);accepted=None
        for length in lengths:
            if length<2:continue
            wanted=v[:]
            for z in events[i:i+length]:step(wanted,z,ONES)
            for attempt in range(2):
                rev=bool(attempt%2)
                trial=synth(wanted if rev else v,v if rev else wanted,rng,length-1,ONES,False,deadline)
                if trial is None:continue
                if rev:trial=list(reversed(trial))
                actual=v[:]
                for z in trial:step(actual,z,ONES)
                assert actual==wanted
                accepted=trial,wanted,length,rev;break
            if accepted:break
        if accepted:
            trial,wanted,length,rev=accepted;out+=trial;v=wanted
            proof.append(dict(start=i,end=i+length,before=length,after=len(trial),reverse=rev,all_80_signatures_equal=True));i+=length
        else:step(v,e,ONES);out.append(e);i+=1
    assert v[:8]==list(truth_patterns(8)) and all(z==0 for z in v[8:])
    return out,proof

def main():
    source=ROOT/'results/aes_t3_final/AES_Sbox_C1_Q80_T3_best_certificate.json';cert=json.loads(source.read_text());events=cert['events'];validate(events)
    start=time.time();deadline=start+150;records=[];best=None;bestevents=events
    for trial in range(8):
        try:candidate,proof=rewrite(bestevents,202610040+trial,deadline)
        except TimeoutError:break
        validation=validate(candidate)
        assert [e for e in candidate if e['kind'] not in ('cx','x')]==[e for e in events if e['kind'] not in ('cx','x')]
        raw=[g for e in candidate for g in expand_event(e)];ops,cancellations=cancel_self_inverse(raw);checked,cancelproof=verify_cancellations(raw,cancellations);assert checked==ops
        selected=schedule(ops,80,64,202610040+trial*64)
        if selected:
            key,m,layers=selected;ordering=verify_reordering(ops,layers)
            row=dict(trial=trial,metrics=m,rewrites=len(proof));records.append(row);print(row,flush=True)
            if best is None or (m['full_depth'],m['cnot'])<(best['metrics']['full_depth'],best['metrics']['cnot']):
                best=dict(events=candidate,cancellations=cancellations,layers=layers,metrics=m,
                    source=str(source.relative_to(ROOT)),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    promised_interface='|x>|S(x)>|0^64> -> |x>|0^8>|0^64>; reverse state only; never generic key targets',
                    validation=validation,window_proofs=proof,source_events=bestevents,ordering=ordering,cancellation_verification=cancelproof)
                (OUT/'best_certificate.json').write_text(json.dumps(best,indent=2));bestevents=candidate
                (OUT/'best_dynamic.qasm').write_text(write_qasm(ops,80,layers,True))
        if time.time()>deadline:break
    result=dict(seconds=time.time()-start,records=records,best_metrics=best['metrics'] if best else None,
      generic_C1_reference=dict(width=80,full_depth=88,t_depth=3,cnot=821),
      limitation='Full AES integration and independent QASM replay pending; valid only under target=S(input).')
    (OUT/'search.json').write_text(json.dumps(result,indent=2));print('DONE',result,flush=True)
if __name__=='__main__':main()
