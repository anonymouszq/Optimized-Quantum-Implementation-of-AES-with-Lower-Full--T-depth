"""Import external textual circuit descriptions."""

from __future__ import annotations

import re
from pathlib import Path

from .circuit import Circuit, Signal
from .external_eqs import parse_comment_equations, masks_until_nonlinear
from .linear_synth import paar_synthesize


COMMENT_RE = re.compile(r"^//\s+([A-Za-z]\w*|y\d+)\s*=\s*(\w+)\s*([+x#])\s*(\w+)\s*$")
PDF_LISTING_ASSIGN_RE = re.compile(
    r"(?:^|[^\S\r\n])(\d{1,2})[^\S\r\n]+"
    r"([tgy]\d+)[^\S\r\n]*=[^\S\r\n]*"
    r"("
    r"(?:NAND|NOR|AND|OR)[^\S\r\n]*\([^\S\r\n]*\w+[^\S\r\n]*,[^\S\r\n]*\w+[^\S\r\n]*\)"
    r"|"
    r"\w+[^\S\r\n]*(?:\+|#|x|⊕|⊖|\S)[^\S\r\n]*(?:\w+|1)"
    r"|"
    r"\w+"
    r")"
)


def import_comment_circuit(path: str | Path, hash_is_xnor: bool = False) -> Circuit:
    """Parse lines like ``// t0 = x1 + x2`` and ``// z0 = a x b``.

    The pasted AES reference stores the normal signal equations in comments while the
    executable code carries Gurobi variables. This importer intentionally reads only the
    normal Boolean network.
    """
    c = Circuit(8)
    sig: dict[str, Signal] = {f"x{i}": Signal(i) for i in range(8)}
    outputs: dict[int, Signal] = {}
    for raw in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        m = COMMENT_RE.match(raw.strip())
        if not m:
            continue
        dst, lhs, op, rhs = m.groups()
        if lhs not in sig or rhs not in sig:
            continue
        if op == "x":
            out = c.add("AND", sig[lhs], sig[rhs])
        else:
            out = c.add("XOR", sig[lhs], sig[rhs])
            if op == "#" and hash_is_xnor:
                out = Signal(out.idx, True)
        sig[dst] = out
        if dst.startswith("y"):
            outputs[int(dst[1:])] = out
    if set(outputs) != set(range(8)):
        raise ValueError(f"expected y0..y7, got {sorted(outputs)}")
    c.set_outputs([outputs[i] for i in range(8)])
    return c


def import_pdf_listing(path: str | Path, listing: int, n_inputs: int = 8) -> Circuit:
    """Import operation tables extracted from SLICE-style PDF listings.

    The PDF text extractor used on these papers mojibakes the XOR/XNOR glyphs, so this
    parser treats any unknown binary infix token as XOR. The known listings use NAND/NOR
    for inverted nonlinear gates and do not rely on the distinction between XOR glyphs.
    """
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    start = text.find(f"Listing {listing}:")
    if start < 0:
        raise ValueError(f"Listing {listing} not found in {path}")
    end = text.find(f"Listing {listing + 1}:", start + 1)
    if end < 0:
        end = len(text)
    block = text[start:end]

    c = Circuit(n_inputs)
    sig: dict[str, Signal] = {f"x{i}": Signal(i) for i in range(n_inputs)}
    outputs: dict[int, Signal] = {}

    def parse_signal(tok: str) -> Signal:
        tok = tok.strip()
        if tok == "1":
            raise ValueError("constant 1 is not a signal")
        if tok not in sig:
            raise ValueError(f"unknown signal {tok}")
        return sig[tok]

    def xor_with_const(a: Signal, rhs: str, xnor: bool = False) -> Signal:
        if rhs == "1":
            return Signal(a.idx, a.inv ^ (not xnor))
        b = parse_signal(rhs)
        out = c.add("XOR", a, b)
        return Signal(out.idx, out.inv ^ xnor)

    ops = [(int(depth), pos, dst, expr) for pos, (depth, dst, expr) in enumerate(PDF_LISTING_ASSIGN_RE.findall(block))]
    ops.sort(key=lambda item: (item[0], item[1]))

    for _, _, dst, expr in ops:
        expr = expr.strip()
        gate = re.fullmatch(r"(NAND|NOR|AND|OR)\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)", expr)
        if gate:
            op, a, b = gate.groups()
            base_op = "AND" if op in {"AND", "NAND"} else "OR"
            out = c.add(base_op, parse_signal(a), parse_signal(b))
            if op in {"NAND", "NOR"}:
                out = Signal(out.idx, True)
        elif expr in sig:
            out = sig[expr]
        else:
            m = re.fullmatch(r"(\w+)\s*(\S+)\s*(\w+|1)", expr)
            if not m:
                raise ValueError(f"unsupported listing expression: {dst} = {expr}")
            a, op, b = m.groups()
            xnor = op in {"#", "⊖"}
            out = xor_with_const(parse_signal(a), b, xnor=xnor)
        sig[dst] = out
        if dst.startswith("y"):
            outputs[int(dst[1:])] = out

    if set(outputs) != set(range(n_inputs)):
        raise ValueError(f"expected y0..y{n_inputs - 1}, got {sorted(outputs)}")
    c.set_outputs([outputs[i] for i in range(n_inputs)])
    return c


