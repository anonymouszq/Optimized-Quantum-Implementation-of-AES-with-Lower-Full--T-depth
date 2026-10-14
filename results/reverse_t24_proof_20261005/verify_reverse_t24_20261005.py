"""Independent stdlib-only verifier for a fixed reverse AES gate schedule.

Reconstructs physical-wire and classical-feedback edges, checks the commuting
permutation, constructs executable T batches, and extracts a full gate path.
Does not import the synthesis code, scheduler, or its resource counter.
"""
from collections import Counter, defaultdict
from pathlib import Path
import bisect
import gzip
import json
import re
import sys


def commute(a,b):
    if a['m'] is not None and a['m']==b['c']:return False
    if b['m'] is not None and b['m']==a['c']:return False
    if not set(a['q']) & set(b['q']):return True
    if a['k']=='mm' or b['k']=='mm':return False
    if a['k']=='cx' and b['k']=='cx':
        return a['q'][0]!=b['q'][1] and b['q'][0]!=a['q'][1]
    diag={'s','sdg','t','tdg','z'}
    if a['k']=='cx' or b['k']=='cx':
        x,y=(a,b) if a['k']=='cx' else (b,a)
        return ((y['q'][0]==x['q'][0] and y['k'] in diag) or
                (y['q'][0]==x['q'][1] and y['k']=='x'))
    return a['k']==b['k'] or a['k'] in diag and b['k'] in diag


def verify(cert):
    ops,order,width=cert['ops'],cert['order'],cert['width']
    n=len(ops)
    assert sorted(order)==list(range(n))
    pos=[0]*n
    for j,i in enumerate(order):pos[i]=j
    sequences=[[] for _ in range(width)]
    original_measure={}
    for i,g in enumerate(ops):
        assert len(g['q'])==len(set(g['q'])) and all(0<=q<width for q in g['q'])
        for q in g['q']:sequences[q].append(i)
        if g['c'] is not None:
            assert g['c'] in original_measure and pos[original_measure[g['c']]]<pos[i]
        if g['m'] is not None:
            assert g['m'] not in original_measure
            original_measure[g['m']]=i
    inversions=0
    for seq in sequences:
        seen=[]
        for i in seq:
            for p,j in reversed(seen):
                if p<pos[i]:break
                assert commute(ops[j],ops[i]),(j,i)
                inversions+=1
            bisect.insort(seen,(pos[i],i))
    # Physical-wire serialization is stronger than the optimizer's commuting
    # DAG, and certifies that no fixed physical wire is double-booked.
    preds=[None]*n
    parent=[None]*n
    dt=[0]*n
    depth=[0]*n
    last=[None]*width
    measurements={}
    feedback_stronger=0
    for i in order:
        g=ops[i]
        p={last[q] for q in g['q']} - {None}
        wire_max=max((dt[j] for j in p),default=0)
        if g['c'] is not None:
            m=measurements[g['c']]
            if dt[m]>wire_max:feedback_stronger+=1
            p.add(m)
        preds[i]=sorted(p)
        if p:
            parent[i]=max(p,key=lambda j:(dt[j],depth[j],-j))
        dt[i]=max((dt[j] for j in p),default=0)+(g['k'] in ('t','tdg'))
        depth[i]=max((depth[j] for j in p),default=0)+1
        for q in g['q']:last[q]=i
        if g['m'] is not None:measurements[g['m']]=i
    D=max(dt)
    end=max(order,key=lambda i:(dt[i],depth[i],-i))
    chain=[]
    while end is not None:
        chain.append(end);end=parent[end]
    chain.reverse()
    assert sum(ops[i]['k'] in ('t','tdg') for i in chain)==D
    # Explicit construction: zero-T prefix, then T_k followed by zero-T closure
    # at level k. Every physical and classical edge must remain ordered.
    staged=sorted(order,key=lambda i:(dt[i],0 if ops[i]['k'] in ('t','tdg') else 1,pos[i]))
    stage_pos={i:j for j,i in enumerate(staged)}
    assert all(stage_pos[p]<stage_pos[i] for i in order for p in preds[i])
    seenT=defaultdict(set)
    for i in staged:
        if ops[i]['k'] in ('t','tdg'):
            assert not seenT[dt[i]].intersection(ops[i]['q'])
            seenT[dt[i]].update(ops[i]['q'])
    # Count the ordinary layers of this *explicit* globally T-batched schedule.
    # This is not assumed equal to the separately gate-depth-oriented schedule.
    ready=[0]*width
    classical={}
    staged_layers=[0]*n
    all_groups=defaultdict(list)
    for i in staged:all_groups[dt[i],ops[i]['k'] in ('t','tdg')].append(i)
    barrier=0
    for level in range(D+1):
        group=all_groups.get((level,True),[])
        if group:
            layer=barrier+1
            for i in group:
                assert max(ready[q] for q in ops[i]['q'])<=barrier
                staged_layers[i]=layer
                for q in ops[i]['q']:ready[q]=layer
            barrier=layer
        for i in all_groups.get((level,False),[]):
            g=ops[i]
            prereq=max([barrier]+[ready[q] for q in g['q']]+([] if g['c'] is None else [classical[g['c']]]))
            layer=prereq+1
            staged_layers[i]=layer
            for q in g['q']:ready[q]=layer
            if g['m'] is not None:classical[g['m']]=layer
        barrier=max(ready)
    assert all(staged_layers[p]<staged_layers[i] for i in order for p in preds[i])
    rows=[]
    for level in range(1,D+1):
        group=all_groups[level,True]
        counts=Counter(ops[i]['tag'] for i in group)
        rows.append(dict(reverse_t_layer=level,global_t_layer=30+level,
                         t_count=len(group),distinct_physical_wires=len(seenT[level]),
                         call_counts=dict(sorted(counts.items())),
                         after_t_nonT_counts=dict(Counter(ops[i]['k'] for i in all_groups.get((level,False),[])))))
    def detail(i):
        return dict(reverse_source_index=i,source_gate_index=cert['cut']+i,
                    kind=ops[i]['k'],wires=ops[i]['q'],condition=ops[i]['c'],measurement=ops[i]['m'],
                    tag=ops[i]['tag'],local_gate_index=ops[i]['local'],reverse_t_layer=dt[i],
                    global_t_layer=dt[i]+30,reverse_gate_layer=depth[i],
                    explicit_t_batched_gate_layer=staged_layers[i],
                    predecessors=[cert['cut']+p for p in preds[i]])
    result=dict(status='PASS',width=width,reverse_gates=n,reverse_T_depth=D,
                reverse_T_count=sum(g['k'] in ('t','tdg') for g in ops),
                reverse_gate_depth=max(depth),explicit_T_batched_reverse_gate_depth=max(staged_layers),
                inverted_same_wire_pairs_verified=inversions,
                feedback_edges=sum(g['c'] is not None for g in ops),
                feedback_edges_stronger_than_wire_T_bound=feedback_stronger,
                all_quantum_and_classical_edges_checked=True,all_T_batches_wire_disjoint=True,
                explicit_T_batch_order_valid=True,critical_path_gates=len(chain),
                critical_path_T_gates=sum(ops[i]['k'] in ('t','tdg') for i in chain),
                critical_path=[detail(i) for i in chain],layers=rows,
                zero_T_prefix_counts=dict(Counter(ops[i]['k'] for i in all_groups.get((0,False),[]))))
    return result, [detail(i) for i in order], staged


