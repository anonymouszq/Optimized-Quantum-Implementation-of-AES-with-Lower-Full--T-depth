"""Bounded whole-AES allocation search with a frozen reverse-state C1 and fusion."""
from pathlib import Path
import argparse,json,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from scripts import experiment_reverse_specialized_AES_20261004b as ex
alloc=ex.alloc
OUT=ROOT/'results/reverse_specialized_AES_20261004b/allocation_search';OUT.mkdir(exist_ok=True)
SRC=ROOT/'results/reverse_sbox_specialization_20261004b/candidate_cx794_d86.json'
FUSED=ROOT/'results/fused_affine_synthesis_20261004b/candidate_d11.json'

def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=240);p.add_argument('--check-case',type=int);p.add_argument('--stage2',action='store_true');a=p.parse_args()
    setup=ex.configure(SRC,'795',FUSED)
    path=OUT/'search.json';rows=json.loads(path.read_text())['rows'] if path.exists() else []
    if a.check_case is not None:
        r=next(row for row in rows if row['case']==a.check_case)
        alloc.OUT=OUT/f'case_{a.check_case:02d}';alloc.OUT.mkdir(exist_ok=True)
        verified=alloc.evaluate(r['spec'],check=True)
        assert verified['full']==r['full']
        verified.update(case=a.check_case,setup=setup)
        (alloc.OUT/'verified_winner.json').write_text(json.dumps(verified,indent=2))
        print(json.dumps(dict(case=a.check_case,full=verified['full'],forward=verified['forward'],extended_basis_audit=verified['extended_basis_audit'],export=verified['export'])),flush=True)
        return
    base=dict(width=3040,key_first=False,mapping=2,interface='migrating',policy='tfirst',seed=0,reverse_order='ready')
    jobs=[base]
    jobs += [dict(base,mapping=m) for m in [0,1]]
    jobs += [dict(base,reverse_order=r) for r in ['natural','reverse','rows','even_odd','late']]
    jobs += [dict(base,policy=q,seed=s) for q,s in [('reverse_tie',0),('random_tie',1),('random_tie',2),('random_tie',3),('bucket4',1),('bucket8',1),('bucket16',1),('history_full',0),('weighted4',0)]]
    jobs += [dict(base,width=w) for w in [3024,3008,2992,2960,3048,3072]]
    jobs += [dict(base,key_first=True)]
    if a.stage2:
        best=dict(base,reverse_order='late')
        jobs=[dict(best,width=w) for w in [3039,3038,3036,3032,3028,3024,3008]]
        jobs += [dict(best,mapping=m) for m in [0,1]]
        jobs += [dict(best,policy=q,seed=s) for q,s in [('reverse_tie',0),('random_tie',1),('random_tie',2),('random_tie',3),('history_full',0)]]
        jobs += [dict(best,forward_order='ready'),dict(best,forward_order='rows')]
    start=time.time()
    for i,spec in enumerate(jobs):
        if time.time()-start>a.seconds:break
        if any(r['spec']==spec for r in rows):continue
        case=i+(24 if a.stage2 else 0)
        alloc.OUT=OUT/f'case_{case:02d}';alloc.OUT.mkdir(exist_ok=True)
        row=alloc.evaluate(spec);row['case']=case;row['setup']=setup
        rows.append(row);path.write_text(json.dumps(dict(rows=rows,elapsed=time.time()-start),indent=2))
        print(i,spec,row['full']['full_depth'],row['full']['t_depth'],row['full']['cnot'],flush=True)
    eligible=[r for r in rows if r['eligible']]
    best=min(eligible,key=lambda r:(r['full']['full_depth'],r['DW'],r['full']['gate_count']))
    print('BEST',best['case'],best['spec'],best['full'],flush=True)

if __name__=='__main__':main()
