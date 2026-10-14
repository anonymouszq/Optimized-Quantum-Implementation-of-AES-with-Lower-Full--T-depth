"""Bounded S-box improvement search. Original certificates are read-only.

Semantic rewrites are restricted to contiguous X/CNOT event windows and
checked against all physical-line truth signatures at both boundaries.
The search adds reverse synthesis, three-control update candidates, varied
window lengths, and current-certificate scheduling priority policies.
"""
import argparse, copy, hashlib, json, random, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from qsboxopt.quantum_width import expand_event,truth_patterns
from qsboxopt.quantum_schedule import SchedulingProblem,metrics,verify_reordering,write_qasm
from qsboxopt.quantum_cancel import cancel_self_inverse
from verify_aes_t3_width import verify_events,verify_three_wire
from verify_aes_t3_quantum import local_checks
from aes_t3_final_search import check_variants
from aes128_pipeline_joint_optimize import load_component
from aes_whole_semantic_integrate import load_new
OUT=ROOT/'results/sbox_optimization_20261002'
OUT.mkdir(exist_ok=True)

def step(v,e,ones):
 k=e['kind'];q=e['wires']
 if k=='prep': assert v[q[0]]==0; v[q[0]]='magic'
 elif k in ('and3','and4'):
  a,b,c=q[:3];assert isinstance(v[a],int) and isinstance(v[b],int)
  if k=='and3':assert v[c]=='magic'
  else:assert v[c]==0 and v[q[3]]==0
  v[c]=v[a]&v[b]
 elif k=='cleanup':a,b,c=q;assert v[c]==v[a]&v[b];v[c]=0
 elif k=='cx':a,b=q;assert isinstance(v[a],int) and isinstance(v[b],int);v[b]^=v[a]
 else:assert k=='x';v[q[0]]^=ones

def synth(initial,wanted,rng,limit,ones,allow3,deadline):
 v=initial[:];out=[];pending={i for i in range(len(v)) if v[i]!=wanted[i]}
 jitter=rng.choice([0,.4,1,2,4]);zero_bias=rng.choice([0,0,8,-1])
 while pending:
  if time.time()>deadline:raise TimeoutError('semantic search deadline reached')
  opts=[]
  for t in sorted(pending):
   lookup={}
   for q,z in enumerate(v):
    if q!=t and isinstance(z,int):lookup.setdefault(z,[]).append(q)
   cand=[];delta=v[t]^wanted[t]
   for flip in (0,1):
    d=delta^(ones if flip else 0)
    if not d:cand.append(([],flip))
    cand.extend(([a],flip) for a in lookup.get(d,[]))
    # Two-control updates, including complemented ones, are compared jointly.
    for a,z in enumerate(v):
     if a==t or not isinstance(z,int):continue
     for b in lookup.get(d^z,[]):
      if a<b:cand.append(([a,b],flip))
   if not cand and allow3:
    sources=[i for i,z in enumerate(v) if i!=t and isinstance(z,int)]
    for flip in (0,1):
     d=delta^(ones if flip else 0)
     for ii,a in enumerate(sources):
      for b in sources[ii+1:]:
       for c in lookup.get(d^v[a]^v[b],[]):
        if b<c:cand.append(([a,b,c],flip))
   if cand:
    cheapest=min(len(a)+f for a,f in cand)
    a,f=rng.choice([z for z in cand if len(z[0])+z[1]==cheapest])
    opts.append((cheapest+jitter*rng.random()+(zero_bias if wanted[t]==0 else 0),t,a,f))
  if not opts:return None
  _,t,controls,flip=min(opts)
  # Commuting same-target CNOT order may influence later scheduling.
  rng.shuffle(controls)
  for a in controls:out.append({'kind':'cx','wires':[a,t],'semantic_linear':True});v[t]^=v[a]
  if flip:out.append({'kind':'x','wires':[t],'semantic_linear':True});v[t]^=ones
  assert v[t]==wanted[t];pending.remove(t)
  if len(out)>limit:return None
 assert v==wanted
 return out

