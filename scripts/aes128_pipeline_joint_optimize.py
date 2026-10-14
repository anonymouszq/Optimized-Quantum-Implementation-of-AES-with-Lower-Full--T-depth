"""Compose the certified T-depth-3 AES S-boxes with a depth-9 MixColumns.

The generated circuit follows the pipelined AES-128 compute/uncompute layout
used by Huang, Zhang and Lin.  The comparison operation between compute and
uncompute is intentionally excluded, matching the resource table convention
in their public ProjectQ program.

This script performs a dependency-respecting ASAP schedule over the complete
dynamic Clifford+T operation stream.  Consequently, the linear layer can
start as soon as each S-box output wire is ready; it need not wait for all
S-box cleanup operations to finish.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qsboxopt.cnot_resynthesis import verify_substitutions
from qsboxopt.quantum_cancel import verify_cancellations
from qsboxopt.quantum_schedule import Op, metrics, verify_reordering
from qsboxopt.quantum_width import expand_event
from qsboxopt.sboxes import SBOXES


SBOX_DIR = ROOT / "results" / "aes_t3_final"
MIX_PATH = ROOT / "tmp" / "pdfs" / "paper_analysis" / "aes_mixcolumn_d9_g111_tableV.json"


def load_component(interface: str) -> tuple[int, list[Op], dict]:
    assert interface in {"C0", "C1"}
    width = 72 if interface == "C0" else 80
    path = SBOX_DIR / f"AES_Sbox_{interface}_Q{width}_T3_best_certificate.json"
    cert = json.loads(path.read_text(encoding="utf-8"))
    ops = [op for event in cert["events"] for op in expand_event(event)]
    ops, cancel_before = verify_cancellations(ops, cert["cancel_before"])
    ops, substitutions = verify_substitutions(ops, cert["substitutions"])
    ops, cancel_after = verify_cancellations(ops, cert["cancel_after"])
    schedule_replay = verify_reordering(ops, cert["layers"])
    ops = [ops[i] for layer in cert["layers"] for i in layer]
    expected = {
        "C0": dict(width=72, full_depth=85, t_depth=3, t_count=168,
                   cnot=806, measurements=34, one_qubit_clifford=266,
                   gate_count=1274),
        "C1": dict(width=80, full_depth=88, t_depth=3, t_count=168,
                   cnot=821, measurements=42, one_qubit_clifford=298,
                   gate_count=1329),
    }[interface]
    got = metrics(ops, width)
    assert got == expected, (interface, got, expected)
    replay = {
        "certificate": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "cancel_before": cancel_before,
        "substitutions": substitutions,
        "cancel_after": cancel_after,
        "schedule_replay": schedule_replay,
        "metrics": got,
    }
    return width, ops, replay


def load_mix() -> tuple[list[list[tuple[int, int]]], dict]:
    data = json.loads(MIX_PATH.read_text(encoding="utf-8"))
    layers = [[(g["control"], g["target"]) for g in layer["gates"]]
              for layer in data["layers"]]
    assert len(layers) == 9
    assert sum(map(len, layers)) == 111
    for layer in layers:
        flat = [q for gate in layer for q in gate]
        assert len(flat) == len(set(flat)), "paper layer is not a matching"
    return layers, {
        "source": str(MIX_PATH.relative_to(ROOT)).replace("\\", "/"),
        "sha256": hashlib.sha256(MIX_PATH.read_bytes()).hexdigest(),
        "width": 32,
        "depth": 9,
        "cnot": 111,
        "layer_gate_counts": [len(x) for x in layers],
    }


class Timeline:
    """Online version of quantum_schedule.metrics plus a complete schedule."""

    def __init__(self, width: int):
        self.width = width
        self.full_ready = [0] * width
        self.t_ready = [0] * width
        self.classical: dict[int, int] = {}
        self.records: list[tuple[int, Op]] = []
        self.counts: Counter[str] = Counter()
        self.next_measurement = 0

    def emit(self, op: Op) -> int:
        assert op.wires and all(0 <= q < self.width for q in op.wires), op
        start = max(self.full_ready[q] for q in op.wires)
        if op.condition is not None:
            start = max(start, self.classical[op.condition])
        layer = start + 1
        tlevel = max(self.t_ready[q] for q in op.wires)
        if op.kind in {"t", "tdg"}:
            tlevel += 1
        for q in op.wires:
            self.full_ready[q] = layer
            self.t_ready[q] = tlevel
        if op.measurement is not None:
            self.classical[op.measurement] = layer
        self.records.append((layer, op))
        self.counts[op.kind] += 1
        return layer

    def emit_many(self, ops: list[Op]) -> None:
        for op in ops:
            self.emit(op)

    @property
    def full_depth(self) -> int:
        return max(self.full_ready, default=0)

    @property
    def t_depth(self) -> int:
        return max(self.t_ready, default=0)

    def metric_dict(self) -> dict:
        c = self.counts
        return {
            "width": self.width,
            "full_depth": self.full_depth,
            "t_depth": self.t_depth,
            "t_count": c["t"] + c["tdg"],
            "cnot": c["cx"],
            "measurements": c["mm"],
            "one_qubit_clifford": sum(c[k] for k in ["x", "y", "z", "h", "s", "sdg"]),
            "gate_count": sum(c.values()),
        }


@dataclass
class Layout:
    key: list[int]
    states: list[list[int]]
    work: list[list[int]]
    key_banks: int
    state_banks: int
    width: int


def make_layout(key_banks: int = 1, state_banks: int = 1) -> Layout:
    # key + eleven 128-bit state registers + twenty reusable 64-bit S-box slots
    assert key_banks >= 1 and state_banks >= 1
    key = list(range(128))
    states = [list(range(128 + 128 * i, 128 + 128 * (i + 1))) for i in range(11)]
    base = 128 + 11 * 128
    slots = 4 * key_banks + 16 * state_banks
    work = [list(range(base + 64 * i, base + 64 * (i + 1))) for i in range(slots)]
    return Layout(key=key, states=states, work=work, key_banks=key_banks,
                  state_banks=state_banks, width=base + slots * 64)


def key_work(layout: Layout, rnd: int, box: int) -> list[int]:
    bank = (rnd - 1) % layout.key_banks
    return layout.work[4 * bank + box]


def state_work(layout: Layout, rnd: int, box: int) -> list[int]:
    bank = (rnd - 1) % layout.state_banks
    offset = 4 * layout.key_banks
    return layout.work[offset + 16 * bank + box]


def byte(view: list[int], index: int) -> list[int]:
    return view[8 * index:8 * index + 8]


def shift_rows_view(view: list[int]) -> list[int]:
    """Free logical relabeling: output byte (r,c) receives input (r,c+r)."""
    out = [0] * 128
    for c in range(4):
        for r in range(4):
            src = 4 * ((c + r) % 4) + r
            dst = 4 * c + r
            out[8 * dst:8 * dst + 8] = byte(view, src)
    assert sorted(out) == sorted(view)
    return out


def map_component(timeline: Timeline, component: list[Op], local_width: int,
                  controls: list[int], targets: list[int], work: list[int]) -> None:
    assert len(controls) == len(targets) == 8
    assert len(work) >= local_width - 16
    qmap = controls + targets + work[:local_width - 16]
    mids = sorted({op.measurement for op in component if op.measurement is not None})
    mmap = {m: timeline.next_measurement + i for i, m in enumerate(mids)}
    timeline.next_measurement += len(mids)
    for op in component:
        timeline.emit(Op(
            op.kind,
            tuple(qmap[q] for q in op.wires),
            condition=None if op.condition is None else mmap[op.condition],
            measurement=None if op.measurement is None else mmap[op.measurement],
        ))


def add_round_key(timeline: Timeline, key: list[int], state: list[int]) -> None:
    for k, s in zip(key, state):
        timeline.emit(Op("cx", (k, s)))


def add_rcon(timeline: Timeline, first_word: list[int], value: int) -> None:
    # Each byte is represented MSB first.  Rcon occupies the first byte.
    for j, q in enumerate(byte(first_word, 0)):
        if value & (1 << (7 - j)):
            timeline.emit(Op("x", (q,)))


def xor_words_forward(timeline: Timeline, key: list[int]) -> None:
    for word in range(3):
        for bit in range(32):
            timeline.emit(Op("cx", (key[32 * word + bit], key[32 * (word + 1) + bit])))


def xor_words_reverse(timeline: Timeline, key: list[int]) -> None:
    for word in reversed(range(3)):
        for bit in range(32):
            timeline.emit(Op("cx", (key[32 * word + bit], key[32 * (word + 1) + bit])))


def mix_column(timeline: Timeline, column_bytes: list[list[int]],
               layers: list[list[tuple[int, int]]], inverse: bool = False) -> None:
    assert len(column_bytes) == 4 and all(len(x) == 8 for x in column_bytes)
    # Table V labels bit k least-significant first; our byte views are MSB first.
    qmap = [column_bytes[b][7 - k] for b in range(4) for k in range(8)]
    selected = list(reversed(layers)) if inverse else layers
    for layer in selected:
        gates = list(reversed(layer)) if inverse else layer
        for c, t in gates:
            timeline.emit(Op("cx", (qmap[c], qmap[t])))


def mix_state(timeline: Timeline, state: list[int], layers, inverse: bool = False) -> None:
    for column in range(4):
        bs = [byte(state, 4 * column + r) for r in range(4)]
        mix_column(timeline, bs, layers, inverse=inverse)


def component_finish_profile(component: list[Op], width: int) -> dict:
    t = Timeline(width)
    t.emit_many(component)
    return {
        "overall": t.full_depth,
        "input_ready": max(t.full_ready[:8]),
        "target_ready": max(t.full_ready[8:16]),
        "work_ready": max(t.full_ready[16:]),
        "target_wire_ready": t.full_ready[8:16],
    }


def build_pipeline(c0: tuple[int, list[Op]], c1: tuple[int, list[Op]], mix_layers,
                   key_banks: int = 1, state_banks: int = 1):
    layout = make_layout(key_banks=key_banks, state_banks=state_banks)
    timeline = Timeline(layout.width)
    width0, ops0 = c0
    width1, ops1 = c1
    rcons = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]
    state_views: list[list[int]] = [layout.states[0]]
    stages = []

    def snap(label: str, round_no: int | None = None, before: int | None = None):
        item = {"label": label, "full_depth": timeline.full_depth,
                "t_depth": timeline.t_depth, "operations": len(timeline.records)}
        if round_no is not None:
            item["round"] = round_no
        if before is not None:
            item["increment_from_previous_snapshot"] = timeline.full_depth - before
        stages.append(item)
        return timeline.full_depth

    # Forward AES computation.
    for rnd in range(1, 11):
        round_start = timeline.full_depth
        add_round_key(timeline, layout.key, state_views[rnd - 1])
        after_ark = snap("forward_after_AddRoundKey", rnd, round_start)

        # AES-128 key schedule: RotWord is absorbed into this byte mapping.
        for i in range(4):
            control_byte = 12 + ((i + 1) % 4)
            map_component(timeline, ops1, width1, byte(layout.key, control_byte),
                          byte(layout.key, i), key_work(layout, rnd, i))
        add_rcon(timeline, layout.key[:32], rcons[rnd - 1])
        xor_words_forward(timeline, layout.key)

        raw_out = layout.states[rnd]
        for i in range(16):
            map_component(timeline, ops0, width0, byte(state_views[rnd - 1], i),
                          byte(raw_out, i), state_work(layout, rnd, i))
        after_sboxes = snap("forward_after_Sboxes_and_key_schedule", rnd, after_ark)

        shifted = shift_rows_view(raw_out)
        if rnd != 10:
            mix_state(timeline, shifted, mix_layers)
        state_views.append(shifted)
        snap("forward_after_linear_layer", rnd, after_sboxes)

    add_round_key(timeline, layout.key, state_views[10])
    forward_end = snap("forward_ciphertext_ready", 10)
    forward_metrics = timeline.metric_dict()

    # The ciphertext comparison/phase-mark is excluded, as in the reference.
    add_round_key(timeline, layout.key, state_views[10])

    # Reverse computation.  C1 safely clears a nonzero S-box target; directly
    # reversing a measurement-based C0 QASM would not be a valid dynamic circuit.
    for rnd in reversed(range(1, 11)):
        reverse_start = timeline.full_depth
        if rnd != 10:
            mix_state(timeline, state_views[rnd], mix_layers, inverse=True)
        after_inverse_linear = snap("reverse_after_inverse_linear_layer", rnd, reverse_start)

        raw_out = layout.states[rnd]
        for i in range(16):
            map_component(timeline, ops1, width1, byte(state_views[rnd - 1], i),
                          byte(raw_out, i), state_work(layout, rnd, i))

        xor_words_reverse(timeline, layout.key)
        add_rcon(timeline, layout.key[:32], rcons[rnd - 1])
        for i in reversed(range(4)):
            control_byte = 12 + ((i + 1) % 4)
            map_component(timeline, ops1, width1, byte(layout.key, control_byte),
                          byte(layout.key, i), key_work(layout, rnd, i))
        after_clear = snap("reverse_after_Sboxes_and_key_schedule", rnd, after_inverse_linear)
        add_round_key(timeline, layout.key, state_views[rnd - 1])
        snap("reverse_after_AddRoundKey", rnd, after_clear)

    full_metrics = timeline.metric_dict()
    assert timeline.next_measurement == full_metrics["measurements"]
    return layout, timeline, state_views, stages, forward_end, forward_metrics, full_metrics


def xtime(x: int) -> int:
    return ((x << 1) & 0xff) ^ (0x1b if x & 0x80 else 0)


def mix_column_bytes(col: list[int]) -> list[int]:
    a, b, c, d = col
    return [xtime(a) ^ (xtime(b) ^ b) ^ c ^ d,
            a ^ xtime(b) ^ (xtime(c) ^ c) ^ d,
            a ^ b ^ xtime(c) ^ (xtime(d) ^ d),
            (xtime(a) ^ a) ^ b ^ c ^ xtime(d)]


def shift_rows_bytes(state: list[int]) -> list[int]:
    out = [0] * 16
    for c in range(4):
        for r in range(4):
            out[4 * c + r] = state[4 * ((c + r) % 4) + r]
    return out


def next_round_key(key: list[int], rcon: int) -> list[int]:
    sbox = SBOXES["AES"]
    temp = [sbox[key[13]], sbox[key[14]], sbox[key[15]], sbox[key[12]]]
    temp[0] ^= rcon
    out = [0] * 16
    for i in range(4):
        out[i] = key[i] ^ temp[i]
    for word in range(1, 4):
        for i in range(4):
            out[4 * word + i] = key[4 * word + i] ^ out[4 * (word - 1) + i]
    return out


def aes128_reference(plaintext: bytes, key_bytes: bytes) -> tuple[bytes, list[list[int]]]:
    state = list(plaintext)
    key = list(key_bytes)
    history = []
    rcons = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]
    for rnd in range(10):
        state = [x ^ y for x, y in zip(state, key)]
        key = next_round_key(key, rcons[rnd])
        state = [SBOXES["AES"][x] for x in state]
        state = shift_rows_bytes(state)
        if rnd != 9:
            mixed = []
            for col in range(4):
                mixed.extend(mix_column_bytes(state[4 * col:4 * col + 4]))
            state = mixed
        history.append(state[:])
    state = [x ^ y for x, y in zip(state, key)]
    return bytes(state), history


def verify_reference_vectors() -> dict:
    vectors = [
        ("000102030405060708090a0b0c0d0e0f",
         "00112233445566778899aabbccddeeff",
         "69c4e0d86a7b0430d8cdb78070b4c55a"),
        ("00000000000000000000000000000000",
         "00000000000000000000000000000000",
         "66e94bd4ef8a2c3b884cfa59ca342b2e"),
    ]
    rows = []
    for key, plain, expected in vectors:
        got, _ = aes128_reference(bytes.fromhex(plain), bytes.fromhex(key))
        rows.append({"key": key, "plaintext": plain, "expected": expected,
                     "computed": got.hex(), "pass": got.hex() == expected})
    assert all(x["pass"] for x in rows)
    return {"nist_and_known_answer_vectors": rows, "all_pass": True}


def write_scheduled_qasm_gz(path: Path, timeline: Timeline,
                            description: str = "AES-128 compute/uncompute; comparison/phase mark intentionally omitted.") -> dict:
    by_layer: dict[int, list[Op]] = {}
    for layer, op in timeline.records:
        by_layer.setdefault(layer, []).append(op)
    # Online scheduling guarantees one operation per wire in each layer.
    for layer, ops in by_layer.items():
        used = set()
        for op in ops:
            assert not used.intersection(op.wires), (layer, op)
            used.update(op.wires)

    h = hashlib.sha256()
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as f:
        def put(row: str):
            data = (row + "\n").encode("utf-8")
            h.update(data)
            f.write(row + "\n")

        put("OPENQASM 2.0;")
        put('include "qelib1.inc";')
        put(f"qreg q[{timeline.width}];")
        for m in range(timeline.next_measurement):
            put(f"creg m{m}[1];")
        put(f"// {description}")
        put("// The operations below are grouped by the certified ASAP full-depth layer.")
        for layer in range(1, timeline.full_depth + 1):
            put("")
            put(f"// Layer {layer}")
            for op in by_layer.get(layer, []):
                wires = ",".join(f"q[{q}]" for q in op.wires)
                if op.kind == "mm":
                    put(f"measure q[{op.wires[0]}]->m{op.measurement}[0];")
                    put(f"barrier {wires};")
                else:
                    prefix = f"if(m{op.condition}==1) " if op.condition is not None else ""
                    put(f"{prefix}{op.kind} {wires};")
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256_uncompressed_text": h.hexdigest(),
            "compressed_bytes": path.stat().st_size}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "aes_whole_dw_round1")
    ap.add_argument("--write-qasm", action="store_true")
    ap.add_argument("--key-banks", type=int, default=1,
                    help="number of four-slot C1 work banks used round-robin")
    ap.add_argument("--state-banks", type=int, default=1,
                    help="number of sixteen-slot state S-box work banks")
    ap.add_argument("--sweep-key-banks", type=int, default=0,
                    help="evaluate key-bank counts 1..N and choose minimum width*full_depth")
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    w0, c0ops, c0replay = load_component("C0")
    w1, c1ops, c1replay = load_component("C1")
    mix_layers, mix_info = load_mix()
    bank_sweep = []
    if args.sweep_key_banks:
        for kb in range(1, args.sweep_key_banks + 1):
            trial = build_pipeline((w0, c0ops), (w1, c1ops), mix_layers,
                                   key_banks=kb, state_banks=args.state_banks)
            trial_metrics = trial[-1]
            bank_sweep.append({
                "key_banks": kb,
                "state_banks": args.state_banks,
                **trial_metrics,
                "DW_full": trial_metrics["width"] * trial_metrics["full_depth"],
                "DW_T": trial_metrics["width"] * trial_metrics["t_depth"],
            })
        args.key_banks = min(bank_sweep, key=lambda x: (x["DW_full"], x["width"]))["key_banks"]
    layout, timeline, state_views, stages, forward_end, forward_metrics, full_metrics = build_pipeline(
        (w0, c0ops), (w1, c1ops), mix_layers,
        key_banks=args.key_banks, state_banks=args.state_banks)

    # Cross-check the online metric implementation against the project metric.
    flat_ops = [op for _, op in timeline.records]
    assert metrics(flat_ops, layout.width) == full_metrics
    reference = verify_reference_vectors()

    published_huang = {
        "source": "Huang-Zhang-Lin EUROCRYPT 2025 public ProjectQ Table 8",
        "width": 3156,
        "full_depth": 1782,
        "t_depth": 60,
        "t_count": 67200,
        "cnot": 353160,
        "measurements": 16800,
        "one_qubit_clifford": 119200,
    }
    full_metrics["DW_full"] = full_metrics["width"] * full_metrics["full_depth"]
    full_metrics["DW_T"] = full_metrics["width"] * full_metrics["t_depth"]
    published_huang["DW_full"] = published_huang["width"] * published_huang["full_depth"]
    published_huang["DW_T"] = published_huang["width"] * published_huang["t_depth"]

    comparison = {
        "scope": "AES-128 pipelined compute/uncompute, excluding ciphertext comparison/phase mark",
        "resource_model": "all-to-all logical wires; unit gate/measurement/feed-forward layer; ShiftRows and RotWord as wire relabeling",
        "candidate": full_metrics,
        "published_huang_2025": published_huang,
        "delta_candidate_minus_published": {
            k: full_metrics[k] - published_huang[k]
            for k in ["width", "full_depth", "t_depth", "t_count", "cnot",
                      "measurements", "one_qubit_clifford", "DW_full", "DW_T"]
        },
        "percent_change": {
            k: 100.0 * (full_metrics[k] - published_huang[k]) / published_huang[k]
            for k in ["width", "full_depth", "t_depth", "t_count", "cnot",
                      "measurements", "one_qubit_clifford", "DW_full", "DW_T"]
            if published_huang[k]
        },
    }

    artifact = {
        "name": "AES128_T3_pipeline_joint_MixColumns_d9_round1",
        "claim_status": "verified candidate; no global optimality claim",
        "layout": {
            "key": [layout.key[0], layout.key[-1]],
            "state_registers": [[x[0], x[-1]] for x in layout.states],
            "work_slots": [[x[0], x[-1]] for x in layout.work],
            "work_slot_count": len(layout.work),
            "work_slot_width": 64,
            "key_work_banks": layout.key_banks,
            "state_work_banks": layout.state_banks,
            "peak_width": layout.width,
            "output_wire_view_msb_first": state_views[10],
        },
        "interfaces": {
            "forward_state_sboxes": "160 C0 calls: |x>|0> -> |x>|S(x)>",
            "forward_key_sboxes": "40 C1 calls: |x>|y> -> |x>|y xor S(x)>",
            "reverse_state_sboxes": "160 C1 calls clear nonzero targets safely",
            "reverse_key_sboxes": "40 C1 calls reverse key expansion",
        },
        "component_replay": {"C0": c0replay, "C1": c1replay, "MixColumns": mix_info},
        "component_finish_profiles": {
            "C0": component_finish_profile(c0ops, w0),
            "C1": component_finish_profile(c1ops, w1),
        },
        "forward_metrics_at_ciphertext": forward_metrics,
        "forward_ciphertext_depth": forward_end,
        "compute_uncompute_metrics": full_metrics,
        "comparison": comparison,
        "bank_sweep": bank_sweep,
        "stages": stages,
        "verification": {
            "component_certificates_replayed": True,
            "whole_stream_online_vs_independent_metric_match": True,
            "layer_wire_exclusivity_checked_when_exported": bool(args.write_qasm),
            "aes_reference": reference,
            "mixcolumns_matrix_verification": "in source JSON generated independently from Table V",
            "dynamic_inverse_rule": "reverse uses forward C1 cleanup circuits, never text-reverses measurement-based QASM",
        },
    }
    if args.write_qasm:
        artifact["qasm"] = write_scheduled_qasm_gz(
            out / "AES128_T3_pipeline_joint_MixColumns_d9_compute_uncompute.qasm.gz", timeline)

    (out / "whole_circuit_certificate.json").write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "comparison.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    if bank_sweep:
        (out / "bank_sweep.json").write_text(
            json.dumps(bank_sweep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "out": str(out),
        "forward": forward_metrics,
        "full": full_metrics,
        "comparison": comparison["percent_change"],
        "records": len(timeline.records),
    }, indent=2))


if __name__ == "__main__":
    main()
