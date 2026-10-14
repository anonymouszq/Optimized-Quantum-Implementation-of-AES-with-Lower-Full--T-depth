"""Bounded, isolated allocation search; existing AES certificates are not modified."""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import random
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT), str(ROOT/'scripts')]
from scripts import aes_streaming_workspace as sw
from qsboxopt.quantum_schedule import metrics

OUT=ROOT/'results/allocation_optimization_20261002'
OUT.mkdir(exist_ok=True)
BasePool=sw.ar.ZeroPool
orig_remap=sw.base.remap

def ordered_indices(t,state,targets,mode):
    if mode=='natural':return range(16)
    if mode=='reverse':return reversed(range(16))
    if mode=='rows':return [4*c+r for r in range(4) for c in range(4)]
    if mode=='even_odd':return list(range(0,16,2))+list(range(1,16,2))
    def key(i):
        wires=state[8*i:8*i+8]+([] if targets is None else targets[8*i:8*i+8])
        T=max(t.t_ready[q] for q in wires);D=max(t.full_ready[q] for q in wires)
        if mode=='ready':return T,D,i
        if mode=='late':return -T,-D,i
        raise ValueError(mode)
    return sorted(range(16),key=key)

_build_source=inspect.getsource(sw.build).replace('def build(', 'def build_ordered(')
_build_source=_build_source.replace("interface='canonical'):", "interface='canonical',forward_order='natural',reverse_order='natural'):")
_build_source=_build_source.replace('for i in range(16):', 'for i in ordered_indices(t,states[-1],None,forward_order):',1)
_build_source=_build_source.replace('for i in range(16):', 'for i in ordered_indices(t,states[rnd-1],raw,reverse_order):',1)

def install_cache():
    new=sw.base.load_new()
    comp={k:sw.load_component(k) for k in ['C1']}
    mix=sw.load_mix()
    sw.base.load_new=lambda:new
    sw.load_component=lambda k:comp[k]
    sw.load_mix=lambda:mix

def build(config,policy='tfirst',seed=0):
    class SearchPool(BasePool):
        def __init__(self,wires):
            super().__init__(wires)
            rng=random.Random(seed)
            self.tie={q:rng.random() for q in range(config['width'])}
        def take(self,t,n):
            assert len(self.wires)>=n
            def key(q):
                T,D=t.t_ready[q],t.full_ready[q]
                if policy=='tfirst':return T,D,q
                if policy=='reverse_tie':return T,D,-q
                if policy=='random_tie':return T,D,self.tie[q]
                if policy=='bucket4':return T,D//4,self.tie[q]
                if policy=='bucket8':return T,D//8,self.tie[q]
                if policy=='bucket16':return T,D//16,self.tie[q]
                if policy=='history_full':return (D,T,q) if n==32 else (T,D,q)
                if policy=='weighted4':return T*4+D,T,D,q
                raise ValueError(policy)
            chosen=sorted(self.wires,key=key)[:n]
            self.wires.difference_update(chosen)
            self.minimum_size=min(self.minimum_size,len(self.wires))
            self.allocations+=n
            self.max_selected_ready=max(self.max_selected_ready,max((t.full_ready[q] for q in chosen),default=0))
            return chosen
    sw.ar.ZeroPool=SearchPool
    try:
        if 'forward_order' in config or 'reverse_order' in config:
            ns=dict(vars(sw));ns['ordered_indices']=ordered_indices
            exec(_build_source,ns)
            return ns['build_ordered'](**config)
        return sw.build(**config)
    finally:sw.ar.ZeroPool=BasePool