def rewrite(events,typ,seed,deadline):
 w=72 if typ=='C0' else 80;n=8 if typ=='C0' else 16;ones=(1<<(1<<n))-1
 v=list(truth_patterns(n))+[0]*(w-n);out=[];proof=[];rng=random.Random(seed);i=0
 while i<len(events):
  if time.time()>deadline:raise TimeoutError('semantic search deadline reached')
  if events[i].get('canonicalization'):
   step(v,events[i],ones);out.append(events[i]);i+=1;continue
  if events[i]['kind'] not in ('cx','x'):
   step(v,events[i],ones);out.append(events[i]);i+=1;continue
  end=i
  while end<len(events) and events[end]['kind'] in ('cx','x') and not events[end].get('canonicalization'):end+=1
  lengths=sorted({min(end-i,z) for z in (3,5,7,11,17,24,40,64,128)},reverse=True)
  rng.shuffle(lengths);accepted=None
  for length in lengths:
   if length<2:continue
   wanted=v[:]
   for e in events[i:i+length]:step(wanted,e,ones)
   for attempt in range(3):
    reverse=bool(attempt%2)
    candidate=synth(wanted if reverse else v,v if reverse else wanted,rng,length-1,ones,seed%3==0,deadline)
    if candidate is not None:
     if reverse:candidate=list(reversed(candidate))
     actual=v[:]
     for e in candidate:step(actual,e,ones)
     assert actual==wanted
     accepted=(candidate,wanted,length,reverse);break
   if accepted:break
  if accepted:
   candidate,wanted,length,reverse=accepted
   proof.append({'start':i,'end':i+length,'before':length,'after':len(candidate),'reverse_synthesis':reverse,'all_wire_truth_signatures_equal':True})
   out+=candidate;v=wanted;i+=length
  else:step(v,events[i],ones);out.append(events[i]);i+=1
 return out,proof

def priority(p,seed):
 rng=random.Random(seed);rev=bool(seed%2)
 pred,succ=(p.succ,p.pred) if rev else (p.pred,p.succ)
 h=p.reverse_height if rev else p.height
 jitter=rng.choice([0,.2,.5,1,2,3,5,8]);weight=rng.choice([-.2,0,.1,.3,.7,1]);support=rng.choice([-.5,0,.5,1,2])
 bias=[rng.random()*jitter for _ in p.groups]
 indeg=[len(z) for z in pred];ready={i for i,n in enumerate(indeg) if not n};layers=[]
 while ready:
  ordered=sorted(ready,key=lambda i:(h[i]+bias[i]+weight*len(succ[i])+support*p.support[i].bit_count(),-i),reverse=True)
  selected=[];used=0
  for i in ordered:
   if not used&p.support[i]:selected.append(i);used|=p.support[i]
  layers.append([j for i in selected for j in p.groups[i]])
  for i in selected:ready.remove(i)
  for i in selected:
   for j in succ[i]:
    indeg[j]-=1
    if not indeg[j]:ready.add(j)
 return layers[::-1] if rev else layers

def schedule(ops,w,count,seed):
 p=SchedulingProblem(ops,w)
 if len(p.tgroups)!=3:return None
 best=None
 for j in range(count):
  layers=priority(p,seed+j)
  m=metrics([ops[i] for row in layers for i in row],w)
  key=(m['full_depth'],m['cnot'],len(layers),m['one_qubit_clifford'])
  if best is None or key<best[0]:best=(key,m,layers)
 return best

