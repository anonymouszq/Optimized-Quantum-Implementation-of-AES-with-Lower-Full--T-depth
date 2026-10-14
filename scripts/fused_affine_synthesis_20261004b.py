"""Depth-preserving affine constant placement for the exact A^4/M target.

Put X gates in idle wire slots of an ASAP CNOT schedule, solving their output
effect over GF(2). Every emitted gate stream receives independent affine proof.
"""
from __future__ import annotations
import json,random,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qsboxopt.quantum_schedule import Op,metrics
from scripts.audit_sbox_mixcolumns_fusion_20261004 import affine_form,verify_affine
from qsboxopt.cnot_resynthesis import matrix,depth,peephole

def layers_of(gates):
    times=[0]*32;layers=[]
    for a,b in gates:
        d=max(times[a],times[b]);times[a]=times[b]=d+1
        while len(layers)<=d:layers.append([])
        layers[d].append((a,b))
    return layers

def idle_vectors(layers):
    vectors=[];slots=[]
    for d,layer in enumerate(layers):
        used={q for g in layer for q in g}
        for q in range(32):
            if q in used:continue
            v=1<<q
            for tail in layers[d+1:]:
                for a,b in tail:v^=((v>>a)&1)<<b
            vectors.append(v);slots.append((d,q))
    return vectors,slots

def representation(vectors,target,order):
    pivots={}
    for j in order:
        v=vectors[j];s=1<<j
        while v:
            p=v.bit_length()-1
            if p not in pivots:pivots[p]=(v,s);break
            w,u=pivots[p];v^=w;s^=u
    s=0;v=target
    while v:
        p=v.bit_length()-1
        if p not in pivots:return None
        w,u=pivots[p];v^=w;s^=u
    return s

def place_constants(gates,target,constant,trials=3000):
    layers=layers_of(gates);vectors,slots=idle_vectors(layers)
    rng=random.Random(20261004);order=list(range(len(slots)));best=None
    # Meet in the middle: complete coverage of every <=4-slot support.
    pairs={0:0}
    def retain(v,s):
        if v not in pairs or s.bit_count()<pairs[v].bit_count():pairs[v]=s
    for i,v in enumerate(vectors):retain(v,1<<i)
    for i,v in enumerate(vectors):
        for j in range(i):retain(v^vectors[j],(1<<i)|(1<<j))
    for v,s in pairs.items():
        if constant^v in pairs:
            cand=s^pairs[constant^v]
            if best is None or cand.bit_count()<best.bit_count():best=cand
    trial=-1
    if best is None:
        for trial in range(trials):
            rng.shuffle(order);s=representation(vectors,constant,order)
            if s is not None and (best is None or s.bit_count()<best.bit_count()):best=s
            if best is not None and best.bit_count()<=constant.bit_count():break
    if best is None:return None
    selected={slots[i] for i in range(len(slots)) if best>>i&1}
    ops=[]
    for d,layer in enumerate(layers):
        ops.extend(Op('cx',tuple(g)) for g in layer)
        ops.extend(Op('x',(q,)) for dd,q in sorted(selected) if dd==d)
    assert affine_form(ops,32)==(list(target),constant)
    verify_affine(ops,target,constant)
    return dict(gates=[dict(kind=g.kind,wires=list(g.wires)) for g in ops],
                metrics=metrics(ops,32),linear_layers=layers,
                idle_X_slots=sorted(selected),trials_used=trial+1,
                exact_GF2_affine_equality=True,full_zero_and_32_basis_checks=True,
                input_permutation=list(range(32)),output_permutation=list(range(32)))

def main():
    src=ROOT/'results/ancilla_liveness_20261004/sbox_mixcolumns_affine_fusion_interface.json'
    f=json.loads(src.read_text())['fusion'];target=tuple(int(x,16) for x in f['matrix_rows_hex']);constant=int(f['constant_hex'],16)
    gates=[tuple(g['wires']) for g in f['combined_gates'] if g['kind']=='cx']
    assert matrix(gates,32)==target
    candidate=place_constants(gates,target,constant)
    out=ROOT/'results/fused_affine_synthesis_20261004b';out.mkdir(exist_ok=True)
    result=dict(source=str(src.relative_to(ROOT)),baseline_metrics=f['combined_metrics'],
      method='Solve the exact GF(2) affine offset using X gates in idle slots of a matching-layer CNOT schedule.',
      matrix_rows_hex=f['matrix_rows_hex'],constant_hex=f['constant_hex'],candidate=candidate)
    (out/'result.json').write_text(json.dumps(result,indent=2))
    if candidate:
        exported=dict(width=32,gates=candidate['gates'],output_view=list(range(32)),
          metrics=candidate['metrics'],verification=dict(exact_GF2_affine_equality=True,
          full_zero_and_32_basis_checks=True),matrix_rows_hex=f['matrix_rows_hex'],constant_hex=f['constant_hex'])
        (out/'candidate_d11.json').write_text(json.dumps(exported,indent=2))
    print(candidate['metrics'] if candidate else 'No idle-slot solution',flush=True)
if __name__=='__main__':main()
