"""Certified cancellation of self-inverse gates across exact commutations."""
from qsboxopt.quantum_schedule import commutes


def cancel_self_inverse(operations):
    ops=list(operations);trace=[]
    while True:
        pair=None
        for i,a in enumerate(ops):
            if a.kind not in {'cx','h','x'} or a.condition is not None:continue
            for j in range(i+1,len(ops)):
                b=ops[j]
                if a==b:
                    pair=(i,j);break
                if not commutes(a,b):break
            if pair is not None:break
        if pair is None:break
        i,j=pair;trace.append(dict(first=i,second=j,kind=ops[i].kind,wires=list(ops[i].wires)))
        ops=[op for k,op in enumerate(ops) if k not in pair]
    return ops,trace


def verify_cancellations(operations,trace):
    ops=list(operations)
    for item in trace:
        i,j=item['first'],item['second'];a=ops[i]
        assert 0<=i<j<len(ops)
        assert a==ops[j] and a.condition is None and a.kind in {'cx','h','x'}
        assert a.kind==item['kind'] and list(a.wires)==item['wires']
        assert all(commutes(a,b) for b in ops[i+1:j])
        ops=[op for k,op in enumerate(ops) if k not in (i,j)]
    return ops,dict(cancelled_pairs=len(trace),removed_gates=2*len(trace),exact_commuting_cancellation=True)
