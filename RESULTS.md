# Frozen results and accounting

| Circuit / interface | Width | Gate depth | T depth | T count | CNOT | Measurements |
|---|---:|---:|---:|---:|---:|---:|
| Full AES-128 compute–uncompute | 3040 | 1305 | 54 | 67200 | 331432 | 15520 |
| Forward AES-128 | 3040 | 679 | 30 | 33600 | 164612 | 7120 |
| S-box C0 candidate, isolated clean target | 72 | 84 | 3 | 168 | 792 | 34 |
| Reverse-state S-box, promised target S(x) | 80 | 86 | 3 | 168 | 794 | 42 |
| Generic XOR-target S-box | 80 | 88 | 3 | 168 | 821 | 42 |
| Fused 32-wire affine component | 32 | 11 | 0 | 0 | 131 | 0 |

The full-circuit CNOT count is not a naive product of isolated component
counts: its data flow reuses and fuses interfaces. The isolated C0=792 result
has ordinary ASAP depth 84; its frozen explicitly aligned schedule has depth
86. Do not substitute that isolated number for every full-AES S-box call.
The reverse-state S-box uses the promise `|x>|S(x)>|0^64> -> |x>|0^8>|0^64>`
only at reverse state calls; generic key-schedule targets retain the Cxor
interface. The full circuit's reverse T depth is 24, certified by the separate
gate-level DAG proof. A hard round barrier instead yields gate depth 1320,
while T depth remains 54. The 4361-vector audit checked every reverse state
call, restored plaintext/key and zeroed all work lines on the tested inputs.

Verification scope: the independent QASM parser checks instruction-level
resources and schedule, and the component checks cover all basis inputs of
their declared interfaces. The 4361-vector result is a deterministic sampled
basis-state audit, not a full state-vector proof of the entire AES circuit.