def import_with_optimized_prelinear(path: str | Path, hash_is_xnor: bool = False) -> Circuit:
    eqs = parse_comment_equations(path)
    first_and = next(i for i, e in enumerate(eqs) if e.op == "x")
    pre_masks, _ = masks_until_nonlinear(eqs)
    used_pre_masks = sorted(
        {
            pre_masks[v]
            for e in eqs[first_and:]
            for v in (e.lhs, e.rhs)
            if v in pre_masks
        }
    )
    prog = paar_synthesize(8, used_pre_masks)

    c = Circuit(8)
    id_to_sig: dict[int, Signal] = {i: Signal(i) for i in range(8)}
    mask_to_sig: dict[int, Signal] = {1 << i: Signal(i) for i in range(8)}
    for new_id, a, b in prog.steps:
        sig = c.add("XOR", id_to_sig[a], id_to_sig[b])
        id_to_sig[new_id] = sig
    for mask, expr in zip(prog.targets, prog.output_exprs):
        terms = [id_to_sig[i] for i in sorted(expr)]
        if not terms:
            raise ValueError("zero prelinear target is unsupported")
        acc = terms[0]
        for t in terms[1:]:
            acc = c.add("XOR", acc, t)
        mask_to_sig[mask] = acc

    sig: dict[str, Signal] = {f"x{i}": Signal(i) for i in range(8)}
    for name, mask in pre_masks.items():
        if mask in mask_to_sig:
            sig[name] = mask_to_sig[mask]

    outputs: dict[int, Signal] = {}
    for e in eqs[first_and:]:
        if e.lhs not in sig or e.rhs not in sig:
            continue
        if e.op == "x":
            out = c.add("AND", sig[e.lhs], sig[e.rhs])
        else:
            out = c.add("XOR", sig[e.lhs], sig[e.rhs])
            if e.op == "#" and hash_is_xnor:
                out = Signal(out.idx, True)
        sig[e.dst] = out
        if e.dst.startswith("y"):
            outputs[int(e.dst[1:])] = out
    if set(outputs) != set(range(8)):
        raise ValueError(f"expected y0..y7, got {sorted(outputs)}")
    c.set_outputs([outputs[i] for i in range(8)])
    return c


def import_simple_verilog(path: str | Path) -> Circuit:
    """Import Verilog emitted by ``Circuit.to_verilog``."""
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    header = re.search(r"input \[(\d+):0\] x, output \[(\d+):0\] y", text)
    if not header:
        raise ValueError("unsupported verilog header")
    n_inputs = int(header.group(1)) + 1
    n_outputs = int(header.group(2)) + 1
    c = Circuit(n_inputs)
    names: dict[str, Signal] = {f"x[{i}]": Signal(i) for i in range(n_inputs)}

    def parse_sig(tok: str) -> Signal:
        tok = tok.strip()
        inv = tok.startswith("~")
        if inv:
            tok = tok[1:].strip()
        base = names[tok]
        return Signal(base.idx, base.inv ^ inv)

    for raw in text.splitlines():
        line = raw.strip()
        m = re.fullmatch(r"wire (n\d+) = (.+);", line)
        if not m:
            continue
        name, expr = m.groups()
        out = None
        for token, op in [(" ^ ", "XOR"), (" & ", "AND"), (" | ", "OR")]:
            if token in expr:
                a, b = expr.split(token)
                out = c.add(op, parse_sig(a), parse_sig(b))
                break
        if out is None:
            if expr.startswith("~"):
                out = c.add("NOT", parse_sig(expr[1:]))
            else:
                out = parse_sig(expr)
        names[name] = out

    outputs = [Signal(0)] * n_outputs
    for raw in text.splitlines():
        line = raw.strip()
        m = re.fullmatch(r"assign y\[(\d+)\] = (.+);", line)
        if m:
            outputs[int(m.group(1))] = parse_sig(m.group(2))
    c.set_outputs(outputs)
    return c


