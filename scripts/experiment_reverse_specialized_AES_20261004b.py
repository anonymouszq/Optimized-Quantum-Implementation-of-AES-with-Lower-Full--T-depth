"""Integrate a promise-specialized uncompute S-box only at reverse-state calls.

Generic key-schedule Cxor calls are unchanged. Optional forward affine fusion
is verified separately by experiment_fused_AES_20261004b.
"""
from pathlib import Path
import argparse, hashlib, json, sys, time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from scripts import experiment_fused_AES_20261004b as fusion
from scripts import reverse_sbox_specialization_20261004b as local
from qsboxopt.quantum_width import expand_event
from qsboxopt.quantum_cancel import verify_cancellations
from qsboxopt.quantum_schedule import metrics,verify_reordering
alloc=fusion.alloc
OUT=ROOT/'results/reverse_specialized_AES_20261004b';OUT.mkdir(exist_ok=True)

def configure(path,variant='795',fused=None,reverse_rounds=tuple(range(1,11))):
    setup=fusion.configure(variant,tuple(range(1,10)) if fused else (),fused)
    cert=json.loads(Path(path).read_text());local.validate(cert['events'])
    source=json.loads((ROOT/cert['source']).read_text())
    assert hashlib.sha256((ROOT/cert['source']).read_bytes()).hexdigest()==cert['source_sha256']
    nonlinear=lambda ee:[e for e in ee if e['kind'] not in ('x','cx')]
    assert nonlinear(cert['events'])==nonlinear(source['events'])
    # Independent, history-free proof: each linear segment has the same full
    # 80-wire signature before the next unchanged nonlinear gadget.
    def segments(events):
        ans=[];pending=[]
        for e in events:
            if e['kind'] in ('x','cx'):pending.append(e)
            else:ans.append((pending,e));pending=[]
        ans.append((pending,None));return ans
    before=segments(source['events']);after=segments(cert['events']);assert len(before)==len(after)
    a=local.initial();b=a.copy()
    for (old,g),(new,h) in zip(before,after):
        assert g==h and a==b
        for e in old:local.step(a,e,local.ONES)
        for e in new:local.step(b,e,local.ONES)
        assert a==b
        if g is not None:local.step(a,g,local.ONES);local.step(b,h,local.ONES)
    raw=[g for e in cert['events'] for g in expand_event(e)]
    ops,cancel=verify_cancellations(raw,cert['cancellations'])
    order=verify_reordering(ops,cert['layers'])
    ops=[ops[i] for ll in cert['layers'] for i in ll]
    assert metrics(ops,80)==cert['metrics']
    alloc.sw.reverse_specialized_ops=ops
    alloc.sw.reverse_specialized_rounds=set(reverse_rounds)
    old="   emit('C1',c1,ar.byte(states[rnd-1],i),targets,16,f'reverse_state_round_{rnd}_byte_{i}')"
    new="   emit('C1_reverse_state' if rnd in reverse_specialized_rounds else 'C1',reverse_specialized_ops if rnd in reverse_specialized_rounds else c1,ar.byte(states[rnd-1],i),targets,16,f'reverse_state_round_{rnd}_byte_{i}')"
    assert old in alloc._build_source;alloc._build_source=alloc._build_source.replace(old,new)
    install_fused=alloc.sw.install_macros
    def install_macros():
        install_fused()
        table=alloc.sw.ar._macro_component_events();table['C1_reverse_state']=cert['events']
        alloc.sw.ar._macro_component_events=lambda:table
    alloc.sw.install_macros=install_macros
    return dict(fusion=setup,specialization=dict(path=str(path),sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        metrics=cert['metrics'],rounds=list(reverse_rounds),promised_interface=cert['promised_interface'],
        segment_equivalence=dict(segments=len(before),promised_basis_inputs=256,physical_lines=80,
            all_boundary_signatures_equal=True,unchanged_nonlinear_gadgets=True),
        cancellation_replay=cancel,reordering_replay=order))

def evaluate(path,variant='795',fused=None,mapping=None,reverse=None,reverse_rounds=tuple(range(1,11)),check=False,width=3040):
    setup=configure(path,variant,fused,reverse_rounds)
    if mapping is None:mapping=2 if variant=='795' else 1
    if reverse is None:reverse='ready' if variant=='795' else 'natural'
    spec=dict(width=width,key_first=False,mapping=mapping,interface='migrating',policy='tfirst',seed=0,reverse_order=reverse)
    tag=f'C{variant}_{Path(path).stem}_m{mapping}_{reverse}_w{width}'
    if fused:tag+='_'+Path(fused).stem
    if len(reverse_rounds)!=10:tag+='_r'+'-'.join(map(str,reverse_rounds))
    alloc.OUT=OUT/tag;alloc.OUT.mkdir(exist_ok=True)
    row=alloc.evaluate(spec,check=check);row.update(tag=tag,**setup)
    if check:(alloc.OUT/'verified_winner.json').write_text(json.dumps(row,indent=2),encoding='utf-8')
    return row

def main():
    p=argparse.ArgumentParser();p.add_argument('candidate',type=Path,nargs='?');p.add_argument('--seconds',type=int,default=180);p.add_argument('--verify-tag');args=p.parse_args()
    dest=OUT/'search.json';rows=json.loads(dest.read_text())['rows'] if dest.exists() else []
    if args.verify_tag:
        r=next(r for r in rows if r['tag']==args.verify_tag);s=r['spec'];f=r['fusion'];sp=r['specialization']
        row=evaluate(sp['path'],'795' if 'third' in f['source'] else '792',f['candidate_path'],s['mapping'],s['reverse_order'],sp['rounds'],True,s['width'])
        assert row['full']==r['full'];print(json.dumps(row),flush=True);return
    fused=ROOT/'results/fused_affine_synthesis_20261004b/candidate_d11.json'
    paths=[args.candidate] if args.candidate else sorted(p for p in (ROOT/'results/reverse_sbox_specialization_20261004b').glob('candidate_*.json') if 'events' in json.loads(p.read_text()))
    start=time.time()
    for path in paths:
        for v,m,rev in [('795',2,'ready'),('792',1,'natural')]:
            for ff in [None,fused]:
                if time.time()-start>args.seconds:return
                tag=f'C{v}_{Path(path).stem}_m{m}_{rev}_w3040'+('_'+Path(ff).stem if ff else '')
                if any(r['tag']==tag for r in rows):continue
                row=evaluate(path,v,ff,m,rev);rows.append(row)
                dest.write_text(json.dumps(dict(rows=rows),indent=2),encoding='utf-8')
                print(row['tag'],row['full'],row['forward'],flush=True)

if __name__=='__main__':main()
