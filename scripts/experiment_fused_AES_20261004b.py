"""Integrate a certified pre-affine S-box plus fused affine/MixColumns map.

Only forward state S-boxes in selected nonfinal rounds lose their eight output
affine gates. The fused column map reinstates A before M. Reverse C1 and inverse
MixColumns retain their original standard-AES interfaces.
"""
from pathlib import Path
import argparse,hashlib,json,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from scripts import experiments_allocation_20261002 as alloc
from scripts.audit_sbox_mixcolumns_fusion_20261004 import affine_form,verify_affine
from qsboxopt.quantum_width import expand_event
from qsboxopt.quantum_schedule import Op,metrics,verify_reordering
OUT=ROOT/'results/fused_AES_20261004b';OUT.mkdir(exist_ok=True)
ORIGINAL_SOURCE=alloc._build_source
ORIGINAL_LOAD=alloc.sw.base.load_new
ORIGINAL_MACROS=alloc.sw.ar._macro_component_events
ORIGINAL_INSTALL=alloc.sw.install_macros
ORIGINAL_REMAP=alloc.sw.base.remap
ORIGINAL_MIX=alloc.sw.ar.mix_state
EVIDENCE=json.loads((ROOT/'results/ancilla_liveness_20261004/sbox_mixcolumns_affine_fusion_interface.json').read_text())

