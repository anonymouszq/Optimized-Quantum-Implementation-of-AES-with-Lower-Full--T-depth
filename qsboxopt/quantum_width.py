"""Retimed temporary-AND preparation and zero-aware quantum wire allocation.

All |A> = T H |0> preparations are explicit gates in the circuit. A three-wire
AND body uses three further T gates. No magic states are supplied for free.
"""
from __future__ import annotations
import heapq
import random
from functools import lru_cache

from qsboxopt.quantum_schedule import Op


def and4(a, b, c, d):
    return [Op('h',(c,)), Op('cx',(b,d)), Op('cx',(c,a)), Op('cx',(c,b)),
            Op('cx',(a,d)), Op('tdg',(a,)), Op('tdg',(b,)), Op('t',(c,)),
            Op('t',(d,)), Op('cx',(a,d)), Op('cx',(c,b)), Op('cx',(c,a)),
            Op('cx',(b,d)), Op('h',(c,)), Op('s',(c,))]


def and3_body(a, b, c, variant='standard'):
    if variant=='fork':
        # Same phase polynomial as chain; different dependencies on the controls.
        linear=[Op('cx',(c,a)),Op('cx',(b,c)),Op('cx',(a,b))]
        return linear+[Op('tdg',(a,)),Op('t',(b,)),Op('tdg',(c,))]+linear[::-1]+[Op('h',(c,)),Op('s',(c,))]
    if variant=='chain':
        # Permute the parity destinations: (b+c, a+b+c, a+c).
        # This allows three CNOTs instead of four on each side of the T layer.
        linear=[Op('cx',(a,c)),Op('cx',(c,b)),Op('cx',(b,a))]
        return linear+[Op('tdg',(a,)),Op('t',(b,)),Op('tdg',(c,))]+linear[::-1]+[Op('h',(c,)),Op('s',(c,))]
    assert variant=='standard'
    # L maps (a,b,c) to (a+c,b+c,a+b+c), an invertible three-bit map.
    linear = [Op('cx',(a,b)), Op('cx',(c,a)), Op('cx',(b,c)), Op('cx',(a,b))]
    return linear + [Op('tdg',(a,)), Op('tdg',(b,)), Op('t',(c,))] + linear[::-1] + [Op('h',(c,)), Op('s',(c,))]


def cleanup(a, b, c, m):
    return [Op('h',(b,)), Op('h',(c,)), Op('mm',(c,a,b),measurement=m),
            Op('cx',(a,b),condition=m), Op('x',(c,),condition=m), Op('h',(b,))]


def expand_event(event):
    kind, q = event['kind'], event['wires']
    if kind == 'prep':
        return [Op('h',(q[0],)), Op('t',(q[0],))]
    if kind == 'and3':
        return and3_body(*q,variant=event.get('variant','standard'))
    if kind == 'and4':
        return and4(*q)
    if kind == 'cleanup':
        return cleanup(*q, event['measurement'])
    assert kind in {'cx', 'x'}
    return [Op(kind, tuple(q))]


@lru_cache(maxsize=None)
def truth_patterns(n_inputs):
    n = 1 << n_inputs
    return tuple(int(('1'*(1<<b)+'0'*(1<<b))*(n>>(b+1)),2) for b in range(n_inputs))


