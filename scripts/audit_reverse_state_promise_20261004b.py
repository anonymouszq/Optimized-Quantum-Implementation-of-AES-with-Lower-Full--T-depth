"""Check the target=S(input) promise at every physical reverse-state S-box call."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from scripts import experiment_reverse_specialized_AES_20261004b as ex
from scripts import audit_aes_extended_vectors_20260928 as audit
from qsboxopt.sboxes import SBOXES
alloc=ex.alloc
OUT=ROOT/'results/reverse_specialized_AES_20261004b/allocation_search/case_07'
SRC=ROOT/'results/reverse_sbox_specialization_20261004b/candidate_cx794_d86.json'
FUSED=ROOT/'results/fused_affine_synthesis_20261004b/candidate_d11.json'

def expected_byte(bits,allones):
    output=[0]*8
    for value in range(256):
        mask=allones
        for i,q in enumerate(bits):mask&=q if (value>>i)&1 else allones^q
        if not mask:continue
        sv=SBOXES['AES_REV'][value]
        for j in range(8):
            if (sv>>j)&1:output[j]|=mask
    return output

def main():
    ex.configure(SRC,'795',FUSED)
    spec=dict(width=3040,key_first=False,mapping=2,interface='migrating',policy='tfirst',seed=0,reverse_order='late')
    r=alloc.build({k:v for k,v in spec.items() if k not in ('policy','seed')},spec['policy'],spec['seed'])
    timeline=r['timeline'];raw=[g for _,g in timeline.records]
    expected_hash=hashlib.sha256('\n'.join(repr(g) for g in raw).encode()).hexdigest()
    cert=json.loads((OUT/'verified_winner.json').read_text());assert expected_hash==cert['source_gate_stream_sha256']
    alloc.sw.install_macros();program=alloc.sw.ar.compose_macro_program(timeline,r['calls'],len(raw))
    calls={c['tag']:c for c in r['calls'] if c['component']=='C1_reverse_state'}
    assert len(calls)==160
    cases=audit.make_cases();audit.CASE_COUNT=len(cases);allones=(1<<len(cases))-1
    initial=audit.input_masks(spec['width'],cases);v=initial.copy()
    current=None;input_before=None;counts={i:0 for i in range(1,11)}
    def finish():
        if current is None:return
        q=calls[current]['qmap']
        assert [v[k] for k in q[:8]]==input_before,current
        assert all(v[k]==0 for k in q[8:]),current
    for i,op in enumerate(program):
        tag=op.get('tag') if op['component']=='C1_reverse_state' else None
        if tag!=current:
            finish();current=tag
            if current is not None:
                q=calls[current]['qmap'];input_before=[v[k] for k in q[:8]]
                assert all(v[k]==0 for k in q[16:]),current
                assert [v[k] for k in q[8:16]]==expected_byte(input_before,allones),current
                rnd=int(current.split('_round_')[1].split('_')[0]);counts[rnd]+=1
        kind=op['kind'];w=op['wires']
        if kind=='CNOT':v[w[1]]^=v[w[0]]
        elif kind=='X':v[w[0]]^=allones
        elif kind=='QAND':
            assert v[w[2]]==0,(i,w)
            v[w[2]]=v[w[0]]&v[w[1]]
        else:
            assert kind=='QAND_DAG' and v[w[2]]==v[w[0]]&v[w[1]],(i,w)
            v[w[2]]=0
    finish()
    assert all(n==16 for n in counts.values())
    assert v[:256]==initial[:256] and all(z==0 for z in v[256:])
    result=dict(status='PASS',vectors=len(cases),random_vectors=audit.RANDOM_CASES,
       reverse_state_calls=160,call_case_checks=160*len(cases),calls_per_round=counts,
       all_call_targets_equal_S_of_input=True,all_64_scratch_zero_at_entry=True,
       all_inputs_preserved_and_target_scratch_zero_at_exit=True,
       complete_core_restores_key_plaintext_and_work=True,
       source_gate_stream_sha256=expected_hash,
       candidate_certificate_sha256=hashlib.sha256(SRC.read_bytes()).hexdigest())
    (OUT/'promise_audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)

if __name__=='__main__':main()
