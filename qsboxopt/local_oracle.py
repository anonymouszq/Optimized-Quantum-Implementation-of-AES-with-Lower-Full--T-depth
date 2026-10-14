"""Python wrapper for the C++/CaDiCaL local resynthesis oracle."""

from __future__ import annotations

import subprocess
import platform
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "cpp" / "local_resynth_cadical"
LAYERED_BIN = ROOT / "cpp" / "local_resynth_layered_cadical"


@dataclass
class OracleResult:
    status: str
    stdout: str


def lut_csv_from_truths(n: int, output_truths: list[int]) -> str:
    values = []
    for x in range(1 << n):
        y = 0
        for bit, tt in enumerate(output_truths):
            y |= ((tt >> x) & 1) << bit
        values.append(format(y, "x"))
    return ",".join(values)


def call_local_oracle(
    n: int,
    output_truths: list[int],
    gates: int,
    conflicts: int = 200000,
    timeout: float = 5.0,
) -> OracleResult:
    lut = lut_csv_from_truths(n, output_truths)
    m = len(output_truths)
    return _run_oracle(BIN, [str(n), str(m), str(gates), lut, str(conflicts)], timeout)


def call_layered_oracle(
    n: int,
    output_truths: list[int],
    layer_counts: list[int],
    conflicts: int = 200000,
    timeout: float = 5.0,
) -> OracleResult:
    lut = lut_csv_from_truths(n, output_truths)
    m = len(output_truths)
    gates = sum(layer_counts)
    layers = ",".join(str(x) for x in layer_counts)
    return _run_oracle(
        LAYERED_BIN,
        [str(n), str(m), str(gates), layers, lut, str(conflicts)],
        timeout,
    )


def _run_oracle(exe: Path, args: list[str], timeout: float) -> OracleResult:
    if platform.system() == "Linux":
        cmd = [str(exe), *args]
        cwd = ROOT
    else:
        rel = exe.relative_to(ROOT).as_posix()
        cmd_text = " ".join([f"./{rel}", *args])
        cmd = ["wsl", "sh", "-lc", f"cd /mnt/c/Users/Administrator/Documents/Sbox && {cmd_text}"]
        cwd = None
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return OracleResult(status="TIMEOUT", stdout="")
    status = proc.stdout.splitlines()[0] if proc.stdout.splitlines() else "NO_OUTPUT"
    return OracleResult(status=status, stdout=proc.stdout)