def import_bp_c(path: str | Path) -> Circuit:
    """Import Boyar-Peralta style C macros: XOR(dst,a,b), AND(dst,a,b)."""
    c = Circuit(8)
    names: dict[str, Signal] = {f"U{i}": Signal(i) for i in range(8)}
    outputs: dict[int, Signal] = {}

    def parse_sig(tok: str) -> Signal:
        tok = tok.strip()
        inv = tok.startswith("~")
        if inv:
            tok = tok[1:].strip()
        base = names[tok]
        return Signal(base.idx, base.inv ^ inv)

    for raw in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        m = re.fullmatch(r"U(\d+)=in\[(\d+)\];", line)
        if m:
            names[f"U{m.group(1)}"] = Signal(int(m.group(2)))
            continue
        m = re.fullmatch(r"(XOR|AND)\((\w+),(\w+),(\w+)\);", line)
        if m:
            op, dst, a, b = m.groups()
            names[dst] = c.add(op, parse_sig(a), parse_sig(b))
            continue
        m = re.fullmatch(r"out\[(\d+)\]=(.+);", line)
        if m:
            outputs[int(m.group(1))] = parse_sig(m.group(2))
    if set(outputs) != set(range(8)):
        raise ValueError(f"expected out[0]..out[7], got {sorted(outputs)}")
    c.set_outputs([outputs[i] for i in range(8)])
    return c


def import_slp(path: str | Path, hash_is_xnor: bool = True) -> Circuit:
    """Import Peralta CMT SLP files with ``+``, ``x`` and optional ``#``."""
    lines = [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip()
    ]
    n_idx = next(i for i, line in enumerate(lines) if line.endswith("inputs"))
    n_inputs = int(lines[n_idx].split()[0])
    input_names = lines[n_idx + 1].split()
    m_idx = next(i for i, line in enumerate(lines) if line.endswith("outputs"))
    n_outputs = int(lines[m_idx].split()[0])
    output_names = lines[m_idx + 1].split()

    c = Circuit(n_inputs)
    names: dict[str, Signal] = {}
    for i, name in enumerate(input_names):
        m = re.search(r"\d+", name)
        names[name] = Signal(int(m.group(0)) if m else i)
    in_body = False
    for line in lines:
        if line == "begin":
            in_body = True
            continue
        if line == "end":
            break
        if not in_body or "=" not in line:
            continue
        dst, expr = [x.strip() for x in line.split("=", 1)]
        m = re.fullmatch(r"(\w+)\s*([+x#])\s*(\w+)", expr)
        if not m:
            raise ValueError(f"unsupported SLP expression: {line}")
        a, op, b = m.groups()
        if op == "x":
            out = c.add("AND", names[a], names[b])
        else:
            out = c.add("XOR", names[a], names[b])
            if op == "#" and hash_is_xnor:
                out = Signal(out.idx, True)
        names[dst] = out

    outputs = [Signal(0)] * n_outputs
    for i, name in enumerate(output_names):
        if name not in names:
            raise ValueError(f"missing output {name}")
        m = re.search(r"\d+", name)
        outputs[int(m.group(0)) if m else i] = names[name]
    if len(outputs) != n_outputs:
        raise ValueError("output count mismatch")
    c.set_outputs(outputs)
    return c


def import_artifact_py(path: str | Path) -> Circuit:
    """Import CHES 2025 Extended-BP artifact Python circuit files."""
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    parts = text.split("################### Here is your code !! ###################")
    if len(parts) < 3:
        raise ValueError("artifact marker not found")
    body = parts[1]
    c = Circuit(8)
    names: dict[str, Signal] = {f"x[{i}]": Signal(i) for i in range(8)}
    outputs: dict[int, Signal] = {}

    def parse_sig(tok: str) -> Signal:
        tok = tok.strip()
        if tok == "1":
            z = c.add("XOR", Signal(0), Signal(0))
            return Signal(z.idx, True)
        if tok not in names:
            raise ValueError(f"unknown signal {tok}")
        return names[tok]

    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith(("t = ", "r = ", "g = ", "T = ", "M = ", "L = ")):
            continue
        dst, expr = [x.strip() for x in line.split("=", 1)]
        expr = expr.replace(" ", "")
        dst = dst.replace(" ", "")
        if not re.fullmatch(r"[trgy]\[\d+\]", dst):
            continue
        out: Signal
        if "^" in expr:
            a, b = expr.split("^", 1)
            if b == "1":
                s = parse_sig(a)
                out = Signal(s.idx, not s.inv)
            elif a == "1":
                s = parse_sig(b)
                out = Signal(s.idx, not s.inv)
            else:
                out = c.add("XOR", parse_sig(a), parse_sig(b))
        elif "&" in expr:
            a, b = expr.split("&", 1)
            out = c.add("AND", parse_sig(a), parse_sig(b))
        elif "|" in expr:
            a, b = expr.split("|", 1)
            out = c.add("OR", parse_sig(a), parse_sig(b))
        else:
            out = parse_sig(expr)
        names[dst] = out
        m = re.fullmatch(r"y\[(\d+)\]", dst)
        if m:
            outputs[int(m.group(1))] = out
    if set(outputs) != set(range(8)):
        raise ValueError(f"expected y[0]..y[7], got {sorted(outputs)}")
    c.set_outputs([outputs[i] for i in range(8)])
    return c