def evaluate(spec,check=False):
    config={k:v for k,v in spec.items() if k not in ['policy','seed']}
    start=time.time()
    r=build(config,spec.get('policy','tfirst'),spec.get('seed',0))
    raw=[g for _,g in r['timeline'].records]
    parts=[raw[:r['cut']],raw[r['cut']:]]
    t=sw.Timeline(config['width']);orders=[]
    for p in parts:
        orders.append(sw.schedule(p,sw.graph(p,t.width),t,0))
        if len(orders)==1:forward=t.metric_dict()
    row=dict(spec=spec,forward=forward,full=t.metric_dict(),DW=t.width*t.full_depth,
             eligible=t.t_depth<=54 and forward['t_depth']<=30,
             pool_minimum=r['pool'].minimum_size,seconds=time.time()-start)
    if check:
        row['reordering_checks']=[sw.verify(p,o,t.width) for p,o in zip(parts,orders)]
        assert metrics([g for _,g in t.records],t.width)==row['full']
        sw.install_macros()
        f=sw.ar.compose_macro_program(r['timeline'],r['calls'],r['cut'])
        a=sw.ar.compose_macro_program(r['timeline'],r['calls'],len(raw))
        row['macro_checks']=sw.ar.simulate_macro_program(a,len(f),t.width,r['states'][10])
        from scripts import audit_aes_extended_vectors_20260928 as audit
        cases=audit.make_cases();audit.CASE_COUNT=len(cases)
        initial=audit.input_masks(t.width,cases)
        vals,boundary=audit.execute([(g['kind'],g['wires']) for g in a],initial.copy(),len(f))
        expected,_=audit.expected_output_masks(cases)
        audit.assert_ciphertext(boundary,r['states'][10],expected)
        assert vals[:256]==initial[:256] and all(v==0 for v in vals[256:])
        row['extended_basis_audit']=dict(vectors=len(cases),random_vectors=audit.RANDOM_CASES,seed=audit.SEED,
          ciphertext_matches_reference=True,key_plaintext_restored=True,all_work_lines_zero=True,
          method='bit-sliced execution of rebuilt physical QAND/CNOT/X macro stream; unchanged certified QAND gadgets')
        hard=sw.Timeline(config['width'])
        for i,p in enumerate(parts):
            if i:
                hard.full_ready=[hard.full_depth]*hard.width
                hard.t_ready=[hard.t_depth]*hard.width
            sw.schedule(p,sw.graph(p,hard.width),hard,0)
        row['hard_barrier']=hard.metric_dict()
        row['ciphertext_view']=r['states'][10]
        row['source_gate_stream_sha256']=hashlib.sha256('\n'.join(repr(g) for g in raw).encode()).hexdigest()
        sw.ar.write_macro_program(OUT/'winner_compute_uncompute.qand',t.width,'AES128_COMPUTE_UNCOMPUTE',a,r['states'][10],insertion_after=len(f))
        qpath=OUT/'winner_compute_uncompute.qasm.gz'
        t.next_measurement=r['timeline'].next_measurement
        row['export']=sw.ar.write_scheduled_qasm_gz(qpath,t,description='Bounded allocation search winner; unchanged certified components; ciphertext comparator excluded.')
    return row

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--check-spec',type=Path)
    ap.add_argument('--seconds',type=int,default=540)
    ap.add_argument('--resume',action='store_true')
    args=ap.parse_args();install_cache()
    if args.check_spec:
        data=json.loads(args.check_spec.read_text());spec=data.get('spec',data)
        row=evaluate(spec,True)
        (OUT/'verified_winner.json').write_text(json.dumps(row,indent=2))
        print(json.dumps(row),flush=True);return
    base=dict(width=3040,key_first=False,mapping=1,interface='migrating',policy='tfirst',seed=0)
    jobs=[base]
    jobs += [dict(base,width=w) for w in [3032,3024,3016,2992,2960,2944,2928,2912]]
    jobs += [dict(base,mapping=m) for m in [0,2]]
    jobs += [dict(base,policy=p,seed=s) for p,s in [('reverse_tie',0),('random_tie',1),('random_tie',2),('random_tie',3),('bucket4',1),('bucket8',1),('bucket16',1)]]
    jobs += [dict(base,histories=[r for r in range(1,10) if r!=omit]) for omit in [1,3,6,9]]
    jobs += [dict(base,histories=list(range(1,11)))]
    jobs += [dict(base,width=w,policy=p,seed=1) for w in [3008,2976] for p in ['random_tie','bucket4','bucket8']]
    jobs += [dict(base,width=w) for w in [3039,3038,3037,3036,3035,3034,3033,3028,3000]]
    jobs += [dict(base,reverse_order=o) for o in ['reverse','rows','even_odd','ready','late']]
    jobs += [dict(base,forward_order=o) for o in ['rows','ready','late']]
    jobs += [dict(base,policy='history_full')]
    rows=json.loads((OUT/'search.json').read_text())['rows'] if args.resume else []
    start=time.time()
    for i,spec in enumerate(jobs):
        if any(r['spec']==spec for r in rows):continue
        if time.time()-start>args.seconds:break
        row=evaluate(spec);rows.append(row)
        print(i,json.dumps(spec),row['full']['full_depth'],row['full']['t_depth'],row['DW'],round(row['seconds'],2),flush=True)
        eligible=[r for r in rows if r['eligible']]
        bestD=min(eligible,key=lambda r:(r['full']['full_depth'],r['full']['width']))
        bestDW=min(eligible,key=lambda r:r['DW'])
        bestW=min(eligible,key=lambda r:(r['full']['width'],r['full']['full_depth']))
        (OUT/'search.json').write_text(json.dumps(dict(rows=rows,best_depth=bestD,best_dw=bestDW,best_width=bestW,elapsed=time.time()-start),indent=2))
    print('BEST_DEPTH',json.dumps(bestD),flush=True)
    print('BEST_DW',json.dumps(bestDW),flush=True)
    (OUT/'winner_spec.json').write_text(json.dumps(bestD['spec'],indent=2))

if __name__=='__main__':main()
