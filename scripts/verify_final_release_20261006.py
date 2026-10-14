"""Independent, standard-library checks of the frozen AES release."""
from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def verify_manifest():
    files = load("MANIFEST.json")["files"]
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    assert actual == set(files) | {"MANIFEST.json"}, (len(actual), len(files))
    for relative, meta in files.items():
        payload = (ROOT / relative).read_bytes()
        assert len(payload) == meta["bytes"]
        assert hashlib.sha256(payload).hexdigest() == meta["sha256"], relative
    return len(files)


FULL = "results/reverse_specialized_AES_20261004b/allocation_search/case_07/"


def verify_full_qasm():
    cert = load(FULL + "verified_winner.json")
    qpath = ROOT / (FULL + "winner_compute_uncompute.qasm.gz")
    payload = gzip.decompress(qpath.read_bytes())
    assert hashlib.sha256(payload).hexdigest() == cert["export"]["sha256_uncompressed_text"]
    counts = Counter()
    used = defaultdict(set)
    W = cert["full"]["width"]
    depth = [0] * W
    tdepth = [0] * W
    measured, measured_t, declared = {}, {}, set()
    layer = 0
    max_label = 0
    qreg = None
    lines = iter(payload.decode("utf-8").splitlines())
    for raw in lines:
        row = raw.strip()
        if not row:
            continue
        m = re.fullmatch(r"// Layer (\d+)", row)
        if m:
            layer = int(m[1]); max_label = max(max_label, layer); continue
        if row.startswith(("//", "OPENQASM ", "include ")):
            continue
        m = re.fullmatch(r"qreg q\[(\d+)\];", row)
        if m:
            qreg = int(m[1]); continue
        m = re.fullmatch(r"creg m(\d+)\[1\];", row)
        if m:
            mid = int(m[1]); assert mid not in declared; declared.add(mid); continue
        condition = None
        m = re.fullmatch(r"if\(m(\d+)==1\) (.+)", row)
        if m:
            condition = int(m[1]); row = m[2]
        m = re.fullmatch(r"measure q\[(\d+)\]->m(\d+)\[0\];", row)
        mid = None
        if m:
            mid = int(m[2]); assert condition is None and mid in declared and mid not in measured
            barrier = next(lines).strip()
            assert re.fullmatch(r"barrier q\[\d+\],q\[\d+\],q\[\d+\];", barrier)
            wires = tuple(map(int, re.findall(r"q\[(\d+)\]", barrier)))
            assert wires[0] == int(m[1])
            kind = "mm"
        else:
            m = re.fullmatch(r"(cx|x|y|z|h|s|sdg|t|tdg) (.+);", row)
            assert m, row
            kind = m[1]
            wires = tuple(map(int, re.findall(r"q\[(\d+)\]", m[2])))
            assert len(wires) == (2 if kind == "cx" else 1)
        assert layer > 0 and len(wires) == len(set(wires))
        assert all(0 <= q < W for q in wires)
        assert not used[layer].intersection(wires)
        used[layer].update(wires)
        need = max(depth[q] for q in wires)
        tneed = max(tdepth[q] for q in wires)
        if condition is not None:
            assert condition in measured and measured[condition] < layer
            need = max(need, measured[condition])
            tneed = max(tneed, measured_t[condition])
        assert need + 1 == layer, (kind, wires, layer, need)
        tneed += kind in {"t", "tdg"}
        for q in wires:
            depth[q] = layer; tdepth[q] = tneed
        if mid is not None:
            measured[mid] = layer; measured_t[mid] = tneed
        counts[kind] += 1
    assert qreg == W and declared == set(measured)
    full = dict(width=W, full_depth=max(depth), t_depth=max(tdepth),
                t_count=counts["t"] + counts["tdg"], cnot=counts["cx"],
                measurements=counts["mm"],
                one_qubit_clifford=sum(counts[k] for k in ("x", "y", "z", "h", "s", "sdg")),
                gate_count=sum(counts.values()))
    assert full == cert["full"]
    assert max_label == full["full_depth"]
    assert load(FULL + "promise_audit.json")["status"] == "PASS"
    return full