def reorder_cleanup(macros, interface, seed=0, width_bias=None):
    """Reorder only the T-free suffix, using exact disjoint/linear commutations."""
    start=1+max(i for i,(k,_) in enumerate(macros) if k=='and')
    suffix=macros[start:]
    pred=[set() for _ in suffix];succ=[set() for _ in suffix]
    def commute(left,right):
        ka,a=left;kb,b=right
        if not set(a)&set(b):return True
        if ka==kb=='cx':return a[0]!=b[1] and b[0]!=a[1]
        if ka==kb=='x':return True
        if ka=='cx' and kb=='x':return b[0]==a[1]
        if ka=='x' and kb=='cx':return a[0]==b[1]
        return False
    for j,b in enumerate(suffix):
        for i in range(j):
            if not commute(suffix[i],b):pred[j].add(i);succ[i].add(j)
    values=[0]*100;patterns=truth_patterns(16 if interface=='C1' else 8)
    ones=(1<<(1<<(16 if interface=='C1' else 8)))-1
    values[:8]=patterns[:8]
    if interface=='C1':values[76:84]=patterns[8:16]
    def update(gate):
        k,q=gate
        if k=='cx':values[q[1]]^=values[q[0]]
        elif k=='x':values[q[0]]^=ones
        elif k=='and':values[q[2]]=values[q[0]]&values[q[1]]
        else:
            assert k=='unand' and values[q[2]]==values[q[0]]&values[q[1]]
            values[q[2]]=0
    for gate in macros[:start]:update(gate)
    heights=[1]*len(suffix)
    for i in reversed(range(len(suffix))):heights[i]=1+max((heights[j] for j in succ[i]),default=0)
    indegree=[len(p) for p in pred]
    ready={i for i,d in enumerate(indegree) if not d}
    rng=random.Random(seed)
    order=[]
    while ready:
        def score(i):
            k,q=suffix[i]
            if k=='unand':delta=-int(values[q[2]]!=0)
            elif k=='cx':delta=int((values[q[0]]^values[q[1]])!=0)-int(values[q[1]]!=0)
            else:delta=int((values[q[0]]^ones)!=0)-int(values[q[0]]!=0)
            if width_bias is not None:
                return (-i-width_bias*delta+width_bias*.5*int(k=='unand'), heights[i]+(seed%5)*rng.random())
            return (-delta, int(k=='unand'), heights[i]+(seed%5)*rng.random(), -i)
        i=max(sorted(ready),key=score);ready.remove(i);order.append(i);update(suffix[i])
        for j in succ[i]:
            indegree[j]-=1
            if indegree[j]==0:ready.add(j)
    position={i:p for p,i in enumerate(order)}
    inversions=0
    for j in range(len(suffix)):
        for i in range(j):
            if position[i]>position[j]:
                assert commute(suffix[i],suffix[j]);inversions+=1
    return macros[:start]+[suffix[i] for i in order],dict(prefix_length=start,order=order,
            inverted_pairs_checked=inversions,all_swapped_macros_commute=True)


def pull_cleanup_early(macros):
    """Pull cleanup left only across disjoint gates; preserve the CNOT order."""
    start=1+max(i for i,(k,_) in enumerate(macros) if k=='and')
    suffix=macros[start:]
    order=[]
    moved=0
    for i,(kind,wires) in enumerate(suffix):
        position=len(order)
        if kind=='unand':
            selected=set(wires)
            while position and not selected.intersection(suffix[order[position-1]][1]):
                position-=1
            moved+=len(order)-position
        order.insert(position,i)
    return macros[:start]+[suffix[i] for i in order],dict(prefix_length=start,order=order,
            inverted_pairs_checked=moved,all_swapped_macros_disjoint=True)


