"""Canonical byte interfaces with independent, dynamically reused scratch.

No forward scratch identity is required by reverse computation. W controls the
available parallelism; full T depth is measured, not forced to 60.
"""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from scripts.aes_whole_commuting_frontier import base,graph,schedule,verify,Timeline,load_component,load_mix
from qsboxopt.quantum_schedule import Op,metrics
OUT=ROOT/'results/aes_streaming_workspace_20260912';OUT.mkdir(exist_ok=True)
ar=base.ar

def install_macros():
 old=ar._macro_component_events()
 old['C0_canonical']=json.loads(base.CERT.read_text())['events']
 ar._macro_component_events=lambda:old

def build(width=2816,key_first=True,histories=tuple(range(1,10)),mapping=1,interface='canonical'):
 c0,im,om,tail,_=base.load_new()
 if interface=='canonical':c0=c0+tail
 else:assert interface=='migrating'
 _,c1,_=load_component('C1');mix,_=load_mix()
 t=Timeline(width);pool=ar.ZeroPool(range(256,width));calls=[];audit=[]
 key=list(range(128));states=[list(range(128,256))];hist=[None]*11
 rcons=[1,2,4,8,16,32,64,128,27,54]
 def emit(component,ops,controls,targets,offset,tag):
  work=base.remap(pool.take(t,72-offset if component=='C0_canonical' else 80-offset),ops,offset,mapping)
  qm=controls+targets+work;assert len(set(qm))==len(qm)
  mids=sorted({g.measurement for g in ops if g.measurement is not None})
  mm={m:t.next_measurement+i for i,m in enumerate(mids)};t.next_measurement+=len(mids)
  start=len(t.records)
  for g in ops:t.emit(Op(g.kind,tuple(qm[q] for q in g.wires),None if g.condition is None else mm[g.condition],None if g.measurement is None else mm[g.measurement]))
  calls.append(dict(start=start,end=len(t.records),component=component,tag=tag,qmap=qm))
  pool.give(work)
 def keys(rnd,inverse):
  if inverse:ar.xor_words_reverse(t,key);ar.add_rcon(t,key[:32],rcons[rnd-1])
  for i in (reversed(range(4)) if inverse else range(4)):
   source=(i+1)%4
   ctrl=ar.byte(key,12+source) if hist[rnd] is None else hist[rnd][8*source:8*source+8]
   emit('C1',c1,ctrl,ar.byte(key,i),16,f'{"reverse" if inverse else "forward"}_key_round_{rnd}_byte_{i}')
  if not inverse:ar.add_rcon(t,key[:32],rcons[rnd-1]);ar.xor_words_forward(t,key)
  elif hist[rnd] is not None:
   for a,b in zip(key[96:],hist[rnd]):t.emit(Op('cx',(a,b)))
   pool.give(hist[rnd])
 for rnd in range(1,11):
  ar.add_round_key(t,key,states[-1])
  if rnd in histories:
   hist[rnd]=pool.take(t,32)
   for a,b in zip(key[96:],hist[rnd]):t.emit(Op('cx',(a,b)))
  raw=pool.take(t,128) if interface=='canonical' else [None]*128
  if key_first:keys(rnd,False)
  for i in range(16):
   if interface=='canonical':emit('C0_canonical',c0,ar.byte(states[-1],i),ar.byte(raw,i),16,f'forward_state_round_{rnd}_byte_{i}')
   else:
    zeros=base.remap(pool.take(t,64),c0,8,mapping)
    ni,no,z=ar.map_relaxed_c0(t,c0,ar.byte(states[-1],i),zeros,im,om,call_log=calls,tag=f'forward_state_round_{rnd}_byte_{i}')
    states[-1][8*i:8*i+8]=ni;raw[8*i:8*i+8]=no;pool.give(z)
  if not key_first:keys(rnd,False)
  shifted=ar.shift_rows_view(raw)
  if rnd!=10:ar.mix_state(t,shifted,mix)
  states.append(shifted)
  audit.append(dict(phase='forward',round=rnd,free=len(pool.wires),depth=t.full_depth))
 ar.add_round_key(t,key,states[10]);cut=len(t.records);forward=t.metric_dict()
 ar.add_round_key(t,key,states[10])
 for rnd in reversed(range(1,11)):
  if rnd!=10:ar.mix_state(t,states[rnd],mix,inverse=True)
  raw=ar.unshift_rows_view(states[rnd])
  if key_first:keys(rnd,True)
  for i in range(16):
   targets=ar.byte(raw,i)
   emit('C1',c1,ar.byte(states[rnd-1],i),targets,16,f'reverse_state_round_{rnd}_byte_{i}')
   pool.give(targets)
  if not key_first:keys(rnd,True)
  ar.add_round_key(t,key,states[rnd-1])
  audit.append(dict(phase='reverse',round=rnd,free=len(pool.wires),depth=t.full_depth))
 restoration=0
 for i in range(128):
  src=states[0][i];dst=128+i
  if src==dst:continue
  other=states[0].index(dst) if dst in states[0] else None
  for a,b in [(src,dst),(dst,src),(src,dst)]:t.emit(Op('cx',(a,b)));restoration+=1
  states[0][i]=dst
  if other is not None:states[0][other]=src
  else:pool.reserve([dst]);pool.give([src])
 assert pool.wires==set(range(256,width))
 return dict(timeline=t,cut=cut,forward=forward,states=states,calls=calls,audit=audit,pool=pool,restoration_cnot=restoration)

def evaluate(config,check=False):
 r=build(**config);raw=[g for _,g in r['timeline'].records];cut=r['cut'];t=Timeline(config['width']);orders=[]
 for part in [raw[:cut],raw[cut:]]:
  orders.append(schedule(part,graph(part,t.width),t,0))
  if len(orders)==1:fm=t.metric_dict()
 row=dict(config=config,forward=fm,full=t.metric_dict(),DW=t.width*t.full_depth,pool_minimum=r['pool'].minimum_size,restoration_cnot=r['restoration_cnot'])
 if check:
  install_macros();f=ar.compose_macro_program(r['timeline'],r['calls'],cut);a=ar.compose_macro_program(r['timeline'],r['calls'],len(raw))
  row['macro_checks']=ar.simulate_macro_program(a,len(f),t.width,r['states'][10])
 return row,r,t,orders

def main():
 rows=[]
 widths=[int(x) for x in sys.argv[1].split(',')] if len(sys.argv)>1 else [3104,2976,2848,2720,2592,2464,2336,2208,2080,1952]
 for w in widths:
  for first in [True,False]:
   config=dict(width=w,key_first=first,mapping=1,interface=sys.argv[2] if len(sys.argv)>2 else 'canonical')
   row,_,_,_=evaluate(config,check=True);rows.append(row);print(row,flush=True)
   (OUT/('search_'+config['interface']+'_'+str(widths[0])+'.json')).write_text(json.dumps(rows,indent=2))

if __name__=='__main__':main()
