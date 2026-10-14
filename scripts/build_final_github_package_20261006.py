"""Create the curated, self-contained AES release directory and ZIP."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = "AES-quantum-circuits-20261006"
DEST = ROOT / "output" / NAME

RESULTS = [
    "aes_t3_semantic_iterate_20260911/best_certificate.json",
    "aes_t3_semantic_third_20260911/best_certificate.json",
    "aes_t3_semantic_third_20260911/C0_best_dynamic.qasm",
    "aes_t3_final/AES_Sbox_C0_Q72_T3_best_certificate.json",
    "aes_t3_final/AES_Sbox_C1_Q80_T3_best_certificate.json",
    "aes_t3_final/AES_Sbox_C1_Q80_T3_best_dynamic.qasm",
    "aes_t3_final/AES_Sbox_C1_Q80_T3_best_logical_qand.qand",
    "sbox_optimization_20261002/C0_candidate_certificate.json",
    "sbox_optimization_20261002/C0_candidate_dynamic.qasm",
    "sbox_optimization_20261002/C0_candidate_independent_audit.json",
    "sbox_optimization_20261002/experiment_summary.json",
    "reverse_sbox_specialization_20261004b/candidate_cx794_d86.json",
    "reverse_sbox_specialization_20261004b/candidate_cx794_d86.qasm",
    "reverse_sbox_specialization_20261004b/candidate_cx794_d86_ops.json",
    "reverse_sbox_specialization_20261004b/candidate_cx794_d86_segment_equivalence.json",
    "reverse_sbox_specialization_20261004b/frozen_manifest.json",
    "fused_affine_synthesis_20261004b/candidate_d11.json",
    "fused_affine_synthesis_20261004b/result.json",
    "ancilla_liveness_20261004/sbox_mixcolumns_affine_fusion_interface.json",
    "reverse_specialized_AES_20261004b/allocation_search/search.json",
    "reverse_specialized_AES_20261004b/allocation_search/case_07/verified_winner.json",
    "reverse_specialized_AES_20261004b/allocation_search/case_07/winner_compute_uncompute.qasm.gz",
    "reverse_specialized_AES_20261004b/allocation_search/case_07/winner_compute_uncompute.qand.gz",
    "reverse_specialized_AES_20261004b/allocation_search/case_07/independent_qasm_audit.json",
    "reverse_specialized_AES_20261004b/allocation_search/case_07/promise_audit.json",
    "reverse_specialized_AES_20261004b/allocation_search/case_07/t_critical_path.json",
    "reverse_t24_proof_20261005/reverse_gate_certificate.json.gz",
    "reverse_t24_proof_20261005/explicit_reverse_T24.qasm.gz",
    "reverse_t24_proof_20261005/independent_verification.json",
    "reverse_t24_proof_20261005/layer_summary.json",
    "reverse_t24_proof_20261005/full_critical_path.txt",
    "reverse_t24_proof_20261005/verify_reverse_t24_20261005.py",
]

SEEDS = {
    "aes_t3_final_search.py", "experiment_sbox_20261002.py",
    "experiment_sbox_20261002_verify.py", "experiment_sbox_20261002_retime.py",
    "reverse_sbox_specialization_20261004b.py",
    "fused_affine_synthesis_20261004b.py",
    "experiment_fused_AES_20261004b.py",
    "experiment_reverse_specialized_AES_20261004b.py",
    "search_reverse_specialized_allocation_20261004b.py",
    "audit_reverse_state_promise_20261004b.py",
    "audit_aes_extended_vectors_20260928.py",
    "verify_aes_t3_final.py",
}


def script_dependencies(name: str) -> set[str]:
    path = ROOT / "scripts" / name
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [part.name for part in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
            if node.module == "scripts":
                names += ["scripts." + part.name for part in node.names]
        else:
            continue
        for module in names:
            if module.startswith("scripts."):
                base = module.split(".")[1]
            else:
                base = module.split(".")[0]
            candidate = base + ".py"
            if (ROOT / "scripts" / candidate).is_file():
                found.add(candidate)
    return found


def copy(relative: str) -> None:
    source = ROOT / relative
    if not source.is_file():
        raise FileNotFoundError(source)
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main() -> None:
    # A fresh directory name prevents stale files from entering the manifest.
    if DEST.exists():
        raise SystemExit(f"Release directory already exists: {DEST}")
    DEST.mkdir(parents=True)
    for item in RESULTS:
        copy("results/" + item)
    copy("tmp/pdfs/paper_analysis/aes_mixcolumn_d9_g111_tableV.json")
    for path in sorted((ROOT / "qsboxopt").glob("*.py")):
        copy(str(path.relative_to(ROOT)))
    selected = set(SEEDS)
    todo = list(SEEDS)
    while todo:
        for dep in script_dependencies(todo.pop()):
            if dep not in selected:
                selected.add(dep)
                todo.append(dep)
    for name in sorted(selected):
        copy("scripts/" + name)
    copy("scripts/verify_final_release_20261006.py")
    copy("scripts/build_final_github_package_20261006.py")
    linear = Path(r"G:\Implementing_Linear_Layers-main (1)")
    for name in ("README.md", "result_AES_9_111.txt",
                 "sxor_depth_priority_satfix.cpp",
                 "sxor_continue_opt_perm_sat_fix.cpp"):
        src = linear / name
        if not src.is_file():
            raise FileNotFoundError(src)
        dst = DEST / "linear_layer" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    (DEST / "README.md").write_text(README, encoding="utf-8")
    (DEST / "RESULTS.md").write_text(RESULTS_MD, encoding="utf-8")
    (DEST / "requirements-research.txt").write_text(
        "# The release verifier itself uses only Python's standard library.\n"
        "numpy\n# Optional: CaDiCaL is required to rerun linear-layer SAT search.\n",
        encoding="utf-8")
    entries = {}
    for path in sorted(DEST.rglob("*")):
        if path.is_file():
            rel = path.relative_to(DEST).as_posix()
            entries[rel] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "bytes": path.stat().st_size}
    (DEST / "MANIFEST.json").write_text(json.dumps({"files": entries}, indent=2) + "\n", encoding="utf-8")
    archive = DEST.parent / (NAME + ".zip")
    if archive.exists():
        raise SystemExit(f"ZIP already exists: {archive}")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(DEST.rglob("*")):
            if path.is_file():
                z.write(path, NAME + "/" + path.relative_to(DEST).as_posix())
    print(json.dumps({"directory": str(DEST), "zip": str(archive),
                      "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                      "bytes": archive.stat().st_size,
                      "source_scripts": len(selected), "files": len(entries) + 1}, indent=2))


README = """# AES quantum-circuit release (6 October 2026)

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
"""

RESULTS_MD = """# Frozen results and accounting

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
"""


if __name__ == "__main__":
    main()
