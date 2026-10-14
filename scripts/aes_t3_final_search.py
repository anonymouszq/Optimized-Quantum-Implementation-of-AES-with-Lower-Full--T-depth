"""A further bounded search over equivalent AND parity networks and controls."""
import argparse
import copy
import json
from pathlib import Path
import random
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qsboxopt.quantum_width import expand_event,and3_body
from qsboxopt.quantum_schedule import SchedulingProblem,metrics
from verify_aes_t3_quantum import step
from verify_aes_t3_width import verify_events


def check_variants():
    error=0.0
    for i in range(8):
        init=np.eye(8,dtype=complex)[:,i]
        values=[]
        for variant in ['standard','chain','fork']:
            for a,b in [(0,1),(1,0)]:
                v=init.copy()
                for op in and3_body(a,b,2,variant):v=step(v,op)
                values.append(v)
        error=max(error,max(float(np.max(np.abs(v-values[0]))) for v in values))
    assert error<1e-12
    return dict(full_unitary_max_error=error,basis_vectors=8,variants=['standard','chain','fork'],both_control_orders=True)


def transform(base,choices):
    events=copy.deepcopy(base);j=0
    for e in events:
        if e['kind'] not in {'and3','and4','cleanup'}:continue
        choice=choices[j];j+=1
        if choice&1:
            e['wires'][0],e['wires'][1]=e['wires'][1],e['wires'][0]
            if 'logical' in e:e['logical'][0],e['logical'][1]=e['logical'][1],e['logical'][0]
        if e['kind']=='and3':e['variant']='fork' if choice&2 else 'chain'
    return events


def score(layers):
    return len(layers),sum((i+1)**2*len(layer) for i,layer in enumerate(layers))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--interface',choices=['C0','C1'],required=True)
    ap.add_argument('--trials',type=int,default=768);ap.add_argument('--seed',type=int,default=904)
    args=ap.parse_args();typ=args.interface;width=72 if typ=='C0' else 80
    out=ROOT/'results/aes_t3_final';out.mkdir(exist_ok=True)
    oldpath=ROOT/f'results/aes_t3_fixed_width/AES_T3_{typ}_Q{width}_depth_certificate.json'
    old=json.loads(oldpath.read_text());base=old['events']
    domains=[4 if e['kind']=='and3' else 2 for e in base if e['kind'] in {'and3','and4','cleanup'}]
    current=[0]*len(domains);best_score=score(old['layers']);current_score=best_score
    local=check_variants();history=[];seen=set();rng=random.Random(args.seed);start=time.time()
    best=dict(events=base,layers=old['layers'],choices=current[:],trial=-1)
    for trial in range(args.trials):
        choices=current[:]
        for j in rng.sample(range(len(domains)),1 if trial%6 else rng.choice([2,3,5])):
            choices[j]=(choices[j]+rng.randrange(1,domains[j]))%domains[j]
        if tuple(choices) in seen:continue
        seen.add(tuple(choices))
        events=transform(base,choices);ops=[op for e in events for op in expand_event(e)]
        model=SchedulingProblem(ops,width)
        if len(model.tgroups)!=3:continue
        best_layers=None
        for s in range(16):
            layers=model.schedule(s,[0,.5,1.5,3,5,8][s%6],bool((s//6)%2))
            if best_layers is None or score(layers)<score(best_layers):best_layers=layers
        key=score(best_layers)
        if key<current_score or (key[0]==current_score[0] and rng.random()<.07):
            current,current_score=choices,key
        if key<best_score:
            best_score=key;best=dict(events=events,layers=best_layers,choices=choices,trial=trial)
            history.append(dict(trial=trial,depth=key[0],score=key[1],seconds=time.time()-start))
            print(typ,history[-1],flush=True)
            (out/f'search_{typ}.json').write_text(json.dumps(dict(**best,width=width,history=history,completed=False)))
        if trial and trial%192==0:current,current_score=best['choices'][:],best_score
    logical=verify_events(best['events'],width,typ)
    (out/f'search_{typ}.json').write_text(json.dumps(dict(**best,width=width,history=history,completed=True,
        trials=args.trials,evaluated=len(seen),seed=args.seed,local=local,logical=logical)))
    print('DONE',typ,'depth',len(best['layers']),'evaluated',len(seen),flush=True)


if __name__=='__main__':main()