def verify_qasm(cert,staged,path):
    """Parse the exported QASM; compare every instruction and honor barriers."""
    with gzip.open(path,'rt',encoding='utf-8') as f:lines=f.read().splitlines()
    qf=[0]*cert['width'];qt=qf.copy();mf={};mt={};declared=set()
    i=0;cursor=0;batches=0
    while i<len(lines):
        line=lines[i].strip();i+=1
        if not line or line.startswith(('//','OPENQASM','include','qreg')):continue
        m=re.fullmatch(r'creg m(\d+)\[1\];',line)
        if m:declared.add(int(m[1]));continue
        if line=='barrier q;':
            qf=[max(qf)]*len(qf);qt=[max(qt)]*len(qt);continue
        condition=None
        m=re.fullmatch(r'if\(m(\d+)==1\) (.+)',line)
        if m:condition=int(m[1]);line=m[2]
        m=re.fullmatch(r'measure q\[(\d+)\]->m(\d+)\[0\];',line)
        mid=None
        if m:
            measured,mid=map(int,m.groups());assert mid in declared and mid not in mf
            reservation=lines[i].strip();i+=1
            assert reservation.startswith('barrier ')
            wires=list(map(int,re.findall(r'q\[(\d+)\]',reservation)))
            assert wires[0]==measured
            kind='mm'
        else:
            m=re.fullmatch(r'(cx|x|y|z|h|s|sdg|t|tdg) (.+);',line);assert m,line
            kind=m[1];wires=list(map(int,re.findall(r'q\[(\d+)\]',m[2])))
        expected=cert['ops'][staged[cursor]]
        assert (kind,wires,condition,mid)==(expected['k'],expected['q'],expected['c'],expected['m']),cursor
        d=max(qf[q] for q in wires);t=max(qt[q] for q in wires)
        if condition is not None:d=max(d,mf[condition]);t=max(t,mt[condition])
        d+=1;t+=kind in ('t','tdg')
        for q in wires:qf[q]=d;qt[q]=t
        if mid is not None:mf[mid]=d;mt[mid]=t
        cursor+=1
    assert cursor==len(cert['ops'])
    return dict(instructions=cursor,all_instructions_match_certificate=True,
                all_global_barriers_honored=True,T_depth=max(qt),gate_depth=max(qf))


if __name__=='__main__':
    path=Path(sys.argv[1])
    with gzip.open(path,'rt',encoding='utf-8') as f:cert=json.load(f)
    result,_,staged=verify(cert)
    qasm=path.parent/'explicit_reverse_T24.qasm.gz'
    if qasm.exists():
        result['exported_QASM']=verify_qasm(cert,staged,qasm)
        assert result['exported_QASM']['T_depth']==result['reverse_T_depth']
        assert result['exported_QASM']['gate_depth']==result['explicit_T_batched_reverse_gate_depth']
    dest=path.parent/'independent_verification.json'
    dest.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('layers','critical_path')},indent=2))
