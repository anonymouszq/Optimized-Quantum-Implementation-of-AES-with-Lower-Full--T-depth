"""Compositional correctness and exact-reordering certificate for AES T3.

Locally verify QAND and measurement cleanup including phases/Kraus amplitudes;
then exhaustively check logical macro preconditions, AES outputs and clean
ancillas. This avoids an infeasible 2**97 state-vector simulation.
"""
from __future__ import annotations
import itertools
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qsboxopt.quantum_schedule import Op, read_author_qasm, commutes, verify_reordering
from qsboxopt.sboxes import SBOXES


def step(v, op, outcome=None):
    n = len(v)
    out = np.zeros(n, dtype=complex)
    if op.condition is not None and outcome == 0:
        return v.copy()
    if op.kind == 'mm':
        for i, a in enumerate(v):
            if ((i >> op.wires[0]) & 1) == outcome:
                out[i] = a
        return out
    if op.kind == 'cx':
        c, t = op.wires
        for i, a in enumerate(v):
            out[i ^ (((i >> c) & 1) << t)] += a
        return out
    q = op.wires[0]
    if op.kind == 'h':
        for i, a in enumerate(v):
            out[i & ~(1 << q)] += a / np.sqrt(2)
            out[i | (1 << q)] += a * (-1 if (i >> q) & 1 else 1) / np.sqrt(2)
        return out
    if op.kind == 'x':
        for i, a in enumerate(v):
            out[i ^ (1 << q)] = a
        return out
    if op.kind == 'y':
        for i, a in enumerate(v):
            out[i ^ (1 << q)] = a * (-1j if (i >> q) & 1 else 1j)
        return out
    phase = {'s':1j, 'sdg':-1j, 't':np.exp(1j*np.pi/4),
             'tdg':np.exp(-1j*np.pi/4), 'z':-1}[op.kind]
    return np.array([a * (phase if (i >> q) & 1 else 1) for i, a in enumerate(v)])


def qand(a, b, c, d):
    return [Op('h',(c,)), Op('cx',(b,d)), Op('cx',(c,a)), Op('cx',(c,b)),
            Op('cx',(a,d)), Op('tdg',(a,)), Op('tdg',(b,)), Op('t',(c,)),
            Op('t',(d,)), Op('cx',(a,d)), Op('cx',(c,b)), Op('cx',(c,a)),
            Op('cx',(b,d)), Op('h',(c,)), Op('s',(c,))]


def unand(a, b, c, m):
    return [Op('h',(b,)), Op('h',(c,)), Op('mm',(c,a,b),measurement=m),
            Op('cx',(a,b),condition=m), Op('x',(c,),condition=m), Op('h',(b,))]


def local_checks():
    max_error = 0.0
    for a, b in itertools.product([0,1], repeat=2):
        init = a | (b << 1)
        v = np.eye(16,dtype=complex)[:,init]
        for op in qand(0,1,2,3):
            v = step(v,op)
        expected = np.eye(16,dtype=complex)[:,init | ((a & b) << 2)]
        max_error = max(max_error, float(np.max(np.abs(v-expected))))
        for m in [0,1]:
            v = expected.copy()
            for op in unand(0,1,2,0):
                v = step(v,op,m)
            expected_out = np.eye(16,dtype=complex)[:,init] / np.sqrt(2)
            max_error = max(max_error,float(np.max(np.abs(v-expected_out))))
    assert max_error < 1e-12
    # Independently test all allowed overlapping unitary commutations on 3 qubits.
    ops = [Op(k,(q,)) for k in ['x','y','z','h','s','sdg','t','tdg'] for q in range(3)]
    ops += [Op('cx',(a,b)) for a in range(3) for b in range(3) if a != b]
    matrices = [np.column_stack([step(np.eye(8,dtype=complex)[:,i],op) for i in range(8)]) for op in ops]
    checked = 0
    for i,a in enumerate(ops):
        for j,b in enumerate(ops):
            if commutes(a,b):
                assert np.allclose(matrices[i] @ matrices[j],matrices[j] @ matrices[i],atol=1e-12)
                checked += 1
    return dict(qand_isometry_and_cleanup_kraus_error=max_error,
                unitary_commutation_pairs_numerically_checked=checked)


