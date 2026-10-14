"""Parse named equations from the pasted AES reference circuit."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

EQ_RE = re.compile(r"^//\s+([A-Za-z]\w*|y\d+)\s*=\s*(\w+)\s*([+x#])\s*(\w+)\s*$")


@dataclass(frozen=True)
class Eq:
    dst: str
    lhs: str
    op: str
    rhs: str


def parse_comment_equations(path: str | Path) -> list[Eq]:
    eqs: list[Eq] = []
    for raw in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        m = EQ_RE.match(raw.strip())
        if m:
            eqs.append(Eq(*m.groups()))
    return eqs


def masks_until_nonlinear(eqs: list[Eq]) -> tuple[dict[str, int], list[int]]:
    masks = {f"x{i}": 1 << i for i in range(8)}
    targets: list[int] = []
    for e in eqs:
        if e.op == "x":
            for v in (e.lhs, e.rhs):
                if v in masks:
                    targets.append(masks[v])
            continue
        if e.lhs in masks and e.rhs in masks:
            masks[e.dst] = masks[e.lhs] ^ masks[e.rhs]
    return masks, sorted(set(targets))


def tail_linear_targets(eqs: list[Eq]) -> tuple[list[str], dict[str, int], list[int]]:
    first_tc = next((i for i, e in enumerate(eqs) if e.dst.startswith("tc") or e.dst.startswith("y")), len(eqs))
    basis_names = sorted(
        {v for e in eqs[first_tc:] for v in (e.lhs, e.rhs) if v.startswith("z")},
        key=lambda s: int(s[1:]),
    )
    masks = {name: 1 << i for i, name in enumerate(basis_names)}
    outputs: dict[str, int] = {}
    for e in eqs[first_tc:]:
        if e.op not in "+#":
            continue
        if e.lhs in masks and e.rhs in masks:
            masks[e.dst] = masks[e.lhs] ^ masks[e.rhs]
            if e.op == "#":
                # Constants do not affect XOR SLP count; track linear mask only.
                pass
            if e.dst.startswith("y"):
                outputs[e.dst] = masks[e.dst]
    return basis_names, masks, [outputs[f"y{i}"] for i in range(8)]