class WidthCompiler:
    def __init__(self, macros, interface, third_targets=(), compress=True, basis_seed=0, allocation='lowest', restore_strategy='all', linear_strategy='basis', and3_variant='standard', prepared_targets=None):
        self.macros = macros
        self.interface = interface
        self.third_targets = set(third_targets)
        # ``prepared_targets`` generalizes the historical search, which fixed
        # every second-layer AND to the prepared three-wire implementation and
        # varied only eligible third-layer targets.  Keeping ``None`` preserves
        # every existing certificate byte-for-byte; an explicit iterable lets
        # the extended search choose U3/U4 independently in layers two and
        # three while retaining the same 42-AND Boolean dataflow.
        self.prepared_targets = (None if prepared_targets is None
                                 else set(prepared_targets))
        self.values = [0] * 100
        self.mapping = {}
        self.free = []
        self.width = 0
        self.events = []
        self.usage = []
        self.skipped = []
        self.compress = compress
        self.basis_seed = basis_seed
        self.compressed = {}
        self.compression_basis = set()
        self.compression_log = []
        self.allocation = allocation
        assert restore_strategy in {'all', 'needed'}
        self.restore_strategy = restore_strategy
        assert linear_strategy in {'basis','available'}
        self.linear_strategy = linear_strategy
        assert and3_variant in {'standard','chain'}
        self.and3_variant=and3_variant
        self.last_full = [0]*128
        self.last_t = [0]*128
        self.classical_time = {}
        self.ones = (1 << (1 << (16 if interface == 'C1' else 8))) - 1
        patterns = truth_patterns(16 if interface == 'C1' else 8)
        for logical in range(8):
            self.values[logical] = patterns[logical]
            self.alloc(logical)
        if interface == 'C1':
            for i in range(8):
                self.values[76 + i] = patterns[8 + i]
                self.alloc(76 + i)

    def take(self):
        if self.free:
            if self.allocation != 'lowest':
                if self.allocation == 'earliest':
                    q=min(self.free,key=lambda q:(self.last_full[q],self.last_t[q],q))
                else:
                    assert self.allocation == 't_first'
                    q=min(self.free,key=lambda q:(self.last_t[q],self.last_full[q],q))
                self.free.remove(q)
                heapq.heapify(self.free)
                return q
            return heapq.heappop(self.free)
        q = self.width
        self.width += 1
        return q

    def alloc(self, logical):
        if logical in self.compressed:
            self.restore([logical])
        if logical not in self.mapping:
            assert self.values[logical] == 0 or not self.events
            self.mapping[logical] = self.take()
        return self.mapping[logical]

    def release_zero(self, logical):
        assert self.values[logical] == 0
        if logical in self.mapping:
            heapq.heappush(self.free, self.mapping.pop(logical))

    def emit(self, kind, wires, **extra):
        if kind=='and3' and self.and3_variant!='standard':extra['variant']=self.and3_variant
        event=dict(kind=kind, wires=list(wires), **extra)
        self.events.append(event)
        for op in expand_event(event):
            full=max(self.last_full[q] for q in op.wires)
            if op.condition is not None:
                full=max(full,self.classical_time[op.condition])
            full+=1
            t=max(self.last_t[q] for q in op.wires)+(op.kind in {'t','tdg'})
            for q in op.wires:self.last_full[q],self.last_t[q]=full,t
            if op.measurement is not None:self.classical_time[op.measurement]=full

    def emit_xor_target(self, logical, expression, **extra):
        target=self.mapping[logical]
        controls=[r for r in self.mapping if r!=logical and (expression>>r)&1]
        flip=bool((expression>>100)&1)
        if self.linear_strategy=='available':
            choices=[(controls,flip)]
            live=[r for r in self.mapping if r!=logical and isinstance(self.values[r],int) and self.values[r]!=0]
            wanted=self.values[logical]
            for i,a in enumerate(live):
                value=self.values[a]
                if value==wanted:choices.append(([a],False))
                if value^self.ones==wanted:choices.append(([a],True))
                for b in live[i+1:]:
                    value2=value^self.values[b]
                    if value2==wanted:choices.append(([a,b],False))
                    if value2^self.ones==wanted:choices.append(([a,b],True))
            def score(choice):
                rows,invert=choice
                time=self.last_full[target]
                for r in sorted(rows,key=lambda r:(self.last_full[self.mapping[r]],r)):
                    time=max(time,self.last_full[self.mapping[r]])+1
                return (time+invert,len(rows)+invert,tuple(sorted(rows)))
            controls,flip=min(choices,key=score)
            controls=sorted(controls,key=lambda r:(self.last_full[self.mapping[r]],r))
        else:
            # Preserve the historical ordering for the existing compiler mode.
            controls=sorted(controls)
        value=self.ones if flip else 0
        for r in controls:value^=self.values[r]
        assert value==self.values[logical]
        for r in controls:self.emit('cx',(self.mapping[r],target),**extra)
        if flip:self.emit('x',(target,),**extra)

    def compress_linear(self, required):
        assert not self.compressed
        basis = {}
        constant = 1 << 100

        def reduce(value):
            expression = 0
            while value:
                pivot = value.bit_length() - 1
                if pivot not in basis:
                    break
                row, combination = basis[pivot]
                value ^= row
                expression ^= combination
            return value, expression

        basis[self.ones.bit_length()-1] = (self.ones, constant)
        selected = []
        order = sorted(required)
        other = [q for q in sorted(self.mapping) if q not in required and isinstance(self.values[q],int)]
        if self.basis_seed:
            random.Random(self.basis_seed).shuffle(other)
        for q in order + other:
            value = self.values[q]
            assert isinstance(value,int) and value != 0
            residual, expression = reduce(value)
            if residual:
                basis[residual.bit_length()-1] = (residual, expression ^ (1 << q))
                selected.append(q)
            elif q not in required:
                self.compressed[q] = expression
        used = 0
        for expression in self.compressed.values():
            used |= expression
        self.compression_basis = {q for q in selected if (used >> q) & 1}
        self.compression_log.append(dict(required=sorted(required), basis=selected,
                                         erased=[dict(logical=q, expression=e) for q,e in self.compressed.items()]))
        for q, expression in self.compressed.items():
            target = self.mapping[q]
            if self.linear_strategy=='basis':
                for r in selected:
                    if (expression >> r)&1:self.emit('cx',(self.mapping[r],target),compression=True)
                if expression&constant:self.emit('x',(target,),compression=True)
            else:
                self.emit_xor_target(q,expression,compression=True)
            heapq.heappush(self.free, self.mapping.pop(q))

    def restore(self, logicals=None):
        if logicals is None or self.restore_strategy == 'all':
            logicals=list(self.compressed)
        else:
            logicals=[q for q in self.compressed if q in logicals]
        for q in logicals:
            expression=self.compressed[q]
            target = self.take()
            self.mapping[q] = target
            self.emit_xor_target(q,expression,restoration=True)
            del self.compressed[q]
        used=0
        for expression in self.compressed.values():used|=expression
        self.compression_basis={q for q in self.compression_basis if (used>>q)&1}

    def restore_before(self, reads, writes):
        needed=set(reads)&self.compressed.keys()
        for q,expression in self.compressed.items():
            if any((expression>>r)&1 for r in writes):needed.add(q)
        if needed:self.restore(needed)

    def compile(self):
        all_ands = [q for k, q in self.macros if k == 'and']
        assert len(all_ands) == 42
        historical_prep = [q[2] for q in all_ands[9:30]] + sorted(self.third_targets)
        prep = historical_prep if self.prepared_targets is None else sorted(self.prepared_targets)
        for c in prep:
            assert self.values[c] == 0
            pc = self.alloc(c)
            self.values[c] = 'magic'
            self.emit('prep', (pc,), logical_target=c)
        index = 0
        stage = 0
        measurement = 0
        while index < len(self.macros):
            kind, q = self.macros[index]
            if kind == 'and':
                group = []
                while index < len(self.macros) and self.macros[index][0] == 'and':
                    group.append(self.macros[index][1])
                    index += 1
                stage += 1
                assert len(group) == [9, 21, 12][stage - 1]
                if stage == 3 and self.compress:
                    self.compress_linear({q for a,b,c,d in group for q in (a,b)})
                # Reserve every target and scratch until the whole T batch ends.
                bodies = []
                scratches = []
                for a, b, c, _ in group:
                    assert isinstance(self.values[a], int) and isinstance(self.values[b], int)
                    pa, pb = self.alloc(a), self.alloc(b)
                    pc = self.alloc(c)
                    if self.values[c] == 'magic':
                        bodies.append(('and3', (pa, pb, pc), (a, b, c)))
                    else:
                        assert self.values[c] == 0
                        pd = self.take()
                        scratches.append(pd)
                        bodies.append(('and4', (pa, pb, pc, pd), (a, b, c)))
                self.usage.append(dict(stage=stage, allocated=len(self.mapping)+len(scratches),
                                       width_so_far=self.width, three_wire=sum(k=='and3' for k,_,_ in bodies),
                                       four_wire=sum(k=='and4' for k,_,_ in bodies)))
                for body, physical, (a, b, c) in bodies:
                    self.emit(body, physical, logical=[a,b,c], stage=stage)
                    self.values[c] = self.values[a] & self.values[b]
                for pd in scratches:
                    heapq.heappush(self.free, pd)
                continue
            if kind == 'cx':
                a, b = q
                self.restore_before((a,b),(b,))
                assert isinstance(self.values[a], int) and isinstance(self.values[b], int), (index, q)
                if self.values[a] == 0:
                    self.skipped.append(dict(macro=index, control=a, target=b, reason='identically_zero_control'))
                else:
                    pa, pb = self.alloc(a), self.alloc(b)
                    self.emit('cx', (pa, pb), logical=[a,b])
                    self.values[b] ^= self.values[a]
                    if self.values[b] == 0:
                        self.release_zero(b)
            elif kind == 'x':
                c = q[0]
                self.restore_before((c,),(c,))
                assert isinstance(self.values[c], int)
                self.emit('x', (self.alloc(c),), logical=[c])
                self.values[c] ^= self.ones
                if self.values[c] == 0:
                    self.release_zero(c)
            else:
                assert kind == 'unand'
                a, b, c = q
                self.restore_before(q,(c,))
                assert self.values[c] == self.values[a] & self.values[b]
                self.emit('cleanup', (self.alloc(a), self.alloc(b), self.alloc(c)),
                          measurement=measurement, logical=[a,b,c])
                measurement += 1
                self.values[c] = 0
                self.release_zero(c)
            index += 1
        assert stage == 3
        assert not self.compressed
        outputs = list(range(76,84)) if self.interface == 'C1' else list(range(68,76))
        assert all(self.values[q] == 0 for q in range(len(self.values)) if q not in list(range(8))+outputs)
        # Restore a standard interface: inputs q[0:8], outputs/targets q[8:16].
        canonicalization = 0
        canonical_logicals = list(range(8)) + (outputs if self.interface == 'C1' else [])
        for target, logical in enumerate(canonical_logicals):
            current = self.mapping[logical]
            if current == target:
                continue
            other = next((l for l, p in self.mapping.items() if p == target), None)
            if other is None:
                self.emit('cx', (current, target), canonicalization=True)
                self.emit('cx', (target, current), canonicalization=True)
                self.free.remove(target)
                self.free.append(current)
                heapq.heapify(self.free)
                canonicalization += 2
            else:
                for a,b in [(current,target),(target,current),(current,target)]:
                    self.emit('cx', (a,b), canonicalization=True)
                self.mapping[other] = current
                canonicalization += 3
            self.mapping[logical] = target
        if self.interface == 'C0':
            # All non-input wires start at zero, so a global static relabeling
            # may choose conventional output labels without any physical SWAP.
            permutation = {q:q for q in range(8)}
            permutation.update({self.mapping[logical]:8+i for i,logical in enumerate(outputs)})
            remaining = iter(q for q in range(self.width) if q not in permutation.values())
            for q in range(self.width):
                if q not in permutation:
                    permutation[q] = next(remaining)
            for event in self.events:
                event['wires'] = [permutation[q] for q in event['wires']]
        ops = [op for event in self.events for op in expand_event(event)]
        return dict(width=self.width, events=self.events, operations=ops, stage_usage=self.usage,
                    skipped_zero_control_cnot=self.skipped, canonicalization_cnot=canonicalization,
                    initial_input_wires=list(range(8)), output_wires=list(range(8,16)),
                    preparation_count=len(prep), third_targets=sorted(self.third_targets),
                    prepared_targets=sorted(prep),
                    compression_log=self.compression_log, basis_seed=self.basis_seed)
