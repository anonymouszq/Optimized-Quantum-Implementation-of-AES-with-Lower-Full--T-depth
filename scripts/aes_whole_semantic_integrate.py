"""Integrate semantic C0 and search role-aware zero-wire mapping plus key history."""
import sys,json,inspect,re,itertools,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import scripts.aes128_pipeline_relaxed_reuse as ar
from qsboxopt.quantum_width import expand_event
from qsboxopt.quantum_cancel import verify_cancellations
from qsboxopt.quantum_schedule import metrics,verify_reordering
from scripts.aes128_pipeline_joint_optimize import load_component,load_mix
OUT=ROOT/'results/aes_whole_semantic_20260911';OUT.mkdir(exist_ok=True)
CERT=ROOT/'results/aes_t3_semantic_iterate_20260911/best_certificate.json'
ar.C0_CERT=CERT

def load_new():
 c=json.loads(CERT.read_text());tail=[g for e in c['events'] if e.get('canonicalization') for g in expand_event(e)];assert len(tail)==13
 raw=[g for e in c['events'] for g in expand_event(e)];raw,proof=verify_cancellations(raw,c['cancellations']);verify_reordering(raw,c['layers']);assert raw[-13:]==tail
 relaxed=[raw[i] for l in c['layers'] for i in l if i<len(raw)-13]
 forms=[0]*72
 for i in range(16):forms[i]=1<<i
 for g in reversed(tail):a,b=g.wires;forms[b]^=forms[a]
 assert sorted(x for x in forms if x)==[1<<i for i in range(16)]
 imap=[forms.index(1<<i) for i in range(8)];omap=[forms.index(1<<(i+8)) for i in range(8)]
 return relaxed,imap,omap,tail,dict(metrics=metrics(relaxed,72),cancellations=proof,source_sha256=hashlib.sha256(CERT.read_bytes()).hexdigest())

def remap(wires,ops,offset,mode):
 if mode==0:return wires
 n=offset+len(wires);first=[10**9]*n;last=[0]*n
 for i,g in enumerate(ops):
  for q in g.wires:
   if q<n:first[q]=min(first[q],i)
 for g in reversed(ops):
  h=1+max(last[q] for q in g.wires)
  for q in g.wires:last[q]=h
 locals_=list(range(offset,n))
 locals_.sort(key=lambda q:(first[q],q) if mode==1 else (-last[q],first[q],q))
 result=[None]*len(wires)
 for q,w in zip(locals_,wires):result[q-offset]=w
 return result
src=inspect.getsource(ar.build_dynamic)
src=src.replace('width=2816, key_history_rounds=frozenset()):','width=2816, key_history_rounds=frozenset(), state_mode=0, key_mode=0, reverse_mode=0):')
src=src.replace('state_zero_sets = [pool.take(timeline, 64) for _ in range(16)]','state_zero_sets = [remap(pool.take(timeline,64),relaxed_c0,8,state_mode) for _ in range(16)]')
src=src.replace('key_work_sets = [pool.take(timeline, 64) for _ in range(4)]','key_work_sets = [remap(pool.take(timeline,64),c1ops,16,key_mode) for _ in range(4)]')
src=src.replace('state_work_sets = [relaxed_zero_sets[i] + borrowed_sets[i] for i in range(16)]','state_work_sets = [remap(relaxed_zero_sets[i]+borrowed_sets[i],c1ops,16,reverse_mode) for i in range(16)]')
ns=dict(vars(ar));ns['remap']=remap;exec(src,ns);build=ns['build_dynamic']

def main():
 start=time.time();c0,im,om,tail,proof=load_new();_,c1,c1proof=load_component('C1');mix,mixproof=load_mix();rows=[];best=None
 def evaluate(rounds,modes):
  nonlocal best
  rounds=frozenset(rounds);w=2816+32*len(rounds)
  r=build(c0,im,om,tail,c1,mix,width=w,key_history_rounds=rounds,state_mode=modes[0],key_mode=modes[1],reverse_mode=modes[2]);m=dict(r[7]);m['DW_full']=w*m['full_depth'];m['DW_T']=w*m['t_depth']
  row=dict(history=sorted(rounds),modes=list(modes),metrics=m,forward=r[6]);rows.append(row)
  if m['t_depth']==60 and (best is None or (m['DW_full'],m['cnot'])<(best['metrics']['DW_full'],best['metrics']['cnot'])):best=row;print('BEST',row,flush=True)
  return r
 for modes in itertools.product(range(3),repeat=3):evaluate(range(1,10),modes)
 selected=tuple(best['modes'])
 choices=[()] + [tuple(range(1,11))] + list(itertools.combinations(range(1,11),9)) + list(itertools.combinations(range(1,11),8))
 for i,rounds in enumerate(choices):
  evaluate(rounds,selected)
  if i%10==0:print('history',i,flush=True)
 (OUT/'search.json').write_text(json.dumps(dict(rows=rows,best=best,seconds=time.time()-start),indent=2))
 r=build(c0,im,om,tail,c1,mix,width=best['metrics']['width'],key_history_rounds=best['history'],state_mode=selected[0],key_mode=selected[1],reverse_mode=selected[2])
 t,states,raw,stages,poolaudit,fe,fm,full,pool,hist,qmaps,calls=r
 assert metrics([g for _,g in t.records],t.width)==full
 checks=dict(architecture=ar.simulate_architecture(t.width,im,om,tail,mix,qmaps,hist),reference=ar.verify_reference_vectors(),sbox=proof)
 fops=ar.compose_macro_program(t,calls,fm['gate_count']);allops=ar.compose_macro_program(t,calls,len(t.records));checks['macro']=ar.simulate_macro_program(allops,len(fops),t.width,states[10])
 exports={}
 for name,timeline,ops in [('forward',ar.prefix_timeline(t,fm['gate_count']),fops),('compute_uncompute',t,allops)]:
  path=OUT/f'AES128_{name}.qasm.gz';meta=ar.write_scheduled_qasm_gz(path,timeline,description='Verified AES compute core; comparison/phase mark excluded.');meta['plain']=ar.materialize_gzip_text(path,path.with_suffix(''),meta['sha256_uncompressed_text']);exports[name]=meta
  ar.write_macro_program(OUT/f'AES128_{name}.qand',t.width,'AES128_'+name.upper(),ops,states[10],insertion_after=len(fops) if name=='compute_uncompute' else None)
 artifact=dict(candidate=best,forward=fm,full=full,stages=stages,pool_audit=poolaudit,checks=checks,components=dict(C0=proof,C1=c1proof,MixColumns=mixproof),exports=exports,ciphertext_view=states[10],input_map=im,output_map=om,history=hist,calls=calls)
 (OUT/'whole_certificate.json').write_text(json.dumps(artifact,indent=2));print('FINAL',best,flush=True)
if __name__=='__main__':main()