def verify_full_basis():
    """Replay the distributed QAND stream on the frozen 4361 AES vectors."""
    from scripts.audit_aes_extended_vectors_20260928 import (
        make_cases, input_masks, expected_output_masks)
    cases = make_cases()
    assert len(cases) == 4361
    expected, _ = expected_output_masks(cases)
    cert = load(FULL + "verified_winner.json")
    values = input_masks(3040, cases)
    initial = values[:256]
    ones = (1 << len(cases)) - 1
    view = cert["ciphertext_view"]
    forward_checked = False
    counts = Counter()
    with gzip.open(ROOT / (FULL + "winner_compute_uncompute.qand.gz"), "rt", encoding="utf-8") as stream:
        for original in stream:
            if not forward_checked and original.startswith("// === FORWARD AES COMPLETE ==="):
                assert all(values[q] == expected[i] for i, q in enumerate(view))
                forward_checked = True
            row = original.split("//", 1)[0].strip()
            if not row or row.startswith(("QAND-CIRCUIT", "QREG", "INTERFACE")):
                continue
            m = re.fullmatch(r"CNOT q\[(\d+)\] -> q\[(\d+)\];", row)
            if m:
                a, b = map(int, m.groups()); values[b] ^= values[a]; counts["CNOT"] += 1; continue
            m = re.fullmatch(r"X q\[(\d+)\];", row)
            if m:
                values[int(m[1])] ^= ones; counts["X"] += 1; continue
            m = re.fullmatch(r"(QAND|QAND_DAG) q\[(\d+)\], q\[(\d+)\] -> q\[(\d+)\];", row)
            assert m, row
            kind = m[1]; a, b, c = map(int, m.groups()[1:])
            product = values[a] & values[b]
            if kind == "QAND":
                assert values[c] == 0
                values[c] = product
            else:
                assert values[c] == product
                values[c] = 0
            counts[kind] += 1
    assert forward_checked
    assert values[:256] == initial
    assert all(value == 0 for value in values[256:])
    frozen = load(FULL + "promise_audit.json")
    assert frozen["vectors"] == len(cases)
    return {"vectors": len(cases), "forward_matches_AES128": True,
            "inputs_restored": True, "all_work_zero": True,
            "logical_operations": sum(counts.values())}


def truth_patterns(n):
    return [sum(((v >> bit) & 1) << v for v in range(1 << n)) for bit in range(n)]


def apply_events(events, width, inputs, sbox, interface):
    n = 1 << inputs
    ones = (1 << n) - 1
    patterns = truth_patterns(inputs)
    wires = patterns + [0] * (width - inputs)
    if interface == "reverse_state":
        wires = patterns + [sum(((sbox[v] >> j) & 1) << v for v in range(n)) for j in range(8)] + [0] * (width - 16)
    for index, event in enumerate(events):
        kind, q = event["kind"], event["wires"]
        assert len(q) == len(set(q)) and all(0 <= v < width for v in q)
        if kind == "prep":
            assert wires[q[0]] == 0, index
            wires[q[0]] = "magic"
        elif kind in ("and3", "and4"):
            a, b, c = q[:3]
            assert isinstance(wires[a], int) and isinstance(wires[b], int)
            assert wires[c] == ("magic" if kind == "and3" else 0)
            if kind == "and4":
                assert wires[q[3]] == 0
            wires[c] = wires[a] & wires[b]
        elif kind == "cleanup":
            a, b, c = q
            assert wires[c] == wires[a] & wires[b], index
            wires[c] = 0
        elif kind == "cx":
            a, b = q
            assert isinstance(wires[a], int) and isinstance(wires[b], int)
            wires[b] ^= wires[a]
        elif kind == "x":
            assert isinstance(wires[q[0]], int)
            wires[q[0]] ^= ones
        else:
            raise AssertionError(kind)
    assert wires[:8] == patterns[:8]
    if interface == "reverse_state":
        assert all(v == 0 for v in wires[8:])
    else:
        for bit in range(8):
            result = sum(((sbox[v & 255] >> bit) & 1) << v for v in range(n))
            if interface == "Cxor":
                result ^= patterns[bit + 8]
            assert wires[bit + 8] == result, (interface, bit)
        assert all(v == 0 for v in wires[16:])
    return n


def verify_sboxes():
    from qsboxopt.sboxes import SBOXES
    sbox = SBOXES["AES_REV"]
    targets = [
        ("results/sbox_optimization_20261002/C0_candidate_certificate.json", 72, 8, "C0"),
        ("results/aes_t3_final/AES_Sbox_C1_Q80_T3_best_certificate.json", 80, 16, "Cxor"),
        ("results/reverse_sbox_specialization_20261004b/candidate_cx794_d86.json", 80, 8, "reverse_state"),
    ]
    return {interface: apply_events(load(path)["events"], width, inputs, sbox, interface)
            for path, width, inputs, interface in targets}


