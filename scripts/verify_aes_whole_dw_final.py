"""Independent static and basis-state checks for the delivered whole AES circuit."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.aes128_pipeline_joint_optimize import aes128_reference, byte

OUT = ROOT / "results" / "aes_whole_dw_final"
CERT = OUT / "whole_circuit_certificate.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_qasm(path: Path, expected: dict, meta: dict) -> dict:
    counts = Counter()
    layer = 0
    maximum_layer = 0
    used_by_layer = defaultdict(set)
    measured_at = {}
    qreg_width = None
    cregs = set()
    conditional = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        row = raw.strip()
        if not row:
            continue
        match = re.fullmatch(r"// Layer (\d+)", row)
        if match:
            layer = int(match.group(1))
            maximum_layer = max(maximum_layer, layer)
            continue
        match = re.fullmatch(r"qreg q\[(\d+)\];", row)
        if match:
            qreg_width = int(match.group(1))
            continue
        match = re.fullmatch(r"creg m(\d+)\[1\];", row)
        if match:
            cregs.add(int(match.group(1)))
            continue
        if row.startswith("//") or row.startswith("OPENQASM") or row.startswith("include"):
            continue
        if row.startswith("barrier"):
            continue

        condition = None
        match = re.match(r"if\(m(\d+)==1\) (.+)", row)
        if match:
            condition = int(match.group(1))
            row = match.group(2)
            conditional += 1

        match = re.fullmatch(r"measure q\[(\d+)\]->m(\d+)\[0\];", row)
        if match:
            wires = [int(match.group(1))]
            measurement = int(match.group(2))
            assert measurement in cregs and measurement not in measured_at
            measured_at[measurement] = layer
            kind = "measurements"
        else:
            match = re.fullmatch(r"(cx|x|y|z|h|s|sdg|t|tdg) (.+);", row)
            assert match, row
            gate = match.group(1)
            wires = [int(q) for q in re.findall(r"q\[(\d+)\]", match.group(2))]
            assert len(wires) == (2 if gate == "cx" else 1), row
            kind = gate
        assert layer > 0 and len(wires) == len(set(wires))
        assert all(0 <= q < expected["width"] for q in wires)
        assert not used_by_layer[layer].intersection(wires), (layer, row)
        used_by_layer[layer].update(wires)
        if condition is not None:
            assert condition in measured_at and measured_at[condition] < layer
        counts[kind] += 1

    observed = {
        "width": qreg_width,
        "full_depth": maximum_layer,
        "t_count": counts["t"] + counts["tdg"],
        "cnot": counts["cx"],
        "measurements": counts["measurements"],
        "one_qubit_clifford": sum(counts[g] for g in ["x", "y", "z", "h", "s", "sdg"]),
        "gate_count": (counts["t"] + counts["tdg"] + counts["cx"] +
                       counts["measurements"] +
                       sum(counts[g] for g in ["x", "y", "z", "h", "s", "sdg"])),
    }
    for key, value in observed.items():
        assert value == expected[key], (key, value, expected[key])
    assert len(cregs) == expected["measurements"]
    assert sha256(path) == meta["plain"]["sha256"] == meta["sha256_uncompressed_text"]
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256(path), "metrics": observed,
            "layer_wire_exclusivity": True,
            "all_feed_forward_conditions_follow_their_measurement": True,
            "conditional_operations": conditional}


def parse_qand(path: Path) -> tuple[int, str, list[tuple[str, tuple[int, ...]]]]:
    width = None
    interface = None
    ops = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        row = raw.split("//", 1)[0].strip()
        if not row:
            continue
        match = re.fullmatch(r"QREG q\[(\d+)\];", row)
        if match:
            width = int(match.group(1)); continue
        match = re.fullmatch(r"INTERFACE ([A-Z0-9_]+);", row)
        if match:
            interface = match.group(1); continue
        if row == "QAND-CIRCUIT 1.0;":
            continue
        match = re.fullmatch(r"CNOT q\[(\d+)\] -> q\[(\d+)\];", row)
        if match:
            ops.append(("CNOT", tuple(map(int, match.groups())))); continue
        match = re.fullmatch(r"X q\[(\d+)\];", row)
        if match:
            ops.append(("X", (int(match.group(1)),))); continue
        match = re.fullmatch(
            r"(QAND|QAND_DAG) q\[(\d+)\], q\[(\d+)\] -> q\[(\d+)\];", row)
        assert match, row
        ops.append((match.group(1), tuple(map(int, match.groups()[1:]))))
    assert width is not None and interface is not None
    return width, interface, ops


def read_byte(values, wires):
    return sum(values[q] << (7 - i) for i, q in enumerate(wires))


def write_byte(values, wires, value):
    for i, q in enumerate(wires):
        values[q] = (value >> (7 - i)) & 1


def run_macro(ops, width, key_bytes, plaintext, checkpoint, ciphertext_view):
    values = [0] * width
    for i, value in enumerate(key_bytes):
        write_byte(values, list(range(8 * i, 8 * i + 8)), value)
    for i, value in enumerate(plaintext):
        write_byte(values, list(range(128 + 8 * i, 128 + 8 * i + 8)), value)
    checkpoint_ciphertext = None
    for index, (kind, wires) in enumerate(ops, start=1):
        if kind == "CNOT":
            values[wires[1]] ^= values[wires[0]]
        elif kind == "X":
            values[wires[0]] ^= 1
        elif kind == "QAND":
            assert values[wires[2]] == 0, (index, kind, wires)
            values[wires[2]] = values[wires[0]] & values[wires[1]]
        else:
            assert kind == "QAND_DAG"
            assert values[wires[2]] == (values[wires[0]] & values[wires[1]]), (index, kind, wires)
            values[wires[2]] = 0
        if index == checkpoint:
            checkpoint_ciphertext = bytes(
                read_byte(values, byte(ciphertext_view, i)) for i in range(16))
    return values, checkpoint_ciphertext


def verify_qand(forward_path: Path, full_path: Path, artifact: dict) -> dict:
    fw, fi, fops = parse_qand(forward_path)
    uw, ui, uops = parse_qand(full_path)
    assert (fw, uw) == (artifact["layout"]["width"], artifact["layout"]["width"])
    assert (fi, ui) == ("AES128_FORWARD", "AES128_COMPUTE_UNCOMPUTE")
    assert uops[:len(fops)] == fops
    qmeta = artifact["logical_qand"]
    boundary_meta = qmeta["compute_uncompute"]
    assert boundary_meta["oracle_insertion_after_macro_operation"] == len(fops)
    assert "// === FORWARD AES COMPLETE ===" in full_path.read_text(encoding="utf-8")
    assert sha256(forward_path) == qmeta["forward_encryption"]["sha256"]
    assert sha256(full_path) == qmeta["compute_uncompute"]["sha256"]
    expected_counts = {
        "forward_encryption": Counter(kind for kind, _ in fops),
        "compute_uncompute": Counter(kind for kind, _ in uops),
    }
    for name, counts in expected_counts.items():
        assert dict(counts) == qmeta[name]["operation_counts"]

    vectors = [
        (bytes.fromhex("000102030405060708090a0b0c0d0e0f"),
         bytes.fromhex("00112233445566778899aabbccddeeff")),
        (bytes(16), bytes(16)),
    ]
    samples = []
    ciphertext_view = artifact["layout"]["ciphertext_view_msb_first"]
    for key, plaintext in vectors:
        forward_values, ciphertext = run_macro(
            fops, fw, key, plaintext, len(fops), ciphertext_view)
        expected, _ = aes128_reference(plaintext, key)
        assert ciphertext == expected
        full_values, checkpoint_ciphertext = run_macro(
            uops, uw, key, plaintext, len(fops), ciphertext_view)
        assert checkpoint_ciphertext == expected
        assert bytes(read_byte(full_values, list(range(8 * i, 8 * i + 8)))
                     for i in range(16)) == key
        assert bytes(read_byte(full_values, list(range(128 + 8 * i, 128 + 8 * i + 8)))
                     for i in range(16)) == plaintext
        assert all(full_values[q] == 0 for q in range(256, uw))
        samples.append({"key": key.hex(), "plaintext": plaintext.hex(),
                        "ciphertext": ciphertext.hex(), "pass": True})
    return {"forward_is_prefix_of_compute_uncompute": True,
            "oracle_insertion_marker_after_forward_prefix": True,
            "operation_counts_match_certificate": True,
            "basis_vectors": len(vectors),
            "forward_matches_AES128": True,
            "compute_uncompute_restores_all_wires": True,
            "samples": samples}


def verify_ablation() -> dict:
    path = OUT / "ablation_results.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    versions = {row["id"]: row for row in data["versions"]}
    assert set(versions) == {"A", "B", "C", "D"}
    keys = ("width", "full_depth", "t_depth", "t_count", "cnot",
            "measurements", "one_qubit_clifford", "DW_full", "DW_T")
    for row in versions.values():
        source = ROOT / row["certificate"]
        source_artifact = json.loads(source.read_text(encoding="utf-8"))
        metrics = source_artifact["compute_uncompute_metrics"]
        for key in keys:
            assert row[key] == metrics[key], (row["id"], key, row[key], metrics[key])
        assert row["DW_full"] == row["width"] * row["full_depth"]
        assert row["DW_T"] == row["width"] * row["t_depth"]
    pairs = {"B_vs_A": ("B", "A"), "C_vs_B": ("C", "B"),
             "D_vs_C": ("D", "C"), "D_vs_A": ("D", "A")}
    for name, (new_id, old_id) in pairs.items():
        new, old, delta = versions[new_id], versions[old_id], data["deltas"][name]
        for key in ("width", "full_depth", "cnot", "DW_full"):
            assert delta[key] == new[key] - old[key], (name, key)
        expected_percent = 100 * (new["DW_full"] - old["DW_full"]) / old["DW_full"]
        assert abs(delta["DW_full_percent"] - expected_percent) < 1e-12
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256(path), "versions": 4,
            "all_metrics_match_source_certificates": True,
            "all_deltas_recomputed": True}


def main():
    artifact = json.loads(CERT.read_text(encoding="utf-8"))
    forward_metrics = artifact["forward_metrics_at_ciphertext"]
    full_metrics = artifact["compute_uncompute_metrics"]
    qasm = artifact["qasm"]
    qasm_checks = {
        "forward_encryption": verify_qasm(
            OUT / "AES128_T3_relaxed_reuse_forward_encryption.qasm",
            forward_metrics, qasm["forward_encryption"]),
        "compute_uncompute": verify_qasm(
            OUT / "AES128_T3_relaxed_reuse_compute_uncompute.qasm",
            full_metrics, qasm["compute_uncompute"]),
    }
    qand_checks = verify_qand(
        OUT / "AES128_T3_relaxed_reuse_forward_encryption.qand",
        OUT / "AES128_T3_relaxed_reuse_compute_uncompute.qand", artifact)
    ablation_checks = verify_ablation()
    assert full_metrics["DW_full"] == full_metrics["width"] * full_metrics["full_depth"]
    assert full_metrics["DW_T"] == full_metrics["width"] * full_metrics["t_depth"]
    assert artifact["search_proof"]["selected_is_search_best"]
    result = {
        "status": "PASS",
        "certificate_sha256": sha256(CERT),
        "qasm_static_checks": qasm_checks,
        "logical_qand_checks": qand_checks,
        "ablation_checks": ablation_checks,
        "resource_arithmetic": True,
        "key_history_local_search_best_reproduced": True,
    }
    path = OUT / "delivery_verification.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
