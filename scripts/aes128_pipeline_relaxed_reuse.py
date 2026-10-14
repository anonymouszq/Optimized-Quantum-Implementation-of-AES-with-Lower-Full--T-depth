"""Whole-AES scheduling with a noncanonical C0 interface and zero-wire reuse.

The low-width C0 S-box spends 13 final CNOTs returning eight input bits to
their conventional physical positions.  A pipelined reversible AES does not
need those positions to stay fixed: the old round state is retained solely so
that the circuit can later uncompute it.  This script removes that final
linear permutation, records where every logical bit moved, and allocates the
zero wires of later S-box calls from a global lifetime-aware pool.

The base pool is the 2,560 initially-zero wires in the 2,816-wire layout.
Selected 32-bit key-history words may be added only when their depth saving
reduces the requested width-times-full-depth objective.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qsboxopt.cnot_resynthesis import verify_substitutions
from qsboxopt.quantum_cancel import verify_cancellations
from qsboxopt.quantum_schedule import Op, metrics, verify_reordering
from qsboxopt.quantum_width import expand_event
from qsboxopt.sboxes import SBOXES
from scripts.aes128_pipeline_joint_optimize import (
    Timeline, add_rcon, add_round_key, aes128_reference, byte,
    load_component, load_mix, mix_state, shift_rows_view,
    verify_reference_vectors, write_scheduled_qasm_gz, xor_words_forward,
    xor_words_reverse,
)


C0_CERT = ROOT / "results" / "aes_t3_final" / "AES_Sbox_C0_Q72_T3_best_certificate.json"


def ready_profile(ops: list[Op], width: int) -> list[int]:
    t = Timeline(width)
    t.emit_many(ops)
    return t.full_ready


def load_relaxed_c0() -> tuple[list[Op], list[int], list[int], list[Op], dict]:
    cert = json.loads(C0_CERT.read_text(encoding="utf-8"))
    canonical_events = [e for e in cert["events"] if e.get("canonicalization")]
    assert canonical_events and cert["events"][-len(canonical_events):] == canonical_events
    canonical_ops = [op for e in canonical_events for op in expand_event(e)]
    assert len(canonical_ops) == 13 and all(op.kind == "cx" for op in canonical_ops)

    raw = [op for event in cert["events"] for op in expand_event(event)]
    raw, cb = verify_cancellations(raw, cert["cancel_before"])
    raw, sub = verify_substitutions(raw, cert["substitutions"])
    raw, ca = verify_cancellations(raw, cert["cancel_after"])
    full_schedule_proof = verify_reordering(raw, cert["layers"])
    canonical_start = len(raw) - len(canonical_ops)
    assert raw[canonical_start:] == canonical_ops
    relaxed = [raw[i] for layer in cert["layers"] for i in layer if i < canonical_start]

    # Start from the certified conventional final interface, and apply the
    # inverse of the removed CNOT tail to derive the relaxed live-wire map.
    forms = [0] * 72
    for i in range(8):
        forms[i] = 1 << i                 # retained input bit i
        forms[8 + i] = 1 << (8 + i)       # AES output bit i (MSB first)
    for op in reversed(canonical_ops):
        c, t = op.wires
        forms[t] ^= forms[c]
    nonzero = [(q, f) for q, f in enumerate(forms) if f]
    assert len(nonzero) == 16
    assert sorted(f for _, f in nonzero) == [1 << i for i in range(16)]
    input_map = [next(q for q, f in nonzero if f == 1 << i) for i in range(8)]
    output_map = [next(q for q, f in nonzero if f == 1 << (8 + i)) for i in range(8)]
    assert len(set(input_map + output_map)) == 16

    # Filtering operations from a certified schedule preserves every relative
    # order among the remaining operations.  The removed tail is itself the
    # exact map used above.
    m = metrics(relaxed, 72)
    assert m == {"width": 72, "full_depth": 84, "t_depth": 3,
                 "t_count": 168, "cnot": 793, "measurements": 34,
                 "one_qubit_clifford": 266, "gate_count": 1261}
    ready = ready_profile(relaxed, 72)
    proof = {
        "source_certificate": str(C0_CERT.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": hashlib.sha256(C0_CERT.read_bytes()).hexdigest(),
        "full_certificate_replayed": {"cancel_before": cb, "substitutions": sub,
                                        "cancel_after": ca, "schedule": full_schedule_proof},
        "removed_tail": {
            "kind": "CNOT-only interface canonicalization",
            "cnot": len(canonical_ops),
            "operations": [{"control": op.wires[0], "target": op.wires[1]}
                           for op in canonical_ops],
            "inverse_symbolic_map_is_16_distinct_basis_values": True,
        },
        "relaxed_interface": {
            "initial_input_local_wires": list(range(8)),
            "final_input_local_wires_msb_first": input_map,
            "final_output_local_wires_msb_first": output_map,
            "final_zero_local_wires": [q for q, f in enumerate(forms) if not f],
            "input_and_output_disjoint": True,
        },
        "metrics": m,
        "finish": {
            "input_ready": max(ready[q] for q in input_map),
            "output_ready": max(ready[q] for q in output_map),
            "zero_pool_ready": max(ready[q] for q, f in enumerate(forms) if not f),
            "input_ready_vector": [ready[q] for q in input_map],
            "output_ready_vector": [ready[q] for q in output_map],
        },
        "equivalence_argument": (
            "The complete C0 certificate implements (x,0)->(x,S(x),0). "
            "Removing its final 13-CNOT linear tail implements the inverse-tail "
            "wire placement calculated exactly above; all 56 other wires remain zero."
        ),
    }
    return relaxed, input_map, output_map, canonical_ops, proof


class ZeroPool:
    def __init__(self, wires):
        self.wires = set(wires)
        self.minimum_size = len(self.wires)
        self.allocations = 0
        self.max_selected_ready = 0

    def take(self, timeline: Timeline, n: int) -> list[int]:
        assert len(self.wires) >= n, (len(self.wires), n)
        # Earliest reusable zeros first.  T readiness breaks ties because a
        # zero selected for a T-carrying gadget should not raise its T level.
        chosen = sorted(self.wires,
                        key=lambda q: (timeline.full_ready[q], timeline.t_ready[q], q))[:n]
        self.wires.difference_update(chosen)
        self.minimum_size = min(self.minimum_size, len(self.wires))
        self.allocations += n
        self.max_selected_ready = max(self.max_selected_ready,
                                      max((timeline.full_ready[q] for q in chosen), default=0))
        return chosen

    def give(self, wires) -> None:
        wires = list(wires)
        assert not self.wires.intersection(wires)
        self.wires.update(wires)

    def reserve(self, wires) -> list[int]:
        wires = list(wires)
        assert len(wires) == len(set(wires))
        assert set(wires) <= self.wires
        self.wires.difference_update(wires)
        self.minimum_size = min(self.minimum_size, len(self.wires))
        self.allocations += len(wires)
        return wires


def map_fixed_component(timeline: Timeline, component: list[Op], controls: list[int],
                        targets: list[int], work: list[int], *, call_log=None,
                        tag: str = "C1") -> None:
    qmap = controls + targets + work
    assert len(qmap) == 80 and len(set(qmap)) == 80
    start = len(timeline.records)
    mids = sorted({op.measurement for op in component if op.measurement is not None})
    mmap = {m: timeline.next_measurement + i for i, m in enumerate(mids)}
    timeline.next_measurement += len(mids)
    for op in component:
        timeline.emit(Op(op.kind, tuple(qmap[q] for q in op.wires),
                         None if op.condition is None else mmap[op.condition],
                         None if op.measurement is None else mmap[op.measurement]))
    if call_log is not None:
        call_log.append({"start": start, "end": len(timeline.records),
                         "component": "C1", "tag": tag, "qmap": qmap})


def map_relaxed_c0(timeline: Timeline, component: list[Op], controls: list[int],
                   zeros: list[int], input_map: list[int], output_map: list[int],
                   *, call_log=None, tag: str = "C0_relaxed"):
    assert len(controls) == 8 and len(zeros) == 64
    qmap = controls + zeros
    assert len(set(qmap)) == 72
    start = len(timeline.records)
    mids = sorted({op.measurement for op in component if op.measurement is not None})
    mmap = {m: timeline.next_measurement + i for i, m in enumerate(mids)}
    timeline.next_measurement += len(mids)
    for op in component:
        timeline.emit(Op(op.kind, tuple(qmap[q] for q in op.wires),
                         None if op.condition is None else mmap[op.condition],
                         None if op.measurement is None else mmap[op.measurement]))
    if call_log is not None:
        call_log.append({"start": start, "end": len(timeline.records),
                         "component": "C0_relaxed", "tag": tag, "qmap": qmap})
    new_input = [qmap[q] for q in input_map]
    new_output = [qmap[q] for q in output_map]
    live = set(new_input + new_output)
    returned_zero = [q for q in qmap if q not in live]
    assert len(live) == 16 and len(returned_zero) == 56
    return new_input, new_output, returned_zero


def unshift_rows_view(shifted: list[int]) -> list[int]:
    raw = [0] * 128
    for c in range(4):
        for r in range(4):
            src = 4 * ((c + r) % 4) + r
            dst = 4 * c + r
            raw[8 * src:8 * src + 8] = byte(shifted, dst)
    assert shift_rows_view(raw) == shifted
    return raw


def _read_byte(values: list[int], wires: list[int]) -> int:
    assert len(wires) == 8
    return sum(values[q] << (7 - i) for i, q in enumerate(wires))


def _write_byte(values: list[int], wires: list[int], value: int) -> None:
    assert len(wires) == 8
    for i, q in enumerate(wires):
        values[q] = (value >> (7 - i)) & 1


def _sim_mix(values: list[int], state: list[int], layers, inverse=False) -> None:
    for column in range(4):
        bs = [byte(state, 4 * column + r) for r in range(4)]
        qmap = [bs[b][7 - k] for b in range(4) for k in range(8)]
        selected = list(reversed(layers)) if inverse else layers
        for layer in selected:
            gates = list(reversed(layer)) if inverse else layer
            for c, t in gates:
                values[qmap[t]] ^= values[qmap[c]]


def simulate_architecture(width: int, input_map: list[int], output_map: list[int],
                          canonical_tail: list[Op], mix_layers,
                          state_qmaps: list[list[list[int]] | None],
                          key_histories: list[list[int] | None],
                          trials: int = 34) -> dict:
    """Macro-level whole-circuit audit using the exact physical wire maps."""
    fixed = [
        (bytes.fromhex("000102030405060708090a0b0c0d0e0f"),
         bytes.fromhex("00112233445566778899aabbccddeeff")),
        (bytes(16), bytes(16)),
    ]
    rng = random.Random(0xA35128)
    vectors = fixed + [(rng.randbytes(16), rng.randbytes(16)) for _ in range(trials - len(fixed))]
    rcons = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]
    rows = []
    for key_bytes, plaintext in vectors:
        values = [0] * width
        key = list(range(128))
        state_views = [list(range(128, 256))]
        for i, v in enumerate(key_bytes):
            _write_byte(values, byte(key, i), v)
        for i, v in enumerate(plaintext):
            _write_byte(values, byte(state_views[0], i), v)

        for rnd in range(1, 11):
            for k, s in zip(key, state_views[rnd - 1]):
                values[s] ^= values[k]
            history = key_histories[rnd]
            if history is not None:
                assert all(values[q] == 0 for q in history)
                for i in range(32):
                    values[history[i]] ^= values[key[96 + i]]
            for i in range(4):
                if history is None:
                    controls = byte(key, 12 + ((i + 1) % 4))
                else:
                    source = (i + 1) % 4
                    controls = history[8 * source:8 * source + 8]
                target = byte(key, i)
                _write_byte(values, target,
                            _read_byte(values, target) ^ SBOXES["AES"][_read_byte(values, controls)])
            for j, q in enumerate(byte(key, 0)):
                if rcons[rnd - 1] & (1 << (7 - j)):
                    values[q] ^= 1
            for word in range(3):
                for bit in range(32):
                    values[key[32 * (word + 1) + bit]] ^= values[key[32 * word + bit]]

            qmaps = state_qmaps[rnd]
            assert qmaps is not None
            prior = state_views[rnd - 1][:]
            raw = [0] * 128
            for i, qmap in enumerate(qmaps):
                assert qmap[:8] == byte(prior, i)
                assert all(values[q] == 0 for q in qmap[8:])
                x = _read_byte(values, qmap[:8])
                for q in qmap:
                    values[q] = 0
                _write_byte(values, [qmap[q] for q in input_map], x)
                _write_byte(values, [qmap[q] for q in output_map], SBOXES["AES"][x])
                prior[8 * i:8 * i + 8] = [qmap[q] for q in input_map]
                raw[8 * i:8 * i + 8] = [qmap[q] for q in output_map]
            state_views[rnd - 1] = prior
            shifted = shift_rows_view(raw)
            if rnd != 10:
                _sim_mix(values, shifted, mix_layers)
            state_views.append(shifted)

        for k, s in zip(key, state_views[10]):
            values[s] ^= values[k]
        ciphertext = bytes(_read_byte(values, byte(state_views[10], i)) for i in range(16))
        expected, _ = aes128_reference(plaintext, key_bytes)
        assert ciphertext == expected

        # Reverse the exact architecture.
        for k, s in zip(key, state_views[10]):
            values[s] ^= values[k]
        for rnd in reversed(range(1, 11)):
            if rnd != 10:
                _sim_mix(values, state_views[rnd], mix_layers, inverse=True)
            raw = unshift_rows_view(state_views[rnd])
            qmaps = state_qmaps[rnd]
            assert qmaps is not None
            for i, qmap in enumerate(qmaps):
                controls = byte(state_views[rnd - 1], i)
                targets = byte(raw, i)
                assert controls == [qmap[q] for q in input_map]
                assert targets == [qmap[q] for q in output_map]
                y = _read_byte(values, targets)
                x = _read_byte(values, controls)
                _write_byte(values, targets, y ^ SBOXES["AES"][x])
                assert _read_byte(values, targets) == 0
            restored = state_views[rnd - 1][:]
            for i, qmap in enumerate(qmaps):
                for op in canonical_tail:
                    c, t = op.wires
                    values[qmap[t]] ^= values[qmap[c]]
                restored[8 * i:8 * i + 8] = qmap[:8]
                assert all(values[q] == 0 for q in qmap[8:])
            state_views[rnd - 1] = restored

            for word in reversed(range(3)):
                for bit in range(32):
                    values[key[32 * (word + 1) + bit]] ^= values[key[32 * word + bit]]
            for j, q in enumerate(byte(key, 0)):
                if rcons[rnd - 1] & (1 << (7 - j)):
                    values[q] ^= 1
            history = key_histories[rnd]
            for i in reversed(range(4)):
                if history is None:
                    controls = byte(key, 12 + ((i + 1) % 4))
                else:
                    source = (i + 1) % 4
                    controls = history[8 * source:8 * source + 8]
                target = byte(key, i)
                _write_byte(values, target,
                            _read_byte(values, target) ^ SBOXES["AES"][_read_byte(values, controls)])
            if history is not None:
                for i in range(32):
                    values[history[i]] ^= values[key[96 + i]]
                assert all(values[q] == 0 for q in history)
            for k, s in zip(key, state_views[rnd - 1]):
                values[s] ^= values[k]

        assert state_views[0] == list(range(128, 256))
        final_key = bytes(_read_byte(values, byte(key, i)) for i in range(16))
        final_plain = bytes(_read_byte(values, byte(state_views[0], i)) for i in range(16))
        assert final_key == key_bytes and final_plain == plaintext
        assert all(values[q] == 0 for q in range(256, width))
        rows.append({"key": key_bytes.hex(), "plaintext": plaintext.hex(),
                     "ciphertext": ciphertext.hex(), "pass": True})
    return {"vectors": trials, "fixed_vectors": len(fixed), "deterministic_random_vectors": trials-len(fixed),
            "forward_ciphertexts_match_reference": True,
            "reverse_restores_original_physical_key_and_plaintext_wires": True,
            "all_other_physical_wires_zero_after_reverse": True,
            "sample_results": rows[:2]}


def build_dynamic(relaxed_c0, input_map, output_map, canonical_tail, c1ops, mix_layers,
                  width=2816, key_history_rounds=frozenset()):
    key_history_rounds = frozenset(key_history_rounds)
    assert key_history_rounds <= set(range(1, 11))
    assert width == 2816 + 32 * len(key_history_rounds)
    key = list(range(128))
    state_views: list[list[int]] = [list(range(128, 256))]
    raw_views: list[list[int] | None] = [None]
    key_histories: list[list[int] | None] = [None]
    state_qmaps: list[list[list[int]] | None] = [None]
    pool = ZeroPool(range(256, width))
    timeline = Timeline(width)
    component_calls = []
    rcons = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]
    stages = []
    pool_audit = [{"point": "initial", "zero_wires": len(pool.wires), "live_wires": 256}]

    def snap(label, rnd, prior=None):
        row = {"label": label, "round": rnd, "full_depth": timeline.full_depth,
               "t_depth": timeline.t_depth, "zero_pool": len(pool.wires),
               "operations": len(timeline.records)}
        if prior is not None:
            row["depth_increment"] = timeline.full_depth - prior
        stages.append(row)
        return timeline.full_depth

    # Forward computation.  Reserve every zero used by the 20 S-boxes before
    # emitting any one of them so independent calls cannot accidentally reuse
    # the same physical wire within a round.
    for rnd in range(1, 11):
        start = timeline.full_depth
        add_round_key(timeline, key, state_views[rnd - 1])
        after_ark = snap("forward_after_AddRoundKey", rnd, start)
        history = pool.take(timeline, 32) if rnd in key_history_rounds else None
        key_work_sets = [pool.take(timeline, 64) for _ in range(4)]
        state_zero_sets = [pool.take(timeline, 64) for _ in range(16)]
        assert len(pool.wires) >= 0

        if history is not None:
            for i in range(32):
                timeline.emit(Op("cx", (key[96 + i], history[i])))

        for i in range(4):
            if history is None:
                controls = byte(key, 12 + ((i + 1) % 4))
            else:
                source = (i + 1) % 4
                controls = history[8 * source:8 * source + 8]
            map_fixed_component(
                timeline, c1ops, controls, byte(key, i), key_work_sets[i],
                call_log=component_calls, tag=f"forward_key_round_{rnd}_byte_{i}")
        add_rcon(timeline, key[:32], rcons[rnd - 1])
        xor_words_forward(timeline, key)

        prior_view = state_views[rnd - 1][:]
        raw_out = [0] * 128
        returned = []
        round_qmaps = []
        for i in range(16):
            round_qmaps.append(byte(prior_view, i) + state_zero_sets[i])
            new_in, new_out, zero = map_relaxed_c0(
                timeline, relaxed_c0, byte(prior_view, i), state_zero_sets[i],
                input_map, output_map, call_log=component_calls,
                tag=f"forward_state_round_{rnd}_byte_{i}")
            prior_view[8 * i:8 * i + 8] = new_in
            raw_out[8 * i:8 * i + 8] = new_out
            returned.extend(zero)
        state_views[rnd - 1] = prior_view
        pool.give(q for ws in key_work_sets for q in ws)
        pool.give(returned)
        assert len(set(prior_view + raw_out)) == 256
        after_sbox = snap("forward_after_relaxed_Sboxes_and_key_schedule", rnd, after_ark)

        shifted = shift_rows_view(raw_out)
        if rnd != 10:
            mix_state(timeline, shifted, mix_layers)
        state_views.append(shifted)
        raw_views.append(raw_out)
        key_histories.append(history)
        state_qmaps.append(round_qmaps)
        snap("forward_after_linear_layer", rnd, after_sbox)
        retained_histories = sum(r <= rnd for r in key_history_rounds)
        expected_pool = (width - 256) - 128 * rnd - 32 * retained_histories
        assert len(pool.wires) == expected_pool, (rnd, len(pool.wires), expected_pool)
        pool_audit.append({"point": f"forward_round_{rnd}", "zero_wires": len(pool.wires),
                           "live_wires": width - len(pool.wires)})

    add_round_key(timeline, key, state_views[10])
    forward_end = snap("forward_ciphertext_ready", 10)
    forward_metrics = timeline.metric_dict()

    # Matching Huang's resource program, the phase comparison is outside scope.
    add_round_key(timeline, key, state_views[10])
    for rnd in reversed(range(1, 11)):
        start = timeline.full_depth
        if rnd != 10:
            mix_state(timeline, state_views[rnd], mix_layers, inverse=True)
        after_linear = snap("reverse_after_inverse_linear_layer", rnd, start)

        round_qmaps = state_qmaps[rnd]
        assert round_qmaps is not None
        live_local = set(input_map + output_map)
        # The 56 relaxed-zero wires from each forward C0 are available again
        # in LIFO order.  Reuse them as 56 of the 64 C1 work wires, borrowing
        # only eight more zeros per byte.
        relaxed_zero_sets = [
            pool.reserve(qmap[q] for q in range(72) if q not in live_local)
            for qmap in round_qmaps
        ]
        key_work_sets = [pool.take(timeline, 64) for _ in range(4)]
        borrowed_sets = [pool.take(timeline, 8) for _ in range(16)]
        state_work_sets = [relaxed_zero_sets[i] + borrowed_sets[i] for i in range(16)]
        # This round state may have migrated when it served as the input to
        # the next relaxed C0.  Undo the free ShiftRows relabeling from its
        # current view rather than using the stale forward-time wire list.
        raw_out = unshift_rows_view(state_views[rnd])
        for i in range(16):
            assert byte(state_views[rnd - 1], i) == [round_qmaps[i][q] for q in input_map]
            assert byte(raw_out, i) == [round_qmaps[i][q] for q in output_map]
            map_fixed_component(timeline, c1ops, byte(state_views[rnd - 1], i),
                                byte(raw_out, i), state_work_sets[i],
                                call_log=component_calls,
                                tag=f"reverse_state_round_{rnd}_byte_{i}")

        # C1 clears the relaxed output.  The omitted C0 tail can now restore
        # the old state byte to the exact physical wires on which it entered
        # the forward call, leaving every other local wire zero.
        restored_previous = state_views[rnd - 1][:]
        for i, qmap in enumerate(round_qmaps):
            for op in canonical_tail:
                timeline.emit(Op("cx", (qmap[op.wires[0]], qmap[op.wires[1]])))
            restored_previous[8 * i:8 * i + 8] = qmap[:8]
        state_views[rnd - 1] = restored_previous

        xor_words_reverse(timeline, key)
        add_rcon(timeline, key[:32], rcons[rnd - 1])
        history = key_histories[rnd]
        for i in reversed(range(4)):
            if history is None:
                controls = byte(key, 12 + ((i + 1) % 4))
            else:
                source = (i + 1) % 4
                controls = history[8 * source:8 * source + 8]
            map_fixed_component(
                timeline, c1ops, controls, byte(key, i), key_work_sets[i],
                call_log=component_calls, tag=f"reverse_key_round_{rnd}_byte_{i}")
        if history is not None:
            # After reversing the word XORs and C1 contribution the physical
            # key is K_(r-1), exactly the value stored in this history word.
            for i in range(32):
                timeline.emit(Op("cx", (key[96 + i], history[i])))
        after_clear = snap("reverse_after_Sboxes_and_key_schedule", rnd, after_linear)

        pool.give(q for ws in key_work_sets for q in ws)
        for i, qmap in enumerate(round_qmaps):
            pool.give(qmap[8:])
            pool.give(borrowed_sets[i])
        if history is not None:
            pool.give(history)
        add_round_key(timeline, key, state_views[rnd - 1])
        snap("reverse_after_AddRoundKey", rnd, after_clear)
        retained_histories = sum(r < rnd for r in key_history_rounds)
        expected_pool = (width - 256) - 128 * (rnd - 1) - 32 * retained_histories
        assert len(pool.wires) == expected_pool, (rnd, len(pool.wires), expected_pool)
        pool_audit.append({"point": f"reverse_round_{rnd}", "zero_wires": len(pool.wires),
                           "live_wires": width - len(pool.wires)})

    assert state_views[0] == list(range(128, 256))
    assert pool.wires == set(range(width)) - set(key) - set(state_views[0])
    full_metrics = timeline.metric_dict()
    return (timeline, state_views, raw_views, stages, pool_audit, forward_end,
            forward_metrics, full_metrics, pool, key_histories, state_qmaps,
            component_calls)


def _macro_component_events() -> dict[str, list[dict]]:
    c0 = json.loads(C0_CERT.read_text(encoding="utf-8"))["events"]
    relaxed = [e for e in c0 if not e.get("canonicalization")]
    assert len(c0) - len(relaxed) == 13
    c1_path = ROOT / "results" / "aes_t3_final" / "AES_Sbox_C1_Q80_T3_best_certificate.json"
    c1 = json.loads(c1_path.read_text(encoding="utf-8"))["events"]
    return {"C0_relaxed": relaxed, "C1": c1}


def _expand_macro_call(call: dict, events: list[dict]) -> list[dict]:
    qmap = call["qmap"]
    out = []
    for event in events:
        kind = event["kind"]
        if kind == "prep":
            continue
        local = event["wires"]
        if kind == "cx":
            op = {"kind": "CNOT", "wires": [qmap[local[0]], qmap[local[1]]]}
        elif kind == "x":
            op = {"kind": "X", "wires": [qmap[local[0]]]}
        elif kind in {"and3", "and4"}:
            op = {"kind": "QAND", "wires": [qmap[q] for q in local[:3]],
                  "implementation": ("HUANG_FOUR_WIRE" if kind == "and4" else
                                     f"PREPARED_{event.get('variant', 'standard').upper()}")}
            if kind == "and4":
                op["scratch"] = qmap[local[3]]
        else:
            assert kind == "cleanup"
            op = {"kind": "QAND_DAG", "wires": [qmap[q] for q in local[:3]],
                  "implementation": "MEASUREMENT_UNCOMPUTE"}
        op["component"] = call["component"]
        op["tag"] = call["tag"]
        out.append(op)
    return out


def compose_macro_program(timeline: Timeline, component_calls: list[dict],
                          record_limit: int) -> list[dict]:
    """Replace each decomposed S-box range by its QAND-level macro program."""
    assert 0 <= record_limit <= len(timeline.records)
    events = _macro_component_events()
    by_start = {call["start"]: call for call in component_calls if call["start"] < record_limit}
    assert len(by_start) == sum(call["start"] < record_limit for call in component_calls)
    for call in by_start.values():
        assert call["end"] <= record_limit, "record limit splits an S-box call"
    result = []
    i = 0
    while i < record_limit:
        call = by_start.get(i)
        if call is not None:
            result.extend(_expand_macro_call(call, events[call["component"]]))
            i = call["end"]
            continue
        op = timeline.records[i][1]
        assert op.kind in {"cx", "x"}, (i, op)
        result.append({"kind": "CNOT" if op.kind == "cx" else "X",
                       "wires": list(op.wires), "component": "AES_linear_or_key"})
        i += 1
    return result


def write_macro_program(path: Path, width: int, interface: str, ops: list[dict],
                        ciphertext_view: list[int],
                        insertion_after: int | None = None) -> dict:
    counts = {kind: sum(op["kind"] == kind for op in ops)
              for kind in ["QAND", "QAND_DAG", "CNOT", "X"]}
    h = hashlib.sha256()
    with path.open("w", encoding="utf-8", newline="\n") as f:
        def put(row: str):
            data = (row + "\n").encode("utf-8")
            h.update(data)
            f.write(row + "\n")

        put("QAND-CIRCUIT 1.0;")
        put(f"QREG q[{width}];")
        put(f"INTERFACE {interface};")
        put("")
        put("// key input/final: q[0..127]; plaintext input/final: q[128..255].")
        put("// QAND target must start at 0; QAND_DAG resets its target to 0.")
        put("// ShiftRows and RotWord are represented by logical wire relabeling.")
        put("// Ciphertext MSB-first physical view is recorded in the certificate JSON.")
        put("")
        if insertion_after is not None:
            assert 0 < insertion_after < len(ops)
        previous_tag = None
        for op_index, op in enumerate(ops):
            if insertion_after is not None and op_index == insertion_after:
                put("")
                put("// === FORWARD AES COMPLETE ===")
                put(f"// Forward macro operations executed: {insertion_after}.")
                put("// INSERT CIPHERTEXT COMPARISON / PHASE MARK HERE, THEN CONTINUE.")
                put("// Ciphertext q wires, MSB-first: " + ",".join(map(str, ciphertext_view)))
                put("// === BEGIN UNCOMPUTE ===")
                put("")
                previous_tag = None
            tag = op.get("tag")
            if tag is not None and tag != previous_tag:
                put(f"// {tag}")
                previous_tag = tag
            kind, wires = op["kind"], op["wires"]
            if kind == "CNOT":
                put(f"CNOT q[{wires[0]}] -> q[{wires[1]}];")
            elif kind == "X":
                put(f"X q[{wires[0]}];")
            elif kind == "QAND":
                suffix = f" // impl={op['implementation']}"
                if "scratch" in op:
                    suffix += f", scratch=q[{op['scratch']}]"
                put(f"QAND q[{wires[0]}], q[{wires[1]}] -> q[{wires[2]}];{suffix}")
            else:
                assert kind == "QAND_DAG"
                put(f"QAND_DAG q[{wires[0]}], q[{wires[1]}] -> q[{wires[2]}];"
                    " // impl=MEASUREMENT_UNCOMPUTE")
    gz_path = path.with_suffix(path.suffix + ".gz")
    with path.open("rb") as source, gzip.open(gz_path, "wb", compresslevel=9) as target:
        while chunk := source.read(1024 * 1024):
            target.write(chunk)
    result = {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "gzip_path": str(gz_path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": h.hexdigest(),
        "bytes": path.stat().st_size,
        "gzip_bytes": gz_path.stat().st_size,
        "operation_counts": counts,
        "operation_count": len(ops),
        "ciphertext_view_msb_first": ciphertext_view,
    }
    if insertion_after is not None:
        result["oracle_insertion_after_macro_operation"] = insertion_after
        result["oracle_insertion_marker"] = "FORWARD AES COMPLETE"
    return result


def simulate_macro_program(ops: list[dict], forward_count: int, width: int,
                           ciphertext_view: list[int]) -> dict:
    vectors = [
        (bytes.fromhex("000102030405060708090a0b0c0d0e0f"),
         bytes.fromhex("00112233445566778899aabbccddeeff")),
        (bytes(16), bytes(16)),
    ]
    samples = []
    for key_bytes, plaintext in vectors:
        values = [0] * width
        for i, value in enumerate(key_bytes):
            _write_byte(values, list(range(8 * i, 8 * i + 8)), value)
        for i, value in enumerate(plaintext):
            _write_byte(values, list(range(128 + 8 * i, 128 + 8 * i + 8)), value)
        ciphertext = None
        for index, op in enumerate(ops, start=1):
            kind, wires = op["kind"], op["wires"]
            if kind == "CNOT":
                values[wires[1]] ^= values[wires[0]]
            elif kind == "X":
                values[wires[0]] ^= 1
            elif kind == "QAND":
                assert values[wires[2]] == 0, (index, op)
                values[wires[2]] = values[wires[0]] & values[wires[1]]
            else:
                assert kind == "QAND_DAG"
                assert values[wires[2]] == (values[wires[0]] & values[wires[1]]), (index, op)
                values[wires[2]] = 0
            if index == forward_count:
                ciphertext = bytes(_read_byte(values, byte(ciphertext_view, i))
                                   for i in range(16))
        expected, _ = aes128_reference(plaintext, key_bytes)
        assert ciphertext == expected, (ciphertext, expected)
        final_key = bytes(_read_byte(values, list(range(8 * i, 8 * i + 8)))
                          for i in range(16))
        final_plain = bytes(_read_byte(values, list(range(128 + 8 * i, 128 + 8 * i + 8)))
                            for i in range(16))
        assert final_key == key_bytes and final_plain == plaintext
        assert all(values[q] == 0 for q in range(256, width))
        samples.append({"key": key_bytes.hex(), "plaintext": plaintext.hex(),
                        "ciphertext": ciphertext.hex(), "expected": expected.hex(),
                        "pass": True})
    return {"basis_vectors": len(vectors), "forward_matches_AES128": True,
            "full_program_restores_key_plaintext_and_all_ancillas": True,
            "samples": samples}


def prefix_timeline(timeline: Timeline, operation_count: int) -> Timeline:
    prefix = Timeline(timeline.width)
    for _, op in timeline.records[:operation_count]:
        prefix.emit(op)
    measurements = [op.measurement for _, op in prefix.records if op.measurement is not None]
    prefix.next_measurement = max(measurements, default=-1) + 1
    return prefix


def materialize_gzip_text(gzip_path: Path, plain_path: Path, expected_sha256: str) -> dict:
    h = hashlib.sha256()
    with gzip.open(gzip_path, "rb") as source, plain_path.open("wb") as target:
        while chunk := source.read(1024 * 1024):
            h.update(chunk)
            target.write(chunk)
    assert h.hexdigest() == expected_sha256
    return {"path": str(plain_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": h.hexdigest(), "bytes": plain_path.stat().st_size}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "results" / "aes_whole_dw_relaxed_reuse")
    ap.add_argument("--write-qasm", action="store_true")
    ap.add_argument("--key-history", action="store_true",
                    help="retain each old 32-bit key word to decouple C1 cleanup")
    ap.add_argument("--history-rounds", default="",
                    help="comma-separated rounds whose old 32-bit key word is retained")
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    relaxed, input_map, output_map, canonical_tail, relaxed_proof = load_relaxed_c0()
    _, c1ops, c1proof = load_component("C1")
    mix_layers, mix_info = load_mix()
    if args.key_history:
        history_rounds = frozenset(range(1, 11))
    else:
        history_rounds = frozenset(int(x) for x in args.history_rounds.split(",") if x)
    result = build_dynamic(
        relaxed, input_map, output_map, canonical_tail, c1ops, mix_layers,
        width=2816 + 32 * len(history_rounds), key_history_rounds=history_rounds)
    (timeline, state_views, raw_views, stages, pool_audit, forward_end,
     forward_metrics, full_metrics, pool, key_histories, state_qmaps,
     component_calls) = result
    assert metrics([op for _, op in timeline.records], timeline.width) == full_metrics
    reference = verify_reference_vectors()
    architecture_simulation = simulate_architecture(
        timeline.width, input_map, output_map, canonical_tail, mix_layers,
        state_qmaps, key_histories)

    local_search_path = ROOT / "results" / "aes_whole_dw_history_local_search.json"
    local_search = json.loads(local_search_path.read_text(encoding="utf-8"))
    if sorted(history_rounds) == local_search["best"]["rounds"]:
        assert local_search["best"]["width"] == timeline.width
        assert local_search["best"]["full_depth"] == full_metrics["full_depth"]
    search_proof = {
        "path": str(local_search_path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": hashlib.sha256(local_search_path.read_bytes()).hexdigest(),
        "cardinalities_exhausted": local_search["sizes"],
        "candidates_evaluated": local_search["evaluated"],
        "best": local_search["best"],
        "selected_is_search_best": sorted(history_rounds) == local_search["best"]["rounds"],
    }

    for m in (forward_metrics, full_metrics):
        m["DW_full"] = m["width"] * m["full_depth"]
        m["DW_T"] = m["width"] * m["t_depth"]
    baselines = {
        "canonical_C0_round1": {"width": 2816, "full_depth": 1820,
                                 "DW_full": 2816 * 1820, "t_depth": 60,
                                 "DW_T": 2816 * 60, "cnot": 338728},
        "Huang_EUROCRYPT_2025_Table8": {"width": 3156, "full_depth": 1782,
                                        "DW_full": 3156 * 1782, "t_depth": 60,
                                        "DW_T": 3156 * 60, "t_count": 67200,
                                        "cnot": 353160, "measurements": 16800,
                                        "one_qubit_clifford": 119200},
    }
    deltas = {}
    for name, baseline in baselines.items():
        common = sorted(set(full_metrics) & set(baseline))
        deltas[name] = {
            "absolute": {k: full_metrics[k] - baseline[k] for k in common},
            "percent": {k: 100 * (full_metrics[k] - baseline[k]) / baseline[k]
                        for k in common if baseline[k]},
        }

    contextual_literature = {
        "Liao_Luo_ASIACRYPT_2025_revised_Table10_Grover": {
            "width": 724, "t_depth": 232, "t_count": 77792,
            "DW_T": 167968,
            "source": "https://eprint.iacr.org/2025/1494",
            "comparison_to_compute_uncompute": {
                "absolute": {
                    "width": full_metrics["width"] - 724,
                    "t_depth": full_metrics["t_depth"] - 232,
                    "t_count": full_metrics["t_count"] - 77792,
                    "DW_T": full_metrics["DW_T"] - 167968,
                },
                "percent": {
                    "width": 100 * (full_metrics["width"] - 724) / 724,
                    "t_depth": 100 * (full_metrics["t_depth"] - 232) / 232,
                    "t_count": 100 * (full_metrics["t_count"] - 77792) / 77792,
                    "DW_T": 100 * (full_metrics["DW_T"] - 167968) / 167968,
                },
            },
            "comparability": "Context only: architecture, S-box family, and oracle accounting differ; neither circuit includes a hardware connectivity/routing model.",
        },
        "Liao_Luo_ASIACRYPT_2025_revised_Table11_encryption": {
            "width": 512, "t_depth": 120, "t_count": 33280,
            "DW_T": 61440,
            "source": "https://eprint.iacr.org/2025/1494",
            "comparability": "Context only: their encryption-oracle key conditions/interface differ from this quantum-key retained-history forward pipeline.",
        },
        "Chen_Cai_Gao_Lin_QIP_2026_Table15_forward_AES128": {
            "width": 1028, "t_depth": 100, "t_count": 52480,
            "DW_T": 102800,
            "source": "https://doi.org/10.1007/s11128-026-05083-7",
            "comparison_to_forward": {
                "absolute": {
                    "width": forward_metrics["width"] - 1028,
                    "t_depth": forward_metrics["t_depth"] - 100,
                    "t_count": forward_metrics["t_count"] - 52480,
                    "DW_T": forward_metrics["DW_T"] - 102800,
                },
                "percent": {
                    "width": 100 * (forward_metrics["width"] - 1028) / 1028,
                    "t_depth": 100 * (forward_metrics["t_depth"] - 100) / 100,
                    "t_count": 100 * (forward_metrics["t_count"] - 52480) / 52480,
                    "DW_T": 100 * (forward_metrics["DW_T"] - 102800) / 102800,
                },
            },
            "comparability": "Forward AES-128 with a quantum nonlinear key schedule, but a different architecture and S-box; full Clifford+T depth is not reported in their Table 15.",
        },
    }

    artifact = {
        "name": "AES128_T3_pipeline_relaxed_C0_key_history_rounds_1_to_9",
        "claim_status": "verified composition candidate; no global-optimality claim",
        "scope": "AES-128 compute/uncompute skeleton excluding ciphertext comparison/phase mark",
        "resource_model": "all-to-all logical wires; unit gate/measurement/feed-forward layer; free ShiftRows/RotWord relabeling",
        "optimization": {
            "idea": "Remove the 13-CNOT C0 input-position restoration tail and track its exact noncanonical live-wire interface across rounds.",
            "zero_pool": "All physically zero wires are selected by earliest-ready lifetime reuse.",
            "linear_overlap": "MixColumns begins per wire as soon as the corresponding relaxed S-box output is ready.",
            "key_history": ("Selected old 32-bit last key words are retained until reverse computation; "
                            "C1 cleanup then uses the history copy and no longer stalls the evolving key."
                            if history_rounds else "disabled"),
        },
        "search_proof": search_proof,
        "interfaces": {
            "forward_state": "160 relaxed-C0 calls",
            "forward_key": "40 canonical C1 calls",
            "reverse_state": "160 canonical C1 calls",
            "reverse_key": "40 canonical C1 calls",
        },
        "relaxed_C0_proof": relaxed_proof,
        "C1_proof": c1proof,
        "MixColumns": mix_info,
        "layout": {
            "width": timeline.width,
            "key_initial_and_final_wires": [0, 127],
            "plaintext_initial_wires": [128, 255],
            "plaintext_final_view_msb_first": state_views[0],
            "ciphertext_view_msb_first": state_views[10],
            "initial_zero_pool": timeline.width - 256,
            "key_history_rounds": sorted(history_rounds),
            "key_history_words": len(history_rounds),
            "key_history_qubits": 32 * len(history_rounds),
            "minimum_unreserved_zero_pool_during_batch_allocation": pool.minimum_size,
            "final_zero_pool": len(pool.wires),
            "zero_pool_allocations_total": pool.allocations,
            "maximum_ready_time_among_selected_zero_wires": pool.max_selected_ready,
        },
        "forward_metrics_at_ciphertext": forward_metrics,
        "forward_ciphertext_depth": forward_end,
        "compute_uncompute_metrics": full_metrics,
        "baselines": baselines,
        "deltas": deltas,
        "contextual_literature": contextual_literature,
        "stages": stages,
        "pool_audit": pool_audit,
        "verification": {
            "source_Sbox_certificates_replayed": True,
            "relaxed_interface_derived_by_exact_inverse_linear_tail": True,
            "all_live_wire_sets_disjoint_each_round": True,
            "zero_pool_cardinality_checked_after_every_round": True,
            "final_live_set_only_key_and_plaintext": True,
            "online_vs_independent_whole_metric_match": True,
            "aes_reference_vectors": reference,
            "whole_physical_macro_simulation": architecture_simulation,
            "dynamic_inverse_uses_C1_not_text_reversed_measurements": True,
        },
    }
    if args.write_qasm:
        forward_operation_count = forward_metrics["gate_count"]
        forward_t = prefix_timeline(timeline, forward_operation_count)
        expected_forward = {k: v for k, v in forward_metrics.items()
                            if k not in {"DW_full", "DW_T"}}
        assert forward_t.metric_dict() == expected_forward

        forward_qasm_gz = out / "AES128_T3_relaxed_reuse_forward_encryption.qasm.gz"
        full_qasm_gz = out / "AES128_T3_relaxed_reuse_compute_uncompute.qasm.gz"
        forward_qasm = write_scheduled_qasm_gz(
            forward_qasm_gz, forward_t,
            description=("AES-128 forward encryption. Output wire view is in the certificate; "
                         "round-key/state history and work garbage are intentionally retained."))
        full_qasm = write_scheduled_qasm_gz(
            full_qasm_gz, timeline,
            description="AES-128 compute/uncompute; comparison/phase mark intentionally omitted.")
        forward_qasm["plain"] = materialize_gzip_text(
            forward_qasm_gz, forward_qasm_gz.with_suffix(""),
            forward_qasm["sha256_uncompressed_text"])
        full_qasm["plain"] = materialize_gzip_text(
            full_qasm_gz, full_qasm_gz.with_suffix(""),
            full_qasm["sha256_uncompressed_text"])
        artifact["qasm"] = {"forward_encryption": forward_qasm,
                            "compute_uncompute": full_qasm}

        forward_macro_ops = compose_macro_program(
            timeline, component_calls, forward_operation_count)
        full_macro_ops = compose_macro_program(
            timeline, component_calls, len(timeline.records))
        assert full_macro_ops[:len(forward_macro_ops)] == forward_macro_ops
        macro_simulation = simulate_macro_program(
            full_macro_ops, len(forward_macro_ops), timeline.width, state_views[10])
        artifact["logical_qand"] = {
            "forward_encryption": write_macro_program(
                out / "AES128_T3_relaxed_reuse_forward_encryption.qand",
                timeline.width, "AES128_FORWARD", forward_macro_ops, state_views[10]),
            "compute_uncompute": write_macro_program(
                out / "AES128_T3_relaxed_reuse_compute_uncompute.qand",
                timeline.width, "AES128_COMPUTE_UNCOMPUTE", full_macro_ops,
                state_views[10], insertion_after=len(forward_macro_ops)),
            "semantics": "QAND/QAND_DAG/CNOT/X inspection form; exact Clifford+T realization is the dynamic QASM.",
        }
        artifact["verification"]["logical_qand_basis_simulation"] = macro_simulation
        artifact["verification"]["exported_layer_wire_exclusivity"] = True

        wire_map = {
            "width": timeline.width,
            "key_history_wires_by_round": {
                str(rnd): key_histories[rnd] for rnd in range(1, 11)
                if key_histories[rnd] is not None},
            "state_sbox_qmaps_by_round_byte": {
                str(rnd): state_qmaps[rnd] for rnd in range(1, 11)},
            "component_calls_in_emission_order": component_calls,
            "forward_decomposed_operation_count": forward_operation_count,
            "full_decomposed_operation_count": len(timeline.records),
            "forward_macro_operation_count": len(forward_macro_ops),
            "full_macro_operation_count": len(full_macro_ops),
        }
        wire_map_path = out / "wire_lifetime_map.json"
        wire_map_path.write_text(json.dumps(wire_map, indent=2), encoding="utf-8")
        artifact["wire_lifetime_map"] = {
            "path": str(wire_map_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": hashlib.sha256(wire_map_path.read_bytes()).hexdigest(),
            "bytes": wire_map_path.stat().st_size,
        }

    (out / "whole_circuit_certificate.json").write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    comparison = {"candidate": full_metrics, "baselines": baselines, "deltas": deltas}
    (out / "comparison.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"forward": forward_metrics, "full": full_metrics,
                      "deltas": deltas, "pool_min": pool.minimum_size}, indent=2))


if __name__ == "__main__":
    main()
