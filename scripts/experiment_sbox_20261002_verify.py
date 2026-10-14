"""Independent scalar audit of the frozen C0 candidate's window replacements."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from qsboxopt.quantum_width import expand_event
from qsboxopt.quantum_cancel import verify_cancellations
from qsboxopt.quantum_schedule import metrics,verify_reordering
from verify_aes_t3_round2 import read_dynamic
from verify_aes_t3_width import verify_events,verify_three_wire
from verify_aes_t3_quantum import local_checks
from aes_t3_final_search import check_variants
OUT=ROOT/'results/sbox_optimization_20261002'

def apply(v,e):
 q=e['wires'];k=e['kind']
 if k=='cx':a,b=q;assert v[a] in (0,1) and v[b] in (0,1);v[b]^=v[a]
 elif k=='x':assert v[q[0]] in (0,1);v[q[0]]^=1
 elif k=='prep':assert v[q[0]]==0;v[q[0]]=-1
 elif k in ('and3','and4'):
  a,b,c=q[:3];assert v[a] in (0,1) and v[b] in (0,1)
  if k=='and3':assert v[c]==-1
  else:assert v[c]==0 and v[q[3]]==0
  v[c]=v[a]&v[b]
 else:a,b,c=q;assert k=='cleanup' and v[c]==v[a]&v[b];v[c]=0

def main():
 oldpath=ROOT/'results/aes_t3_semantic_third_20260911/best_certificate.json'
 newpath=OUT/'C0_candidate_certificate.json'
 old=json.loads(oldpath.read_text());new=json.loads(newpath.read_text())
 checks=[];cursor=newcursor=0
 for block in new['window_proofs']:
  start,end=block['start'],block['end']
  assert old['events'][cursor:start]==new['events'][newcursor:newcursor+start-cursor]
  newcursor+=start-cursor;replacement=new['events'][newcursor:newcursor+block['after']]
  assert all(e['kind'] in ('cx','x') for e in replacement)
  for x in range(256):
   v=[(x>>i)&1 for i in range(8)]+[0]*64
   for e in old['events'][:start]:apply(v,e)
   a,b=v[:],v[:]
   for e in old['events'][start:end]:apply(a,e)
   for e in replacement:apply(b,e)
   assert a==b,(x,start)
  checks.append({**block,'scalar_inputs_checked':256,'all_72_wires_equal':True,'only_phase_free_cnot_x':True})
  cursor=end;newcursor+=block['after']
 assert old['events'][cursor:]==new['events'][newcursor:]
 ops=[g for e in new['events'] for g in expand_event(e)]
 ops,cancel=verify_cancellations(ops,new['cancellations'])
 ordered=[ops[i] for row in new['layers'] for i in row]
 result={'blocks':checks,'untouched_events_identical':True,'source_sha256':hashlib.sha256(oldpath.read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256(newpath.read_bytes()).hexdigest(),'interface':verify_events(new['events'],72,'C0'),'schedule':verify_reordering(ops,new['layers']),'cancellations':cancel,'metrics':metrics(ordered,72),'local_gadgets':{'three_wire':verify_three_wire(),'local':local_checks(),'variants':check_variants()}}
 (OUT/'C0_candidate_independent_audit.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