def save_candidate(typ,events,ops,cancellations,layers,info):
 w=72 if typ=='C0' else 80
 validation={'events':verify_events(events,w,typ),'schedule':verify_reordering(ops,layers)}
 artifact={'events':events,'cancellations':cancellations,'layers':layers,'metrics':metrics([ops[i] for row in layers for i in row],w),'validation':validation,**info}
 (OUT/f'{typ}_best_certificate.json').write_text(json.dumps(artifact,indent=2))
 (OUT/f'{typ}_best_dynamic.qasm').write_text(write_qasm(ops,w,layers,True))
 return artifact

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--seconds',type=int,default=420);ap.add_argument('--trials',type=int,default=2);ap.add_argument('--include-c1',action='store_true');args=ap.parse_args();start=time.time();records=[];history=[]
 paths={'C0':ROOT/'results/aes_t3_semantic_third_20260911/best_certificate.json','C1':ROOT/'results/aes_t3_final/AES_Sbox_C1_Q80_T3_best_certificate.json'}
 bases={k:json.loads(p.read_text()) for k,p in paths.items()}
 baseline={'C0':{k:v for k,v in bases['C0']['metrics'].items() if k!='explicit_schedule_depth'},'C1':load_component('C1')[2]['metrics'],'C0_migrating':load_new()[4]['metrics']}
 best={k:dict(baseline[k]) for k in ('C0','C1')};current={k:bases[k]['events'] for k in bases}
 result={'baseline':baseline,'source_sha256':{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()},'records':records,'history':history}
 # Current gate-stream priority search retains exact current substitutions.
 for typ in ('C0','C1'):
  w=72 if typ=='C0' else 80
  if typ=='C0':ops=[g for e in bases[typ]['events'] for g in expand_event(e)];ops,can=cancel_self_inverse(ops)
  else:_,ops,_=load_component('C1');can=None
  selected=schedule(ops,w,256,202610020)
  key,m,layers=selected;check=verify_reordering(ops,layers)
  records.append({'phase':'priority','interface':typ,'trials':256,'metrics':m,'checks':check})
  print('PRIORITY',typ,m,flush=True)
  if (m['full_depth'],m['cnot'])<(best[typ]['full_depth'],best[typ]['cnot']):
   best[typ]=m;history.append(records[-1]);artifact={'ops':[g.__dict__ for g in ops],'layers':layers,'metrics':m,'checks':check,'source':'exact loaded baseline gates; scheduling only'}
   (OUT/f'{typ}_priority_certificate.json').write_text(json.dumps(artifact,indent=2));(OUT/f'{typ}_priority_dynamic.qasm').write_text(write_qasm(ops,w,layers,True))
 for trial in range(args.trials):
  if time.time()-start>=args.seconds:break
  typ='C1' if args.include_c1 and trial%3==2 else 'C0';w=72 if typ=='C0' else 80
  try:events,proof=rewrite(current[typ],typ,202610020+trial,start+args.seconds)
  except TimeoutError:result['incomplete_trial']={'trial':trial,'interface':typ,'reason':'search deadline reached'};break
  ops=[g for e in events for g in expand_event(e)];ops,can=cancel_self_inverse(ops)
  raw=metrics(ops,w);row={'phase':'semantic','trial':trial,'interface':typ,'windows':proof,'raw_metrics':raw};records.append(row)
  if raw['t_depth']==3 and (proof or raw['cnot']<=best[typ]['cnot']):
   try:selected=schedule(ops,w,32,202610020+trial*32)
   except AssertionError:row['rejected']='T batching cycle';selected=None
   if selected:
    key,m,layers=selected;row['metrics']=m
    if (m['full_depth'],m['cnot'])<(best[typ]['full_depth'],best[typ]['cnot']):
     artifact=save_candidate(typ,events,ops,can,layers,{'trial':trial,'window_proofs':proof,'source_sha256':result['source_sha256'][typ],'source_events':current[typ]})
     best[typ]=m;current[typ]=events;history.append({'trial':trial,'interface':typ,'metrics':m});print('IMPROVED',typ,m,flush=True)
    elif m['full_depth']<=baseline[typ]['full_depth']+1 and m['cnot']<baseline[typ]['cnot']:row['tradeoff_candidate']=True
  result.update(best=best,seconds=time.time()-start,completed_semantic_trials=trial+1)
  (OUT/'search.json').write_text(json.dumps(result,indent=2))
  print('TRIAL',trial,typ,'windows',len(proof),'rawCX',raw['cnot'],'scheduled',row.get('metrics',{}).get('full_depth'),'seconds',round(time.time()-start,1),flush=True)
 result['local_gadget_checks']={'three_wire':verify_three_wire(),'local':local_checks(),'variants':check_variants()};result.update(best=best,seconds=time.time()-start)
 (OUT/'search.json').write_text(json.dumps(result,indent=2));print('DONE',best,flush=True)
if __name__=='__main__':main()