def macro_parse(ops):
    macros, i = [], 0
    while i < len(ops):
        op=ops[i]
        if op.kind in {'cx','x'} and op.condition is None:
            macros.append((op.kind,op.wires)); i += 1
        elif op.kind == 'h' and ops[i+1].kind == 'cx':
            c=op.wires[0]; b,d=ops[i+1].wires; cc,a=ops[i+2].wires
            assert cc==c and len({a,b,c,d})==4
            assert ops[i:i+15]==qand(a,b,c,d)
            macros.append(('and',(a,b,c,d))); i += 15
        elif op.kind == 'h' and ops[i+1].kind == 'h':
            b=op.wires[0]; c=ops[i+1].wires[0]; mm=ops[i+2]
            assert mm.kind=='mm'; a=mm.wires[1]
            assert ops[i:i+6]==unand(a,b,c,mm.measurement)
            macros.append(('unand',(a,b,c))); i += 6
        else:
            raise AssertionError((i,op))
    return macros


def pattern_bit(bit, n):
    b = bytearray((n+7)//8)
    for i in range(n):
        if (i>>bit)&1:
            b[i//8] |= 1 << (i%8)
    return int.from_bytes(b,'little')


def truth_bit(fn, bit, n):
    b=bytearray((n+7)//8)
    for i in range(n):
        if (fn(i)>>bit)&1:
            b[i//8] |= 1 << (i%8)
    return int.from_bytes(b,'little')


def exhaustive_macro_check(macros,width,typ):
    # Infer output wires from the C0 evaluation, and then test arbitrary targets.
    def simulate(n, y_wires):
        ones=(1<<n)-1
        wires=[0]*width
        for bit in range(8):
            wires[bit]=pattern_bit(bit,n)
        for bit,q in enumerate(y_wires):
            wires[q]=pattern_bit(8+bit,n)
        for kind,qs in macros:
            if kind=='cx':
                a,b=qs; wires[b]^=wires[a]
            elif kind=='x':
                wires[qs[0]]^=ones
            elif kind=='and':
                a,b,c,d=qs
                assert wires[c]==0 and wires[d]==0, ('QAND precondition',qs)
                wires[c]=wires[a]&wires[b]
            else:
                a,b,c=qs
                assert wires[c]==(wires[a]&wires[b]), ('uncompute precondition',qs)
                wires[c]=0
        return wires
    wires=simulate(256,[])
    outputs=[]
    for bit in range(8):
        truth=truth_bit(lambda x:SBOXES['AES_REV'][x],bit,256)
        match=[q for q,v in enumerate(wires) if v==truth]
        assert len(match)==1,(bit,match)
        outputs.append(match[0])
    n=65536 if typ=='C1' else 256
    wires=simulate(n,outputs if typ=='C1' else [])
    for bit,q in enumerate(outputs):
        expected=truth_bit(lambda x:SBOXES['AES_REV'][x&255] ^ ((x>>8) if typ=='C1' else 0),bit,n)
        assert wires[q]==expected
    for bit in range(8):
        assert wires[bit]==pattern_bit(bit,n)
    garbage=[q for q in range(width) if q not in list(range(8))+outputs]
    assert all(wires[q]==0 for q in garbage)
    return dict(input_order='q[0] is AES most significant input bit',output_wires_msb_first=outputs,
                exhaustive_inputs=n, aes_correct=True, input_preserved=True,
                all_other_qubits_zero=True, macro_preconditions_verified=True,
                forward_qand=sum(k=='and' for k,_ in macros),
                cleanup_qand=sum(k=='unand' for k,_ in macros))


def main():
    result={'local':local_checks(),'circuits':[]}
    for typ in ['C0','C1']:
        p=ROOT/f'external/Minimal_T-depth_Width/Resource_Estimator/CliffordT_quantum_circuit/AES_T3_{typ}_CliffordT.qasm'
        width,ops=read_author_qasm(p.read_text())
        macros=macro_parse(ops)
        check=exhaustive_macro_check(macros,width,typ)
        layers=json.loads((ROOT/f'results/aes_t3_quantum/AES_T3_{typ}_schedule.json').read_text())
        result['circuits'].append(dict(interface=typ,baseline=check,
                                      reordering=verify_reordering(ops,layers)))
    (ROOT/'results/aes_t3_quantum/verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