def verify_affine():
    cert = load("results/fused_affine_synthesis_20261004b/candidate_d11.json")
    assert cert["width"] == 32
    values = [0] + [1 << i for i in range(32)]
    depth = [0] * 32
    counts = Counter()
    for gate in cert["gates"]:
        kind, q = gate["kind"], gate["wires"]
        if kind == "cx":
            a, b = q
            values = [v ^ (((v >> a) & 1) << b) for v in values]
        elif kind == "x":
            (a,) = q
            values = [v ^ (1 << a) for v in values]
        else:
            raise AssertionError(kind)
        d = max(depth[i] for i in q) + 1
        for i in q:
            depth[i] = d
        counts[kind] += 1
    constant = int(cert["constant_hex"], 16)
    rows = [int(v, 16) for v in cert["matrix_rows_hex"]]
    assert values[0] == constant
    for i in range(32):
        observed = values[i + 1] ^ constant
        expected = sum(((row >> i) & 1) << j for j, row in enumerate(rows))
        assert observed == expected, i
    assert counts["cx"] == 131 and counts["x"] == 4 and max(depth) == 11
    return {"basis_checks": 33, "cnot": 131, "depth": 11}


def xtime(v):
    return ((v << 1) ^ (0x1B if v & 0x80 else 0)) & 255


def mixcolumn(value):
    a = [(value >> (8 * i)) & 255 for i in range(4)]
    out = [xtime(a[i]) ^ (xtime(a[(i + 1) % 4]) ^ a[(i + 1) % 4]) ^
           a[(i + 2) % 4] ^ a[(i + 3) % 4] for i in range(4)]
    return sum(v << (8 * i) for i, v in enumerate(out))


def verify_mixcolumns():
    lines = (ROOT / "linear_layer/result_AES_9_111.txt").read_text(encoding="utf-8").splitlines()
    gates = [(int(b), int(a)) for line in lines
             for a, b in re.findall(r"x(\d+) \^= x(\d+)", line)]
    assert len(gates) == 111
    depth = [0] * 32
    for source, target in gates:
        assert 0 <= source < 32 and 0 <= target < 32 and source != target
        d = max(depth[source], depth[target]) + 1
        depth[source] = depth[target] = d
    assert max(depth) == 9
    for i in range(32):
        value = 1 << i
        for source, target in gates:
            value ^= ((value >> source) & 1) << target
        assert value == mixcolumn(1 << i), i
    return {"basis_checks": 32, "cnot": len(gates), "depth": 9}


def verify_reverse():
    folder = ROOT / "results/reverse_t24_proof_20261005"
    spec = importlib.util.spec_from_file_location("reverse_verifier", folder / "verify_reverse_t24_20261005.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    with gzip.open(folder / "reverse_gate_certificate.json.gz", "rt", encoding="utf-8") as f:
        cert = json.load(f)
    report, _, staged = module.verify(cert)
    qasm = module.verify_qasm(cert, staged, folder / "explicit_reverse_T24.qasm.gz")
    frozen = load("results/reverse_t24_proof_20261005/independent_verification.json")
    for key in ("width", "reverse_gates", "reverse_T_depth", "reverse_T_count",
                "reverse_gate_depth", "explicit_T_batched_reverse_gate_depth",
                "critical_path_T_gates", "all_T_batches_wire_disjoint"):
        assert report[key] == frozen[key], key
    assert qasm["T_depth"] == 24
    return {"reverse_T_depth": report["reverse_T_depth"],
            "reverse_gate_depth": report["reverse_gate_depth"],
            "explicit_QASM_gate_depth": qasm["gate_depth"]}


def main():
    result = {"manifest_files": verify_manifest(),
              "full_QASM": verify_full_qasm(),
              "full_AES_basis_state_audit": verify_full_basis(),
              "S_boxes_exhaustive_inputs": verify_sboxes(),
              "fused_affine": verify_affine(),
              "AES_MixColumns": verify_mixcolumns(),
              "reverse_schedule": verify_reverse()}
    print(json.dumps({"status": "PASS", **result}, indent=2))


if __name__ == "__main__":
    main()