def configure(variant='795',rounds=tuple(range(1,10)),candidate_path=None,reference_roles=False):
    info=next(r for r in EVIDENCE['per_component'] if r['candidate']==variant)
    path=ROOT/info['certificate'];cert=json.loads(path.read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    assert cert['cancellations']==[]
    alloc.sw.base.CERT=path;alloc.sw.ar.C0_CERT=path
    alloc.sw.base.load_new=ORIGINAL_LOAD
    original=ORIGINAL_LOAD();long_c0,im,om,tail,proof=original
    # Retain each surviving original gate's scheduled position and ID mapping.
    removed=set(info['removable_output_affine_event_indices']);ids=set();cursor=0
    for i,e in enumerate(cert['events']):
        n=len(expand_event(e))
        if i in removed:ids.update(range(cursor,cursor+n))
        cursor+=n
    raw=[g for e in cert['events'] for g in expand_event(e)]
    verify_reordering(raw,cert['layers'])
    short=[raw[i] for layer in cert['layers'] for i in layer if i<len(raw)-13 and i not in ids]
    assert len(long_c0)-len(short)==8
    stripped=[e for i,e in enumerate(cert['events'][:-13]) if i not in removed]
    alloc.sw.fused_c0=short
    alloc.sw.active_rounds=set(rounds)
    alloc.sw.base.load_new=lambda:original
    if reference_roles:
        alloc.sw.base.remap=lambda wires,ops,offset,mode:ORIGINAL_REMAP(wires,long_c0 if ops is short else ops,offset,mode)
    else:alloc.sw.base.remap=ORIGINAL_REMAP
    target=EVIDENCE['fusion']
    if candidate_path:
        data=json.loads(Path(candidate_path).read_text());gates=data['gates'];width=data.get('width',32)
        output_view=data.get('output_view',list(range(32)))
    else:
        gates=target['combined_gates'];width=32;output_view=list(range(32));data={}
    ops=[Op(g['kind'],tuple(g['wires'])) for g in gates]
    # Verify promised clean-input subspace including a possible output migration.
    rows=[1<<q if q<32 else 0 for q in range(width)];constants=[0]*width
    for g in ops:
        if g.kind=='cx':a,b=g.wires;rows[b]^=rows[a];constants[b]^=constants[a]
        else:assert g.kind=='x';constants[g.wires[0]]^=1
    assert len(set(output_view))==32
    expected=[int(x,16) for x in target['matrix_rows_hex']];constant=int(target['constant_hex'],16)
    assert [rows[q] for q in output_view]==expected
    assert [constants[q] for q in output_view]==[(constant>>q)&1 for q in range(32)]
    assert all(rows[q]==constants[q]==0 for q in range(width) if q not in output_view)
    def fused_mix(t,pool,state,mix,rnd):
        if rnd not in alloc.sw.active_rounds:ORIGINAL_MIX(t,state,mix);return
        for col in range(4):
            sl=slice(col*32,col*32+32)
            helpers=pool.take(t,width-32) if width>32 else []
            qm=state[sl]+helpers;assert len(set(qm))==width
            for g in ops:t.emit(Op(g.kind,tuple(qm[q] for q in g.wires)))
            state[sl]=[qm[q] for q in output_view]
            pool.give(qm[q] for q in range(width) if q not in output_view)
    alloc.sw.fused_mix=fused_mix
    def install_macros():
        alloc.sw.ar._macro_component_events=ORIGINAL_MACROS
        table=ORIGINAL_MACROS();table['C0_stripped']=stripped
        table['C0_canonical']=cert['events']
        alloc.sw.ar._macro_component_events=lambda:table
    alloc.sw.install_macros=install_macros
    src=ORIGINAL_SOURCE.replace('for rnd in range(1,11):','long_c0=c0\n for rnd in range(1,11):\n  c0=fused_c0 if rnd in active_rounds else long_c0',1)
    before="    states[-1][8*i:8*i+8]=ni;raw[8*i:8*i+8]=no;pool.give(z)"
    after="    if rnd in active_rounds:calls[-1]['component']='C0_stripped'\n"+before
    assert before in src;src=src.replace(before,after)
    src=src.replace('ar.mix_state(t,shifted,mix)','fused_mix(t,pool,shifted,mix,rnd)',1)
    alloc._build_source=src
    return dict(source=str(path.relative_to(ROOT)),source_sha256=info['sha256'],
                removed_events=sorted(removed),rounds=list(rounds),candidate_path=str(candidate_path) if candidate_path else None,
                candidate_sha256=hashlib.sha256(Path(candidate_path).read_bytes()).hexdigest() if candidate_path else None,
                reference_roles=reference_roles,fused_width=width,fused_metrics=metrics(ops,width),
                exact_affine_matrix_and_zero_helpers_verified=True)

def evaluate(variant='795',rounds=tuple(range(1,10)),mapping=2,reverse='ready',reference_roles=False,candidate_path=None,check=False):
    setup=configure(variant,rounds,candidate_path,reference_roles)
    tag=f'C{variant}_r'+('-'.join(map(str,rounds)) or 'none')+f'_m{mapping}_{reverse}_ref{int(reference_roles)}'
    if candidate_path:tag+='_'+Path(candidate_path).stem
    alloc.OUT=OUT/tag;alloc.OUT.mkdir(exist_ok=True)
    spec=dict(width=3040,key_first=False,mapping=mapping,interface='migrating',policy='tfirst',seed=0,reverse_order=reverse)
    result=alloc.evaluate(spec,check=check)
    result.update(tag=tag,fusion=setup)
    if check:(alloc.OUT/'verified_winner.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path);p.add_argument('--verify-tag');p.add_argument('--seconds',type=int,default=220);args=p.parse_args()
    dest=OUT/'search.json';rows=json.loads(dest.read_text())['rows'] if dest.exists() else []
    if args.verify_tag:
        row=next(r for r in rows if r['tag']==args.verify_tag)
        v='795' if 'third' in row['fusion']['source'] else '792';spec=row['spec'];f=row['fusion']
        got=evaluate(v,f['rounds'],spec['mapping'],spec['reverse_order'],f['reference_roles'],f['candidate_path'],True)
        assert got['full']==row['full'];print(json.dumps(got),flush=True);return
    jobs=[('795',[],2,'ready',False)] if args.candidate is None else []
    jobs += [(v,list(range(1,10)),m,rev,ref) for v in ['795','792'] for m,rev in [(2,'ready'),(1,'natural')] for ref in [False,True]]
    jobs += [('795',rr,2,'ready',False) for rr in [[9],[8,9],[7,8,9],list(range(1,6))]]
    start=time.time()
    for v,rounds,m,rev,ref in jobs:
        candidate=str(args.candidate) if args.candidate else None
        if any(r['fusion']['rounds']==rounds and r['spec']['mapping']==m and r['spec']['reverse_order']==rev and r['fusion']['reference_roles']==ref and r['fusion']['candidate_path']==candidate and (('third' in r['fusion']['source'])==(v=='795')) for r in rows):continue
        if time.time()-start>args.seconds:break
        row=evaluate(v,rounds,m,rev,ref,args.candidate);rows.append(row)
        dest.write_text(json.dumps({'rows':rows},indent=2),encoding='utf-8')
        print(row['tag'],row['full'],row['forward'],flush=True)

if __name__=='__main__':main()
