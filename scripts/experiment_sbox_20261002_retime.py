"""Retiming the four third-layer U3 preparation T gates between T batches 1/2."""
import itertools,json,sys,time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from qsboxopt.quantum_width import expand_event
from qsboxopt.quantum_schedule import commutes,metrics,verify_reordering,write_qasm
from experiment_sbox_20261002 import priority
OUT=ROOT/'results/sbox_optimization_20261002'

def problem(ops,batches):
 p=SimpleNamespace(groups=[],tgroups=set())
 group_of=[];tgroups={}
 for i,g in enumerate(ops):
  if g.kind in ('t','tdg'):
   t=batches[i]
   if t not in tgroups:tgroups[t]=len(p.groups);p.groups.append([])
   group=tgroups[t];p.groups[group].append(i)
  else:group=len(p.groups);p.groups.append([i])
  group_of.append(group)
 p.tgroups=set(tgroups.values());p.support=[sum(1<<q for q in {q for i in z for q in ops[i].wires}) for z in p.groups]
 p.succ=[set() for z in p.groups];p.pred=[set() for z in p.groups]
 for j,b in enumerate(ops):
  for i in range(j):
   if not commutes(ops[i],b):
    a,c=group_of[i],group_of[j]
    if a==c:return None
    p.succ[a].add(c);p.pred[c].add(a)
 indeg=[len(x) for x in p.pred];ready=[i for i,n in enumerate(indeg) if not n];topo=[]
 while ready:
  i=ready.pop();topo.append(i)
  for j in p.succ[i]:
   indeg[j]-=1
   if not indeg[j]:ready.append(j)
 if len(topo)!=len(p.groups):return None
 p.height=[1]*len(p.groups);p.reverse_height=p.height[:]
 for i in reversed(topo):p.height[i]=1+max((p.height[j] for j in p.succ[i]),default=0)
 for i in topo:p.reverse_height[i]=1+max((p.reverse_height[j] for j in p.pred[i]),default=0)
 return p

def main():
 start=time.time();c=json.loads((OUT/'C0_candidate_certificate.json').read_text());assert not c['cancellations']
 ops=[];event_ids=[]
 for eidx,e in enumerate(c['events']):
  z=expand_event(e);ops+=z;event_ids += [eidx]*len(z)
 tlevels=[0]*72;batches={};prep={};eligible=[]
 for i,g in enumerate(ops):
  t=max(tlevels[q] for q in g.wires)+(g.kind in ('t','tdg'))
  for q in g.wires:tlevels[q]=t
  if g.kind in ('t','tdg'):
   batches[i]=t;e=c['events'][event_ids[i]]
   if e['kind']=='prep':prep[e['wires'][0]]=i
   if e['kind']=='and3' and t==3:
    q=e['wires'][2]
    if prep[q] not in eligible:eligible.append(prep[q])
 assert len(eligible)==4,eligible
 rows=[];bestkey=(c['metrics']['full_depth'],len(c['layers']));winner=None
 for mask in range(16):
  bs=dict(batches)
  for k,i in enumerate(eligible):
   if mask>>k&1:bs[i]=2
  p=problem(ops,bs)
  if p is None:rows.append({'mask':mask,'feasible':False});continue
  best=None
  for seed in range(128):
   layers=priority(p,202610200+seed);m=metrics([ops[i] for row in layers for i in row],72);key=(m['full_depth'],len(layers))
   if best is None or key<best[0]:best=(key,m,layers)
  key,m,layers=best;row={'mask':mask,'metrics':m,'explicit_layers':len(layers)};rows.append(row)
  if key<bestkey:
   checks=verify_reordering(ops,layers);bestkey=key;winner={**c,'layers':layers,'metrics':m,'retimed_preparation_ops':[i for k,i in enumerate(eligible) if mask>>k&1],'retiming_checks':checks}
   (OUT/'C0_retimed_certificate.json').write_text(json.dumps(winner,indent=2));(OUT/'C0_retimed_dynamic.qasm').write_text(write_qasm(ops,72,layers,True))
  print('RETIME',row,flush=True)
 (OUT/'retiming_search.json').write_text(json.dumps({'rows':rows,'eligible':eligible,'improved':winner is not None,'seconds':time.time()-start},indent=2))
if __name__=='__main__':main()
