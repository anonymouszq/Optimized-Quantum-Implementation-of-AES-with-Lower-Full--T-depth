"""Whole-AES exact commuting scheduler, preserving the forward/oracle cut.

No logical gate is deleted, no ancilla is introduced, and neither side of the
oracle cut is moved across it. Same-wire commuting runs form a conservative
DAG. The resulting permutation is independently checked on every physical wire.
"""
import sys, json, heapq, time, random, hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
from scripts import aes_whole_semantic_integrate as base
from scripts.aes128_pipeline_joint_optimize import Timeline, load_component, load_mix
from qsboxopt.quantum_schedule import commutes, metrics

OUT = ROOT/'results/aes_whole_frontier_20260912'

def role(g, q):
    if g.kind == 'cx': return 'Z' if q == g.wires[0] else 'X'
    if g.kind in ('s','sdg','z'): return 'Z'
    if g.kind == 'x': return 'X'
    return None

def graph(ops, width, regions=None, wire_regions=None):
    # An edge joins all operations in adjacent noncommuting runs on each wire.
    previous = [[] for _ in range(width)]
    current = [[] for _ in range(width)]
    labels = [None]*width
    preds = []
    measures = {}
    tready=[0]*width
    for i,g in enumerate(ops):
        p = set()
        level=max(tready[q] for q in g.wires)+(g.kind in ('t','tdg'))
        for local,q in enumerate(g.wires):
            r = role(g,q)
            label=(r,level,None if regions is None else regions[i],None if wire_regions is None else wire_regions[i][local])
            if r is None or labels[q] != label:
                previous[q],current[q] = current[q],[]
                labels[q] = label
            p.update(previous[q]);current[q].append(i)
            tready[q]=level
        if g.condition is not None: p.add(measures[g.condition])
        if g.measurement is not None: measures[g.measurement] = i
        preds.append(sorted(p))
    succ = [[] for _ in ops]
    for j,ps in enumerate(preds):
        for i in ps: succ[i].append(j)
    height = [1]*len(ops)
    for i in reversed(range(len(ops))):
        if succ[i]: height[i] += max(height[j] for j in succ[i])
    return preds,succ,height

def schedule(ops, dag, timeline, seed, priority='height'):
    preds,succ,height=dag;degree=list(map(len,preds));rng=random.Random(seed)
    # Critical remaining chain first. Randomness breaks only equal heights.
    ties=[rng.random() for _ in ops] if seed else list(range(len(ops)))
    rank=[-h for h in height]
    if priority=='order':rank=list(range(len(ops)))
    elif priority.startswith('blend:'):
        alpha=float(priority.split(':')[1]);ref=Timeline(timeline.width);ref.emit_many(ops)
        rank=[-h+alpha*l for h,(l,g) in zip(height,ref.records)]
    def earliest(i):
        g=ops[i];v=max(timeline.full_ready[q] for q in g.wires)
        if g.condition is not None:v=max(v,timeline.classical[g.condition])
        return v
    ready=[(earliest(i),rank[i],ties[i],i) for i,n in enumerate(degree) if not n]
    heapq.heapify(ready);order=[]
    while ready:
        e,h,tie,i=heapq.heappop(ready)
        now=earliest(i)
        if now>e:
            heapq.heappush(ready,(now,h,tie,i));continue
        order.append(i);timeline.emit(ops[i])
        for j in succ[i]:
            degree[j]-=1
            if not degree[j]:heapq.heappush(ready,(earliest(j),rank[j],ties[j],j))
    assert len(order)==len(ops)
    return order

def verify(ops, order, width):
    assert sorted(order)==list(range(len(ops)))
    position=[0]*len(ops)
    for i,j in enumerate(order):position[j]=i
    wires=[[] for _ in range(width)]
    measures={}
    for i,g in enumerate(ops):
        for q in g.wires:wires[q].append(i)
        if g.measurement is not None:measures[g.measurement]=i
        if g.condition is not None:assert position[measures[g.condition]]<position[i]
    inversions=0
    # Independently verify every inverted same-wire pair commutes. A running
    # suffix maximum avoids checking any pair in already ordered prefixes.
    for seq in wires:
        ordered=[]
        for j in seq:
            for p,i in reversed(ordered):
                if p<position[j]:break
                assert commutes(ops[i],ops[j]),(i,j)
                inversions+=1
            import bisect
            bisect.insort(ordered,(position[j],j))
    return dict(permutation=True,all_inverted_pairs_commute=True,
                classical_dependencies_preserved=True,inverted_wire_pairs=inversions)

def main():
    OUT.mkdir(exist_ok=True);start=time.time()
    c0,im,om,tail,proof=base.load_new();_,c1,_=load_component('C1');mix,_=load_mix()
    r=base.build(c0,im,om,tail,c1,mix,width=3104,key_history_rounds=range(1,10),state_mode=1,key_mode=1,reverse_mode=0)
    ops=[g for _,g in r[0].records];cut=r[6]['gate_count'];parts=[ops[:cut],ops[cut:]]
    print('BASE',r[7],flush=True)
    dags=[graph(p,3104) for p in parts];print('DAG ready',time.time()-start,flush=True)
    rows=[];best=None
    for seed in range(8):
        t=Timeline(3104);orders=[]
        for p,dag in zip(parts,dags):
            orders.append(schedule(p,dag,t,seed))
            if len(orders)==1:fm=t.metric_dict()
        m=t.metric_dict();row=dict(seed=seed,full=m,forward=fm,DW=3104*m['full_depth']);rows.append(row)
        print('RESULT',row,flush=True)
        if m['t_depth']<=60 and (best is None or m['full_depth']<best['full']['full_depth']):
            best=row;best_orders=orders
    (OUT/'search.json').write_text(json.dumps(dict(baseline=r[7],rows=rows,best=best),indent=2))
    if best is None or best['full']['full_depth']>=r[7]['full_depth']:return
    checks=[verify(p,o,3104) for p,o in zip(parts,best_orders)]
    t=Timeline(3104)
    for p,o in zip(parts,best_orders):
        t.emit_many([p[i] for i in o])
    t.next_measurement=r[0].next_measurement
    assert metrics([g for _,g in t.records],3104)==best['full']
    exports={}
    for name,tt in [('forward',base.ar.prefix_timeline(t,cut)),('compute_uncompute',t)]:
        path=OUT/f'AES128_{name}.qasm.gz'
        meta=base.ar.write_scheduled_qasm_gz(path,tt,description='Exact commuting permutation of verified AES core; oracle comparison/phase marking excluded; no gates cross logical oracle cut.')
        meta['plain']=base.ar.materialize_gzip_text(path,path.with_suffix(''),meta['sha256_uncompressed_text']);exports[name]=meta
    source=ROOT/'results/aes_whole_semantic_20260911/whole_certificate.json'
    cert=dict(best=best,checks=checks,exports=exports,source_certificate=str(source),
              source_certificate_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
              forward_gate_cut=cut,orders=best_orders,ciphertext_view=r[1][10],
              interpretation='Compiler scheduling improvement only; unchanged AES architecture and allocation.')
    (OUT/'certificate.json').write_text(json.dumps(cert))
    print('VERIFIED',best,'seconds',time.time()-start,flush=True)

if __name__=='__main__':main()
