# AES quantum-circuit

This archive contains the frozen AES-128 compute–uncompute circuit, component
certificates, independent audit records, source code and a release verifier.
It is ready to unpack as a GitHub repository; no third-party Huang source is
vendored. The frozen results and release verification command below are
self-contained. The original search scripts are included for provenance;
unselected historical ablations may require additional experimental inputs.

## Quick verification

Python 3.10 or later; no package installation required:

```text
python scripts/verify_final_release_20261006.py
```

This checks SHA-256 of every distributed file, independently parses the full
QASM and its feed-forward/resource schedule, exhaustively evaluates the final
S-box event circuits on their stated input domains, verifies the fused affine
map, replays the AES MixColumns CNOT witness, rechecks the 24-layer reverse
schedule, and reruns all 4361 end-to-end AES basis-state vectors directly on
the compressed logical QAND stream.

## Contents

- `results/reverse_specialized_AES_20261004b/allocation_search/case_07/`:
  final full circuit, compressed OpenQASM 2 and logical QAND stream, certificate,
  resource audit, promise audit and T critical path.
- `results/reverse_t24_proof_20261005/`: complete reverse-gate certificate,
  exported 24-T-batch QASM, independent verifier and critical path.
- `results/sbox_optimization_20261002/`,
  `results/reverse_sbox_specialization_20261004b/`,
  `results/fused_affine_synthesis_20261004b/`: final component results.
- `linear_layer/`: AES MixColumns 111-CNOT, depth-9 witness and original
  two-stage C++ search source (CaDiCaL needed only to rerun SAT search).
- `scripts/` and `qsboxopt/`: original Python generation and audit source.

To regenerate the selected allocation case after installing the research
dependencies, run the following in a copy of the repository:

```text
python scripts/search_reverse_specialized_allocation_20261004b.py --check-case 7
```

It overwrites the frozen case-07
exports and therefore changes the manifest until the package is rebuilt.

See `RESULTS.md` for counts, interfaces and verification scope. No license is
assigned by this packaging step; repository owners should choose one before
publishing third-party contributions.
