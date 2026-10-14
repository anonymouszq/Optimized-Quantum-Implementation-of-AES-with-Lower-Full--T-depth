"""Bit-sliced end-to-end basis-state audit of the delivered AES-128 circuit.

The audit evaluates thousands of plaintext/key pairs in parallel.  Every
physical wire is represented by one Python integer whose bit i is the value of
that wire in test case i.  QAND and CNOT then become ordinary bit operations,
so the exact exported logical command stream is exercised rather than a
separate reimplementation of the optimized circuit.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.aes128_pipeline_joint_optimize import aes128_reference
from scripts.verify_aes_whole_dw_final import parse_qand


ARTIFACT = ROOT / "results/aes_whole_dw_final/whole_circuit_certificate.json"
FORWARD = ROOT / "results/aes_whole_dw_final/AES128_T3_relaxed_reuse_forward_encryption.qand"
FULL = ROOT / "results/aes_whole_dw_final/AES128_T3_relaxed_reuse_compute_uncompute.qand"
OUT = ROOT / "results/aes_whole_dw_final/extended_vector_audit_20260928.json"
SEED = 20260928
RANDOM_CASES = 4096


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_cases() -> list[tuple[bytes, bytes, str]]:
    cases: list[tuple[bytes, bytes, str]] = [
        (bytes.fromhex("000102030405060708090a0b0c0d0e0f"),
         bytes.fromhex("00112233445566778899aabbccddeeff"), "nist"),
        (bytes(16), bytes(16), "zero"),
    ]
    for bit in range(128):
        p = bytearray(16); p[bit // 8] = 1 << (7 - bit % 8)
        cases.append((bytes(16), bytes(p), "walking_plaintext"))
    for bit in range(128):
        k = bytearray(16); k[bit // 8] = 1 << (7 - bit % 8)
        cases.append((bytes(k), bytes(16), "walking_key"))
    patterns = [0x00, 0x01, 0x55, 0x80, 0xAA, 0xFE, 0xFF]
    for value in patterns:
        cases.append((bytes([value]) * 16, bytes([value ^ 0xFF]) * 16,
                      "constant_pattern"))
    rng = random.Random(SEED)
    for _ in range(RANDOM_CASES):
        cases.append((rng.randbytes(16), rng.randbytes(16), "random"))
    return cases


def input_masks(width: int, cases: list[tuple[bytes, bytes, str]]) -> list[int]:
    values = [0] * width
    for case_index, (key, plaintext, _) in enumerate(cases):
        bit = 1 << case_index
        for byte_index, value in enumerate(key):
            for offset in range(8):
                if (value >> (7 - offset)) & 1:
                    values[8 * byte_index + offset] |= bit
        for byte_index, value in enumerate(plaintext):
            for offset in range(8):
                if (value >> (7 - offset)) & 1:
                    values[128 + 8 * byte_index + offset] |= bit
    return values


def execute(ops, values, checkpoint: int | None = None):
    checkpoint_values = None
    for index, (kind, wires) in enumerate(ops, start=1):
        if kind == "CNOT":
            values[wires[1]] ^= values[wires[0]]
        elif kind == "X":
            values[wires[0]] ^= (1 << CASE_COUNT) - 1
        elif kind == "QAND":
            assert values[wires[2]] == 0, (index, wires)
            values[wires[2]] = values[wires[0]] & values[wires[1]]
        else:
            assert kind == "QAND_DAG"
            assert values[wires[2]] == (values[wires[0]] & values[wires[1]]), (index, wires)
            values[wires[2]] = 0
        if checkpoint is not None and index == checkpoint:
            checkpoint_values = values.copy()
    return values, checkpoint_values


def expected_output_masks(cases):
    masks = [0] * 128
    samples = []
    for i, (key, plaintext, kind) in enumerate(cases):
        ciphertext, _ = aes128_reference(plaintext, key)
        bit = 1 << i
        for byte_index, value in enumerate(ciphertext):
            for offset in range(8):
                if (value >> (7 - offset)) & 1:
                    masks[8 * byte_index + offset] |= bit
        if i < 10:
            samples.append({"kind": kind, "key": key.hex(),
                            "plaintext": plaintext.hex(),
                            "ciphertext": ciphertext.hex()})
    return masks, samples


def assert_ciphertext(values, view, expected):
    assert len(view) == len(expected) == 128
    for i, q in enumerate(view):
        assert values[q] == expected[i], (i, q)


def main() -> None:
    global CASE_COUNT
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    fw, fi, fops = parse_qand(FORWARD)
    uw, ui, uops = parse_qand(FULL)
    assert fw == uw == artifact["layout"]["width"]
    assert fi == "AES128_FORWARD" and ui == "AES128_COMPUTE_UNCOMPUTE"
    assert uops[:len(fops)] == fops
    cases = make_cases()
    CASE_COUNT = len(cases)
    expected, samples = expected_output_masks(cases)
    view = artifact["layout"]["ciphertext_view_msb_first"]

    forward_initial = input_masks(fw, cases)
    forward_values, _ = execute(fops, forward_initial.copy())
    assert_ciphertext(forward_values, view, expected)

    full_initial = input_masks(uw, cases)
    full_values, boundary = execute(uops, full_initial.copy(), len(fops))
    assert boundary is not None
    assert_ciphertext(boundary, view, expected)
    assert full_values[:256] == full_initial[:256]
    assert all(mask == 0 for mask in full_values[256:])

    categories = {}
    for _, _, kind in cases:
        categories[kind] = categories.get(kind, 0) + 1
    result = {
        "status": "PASS",
        "method": "bit-sliced exact execution of exported QAND/CNOT/X command stream",
        "seed": SEED,
        "total_vectors": CASE_COUNT,
        "categories": categories,
        "forward_operation_count": len(fops),
        "compute_uncompute_operation_count": len(uops),
        "forward_matches_independent_AES128_reference": True,
        "ciphertext_boundary_matches_reference": True,
        "key_and_plaintext_restored": True,
        "all_ancillas_zero_after_uncompute": True,
        "forward_sha256": sha256(FORWARD),
        "compute_uncompute_sha256": sha256(FULL),
        "representative_samples": samples,
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
