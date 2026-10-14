"""Known structural baseline circuits."""

from __future__ import annotations

from .circuit import Circuit, Signal
from .optimize import cleanup


def keccak_chi5() -> Circuit:
    """Naive 5-bit Keccak chi: y_i = x_i xor ((not x_{i+1}) and x_{i+2})."""
    c = Circuit(5)
    outs = []
    for i in range(5):
        n1 = c.add("NOT", Signal((i + 1) % 5))
        a = c.add("AND", n1, Signal((i + 2) % 5))
        y = c.add("XOR", Signal(i), a)
        outs.append(y)
    c.set_outputs(outs)
    return cleanup(c)


def prost4_stoffelen() -> Circuit:
    """Prøst 4-bit S-box implementation from Stoffelen Table 3 appendix.

    t0 = x2 & x1
    y1 = t0 ^ x3
    t2 = x0 & x1
    y0 = x2 ^ t2
    t4 = y1 & y0
    y2 = x0 ^ t4
    t6 = y1 & y2
    y3 = x1 ^ t6
    """
    c = Circuit(4)
    t0 = c.add("AND", Signal(2), Signal(1))
    y1 = c.add("XOR", t0, Signal(3))
    t2 = c.add("AND", Signal(0), Signal(1))
    y0 = c.add("XOR", Signal(2), t2)
    t4 = c.add("AND", y1, y0)
    y2 = c.add("XOR", Signal(0), t4)
    t6 = c.add("AND", y1, y2)
    y3 = c.add("XOR", Signal(1), t6)
    c.set_outputs([y0, y1, y2, y3])
    return c


def keccak5_stoffelen_bitslice() -> Circuit:
    """Keccak/Ketje/Keyak 5-bit S-box, Stoffelen bitslice k=13."""
    c = Circuit(5)
    t0 = c.add("NOT", Signal(2))
    t1 = c.add("AND", t0, Signal(3))
    y1 = c.add("XOR", t1, Signal(1))
    t3 = c.add("NOT", Signal(4))
    t4 = c.add("AND", t3, Signal(0))
    y3 = c.add("XOR", Signal(3), t4)
    t6 = c.add("OR", Signal(3), t3)
    y2 = c.add("XOR", t0, t6)
    t8 = c.add("NOT", Signal(0))
    t9 = c.add("OR", y1, t0)
    t10 = c.add("AND", t8, Signal(1))
    y0 = c.add("XOR", t9, t8)
    y4 = c.add("XOR", Signal(4), t10)
    c.set_outputs([y0, y1, y2, y3, y4])
    return c


def keccak5_depth2_15() -> Circuit:
    """Depth-2 Keccak/Ketje/Keyak 5-bit S-box found by local exact rewriting.

    Each coordinate has form (x_i xor x_{i+1}) xor (x_{i+1} or x_{i+2})
    with the output order used by the Stoffelen appendix LUT.
    """
    c = Circuit(5)
    n0 = c.add("XOR", Signal(0), Signal(4))
    n1 = c.add("OR", Signal(0), Signal(1))
    y4 = c.add("XOR", n0, n1)
    n3 = c.add("XOR", Signal(3), Signal(4))
    n4 = c.add("OR", Signal(0), Signal(4))
    y3 = c.add("XOR", n3, n4)
    n6 = c.add("XOR", Signal(2), Signal(3))
    n7 = c.add("OR", Signal(3), Signal(4))
    y2 = c.add("XOR", n6, n7)
    n9 = c.add("OR", Signal(2), Signal(3))
    n10 = c.add("XOR", Signal(1), Signal(2))
    y1 = c.add("XOR", n9, n10)
    n12 = c.add("XOR", Signal(0), Signal(1))
    n13 = c.add("OR", Signal(1), Signal(2))
    y0 = c.add("XOR", n12, n13)
    c.set_outputs([y0, y1, y2, y3, y4])
    return c


def rectangle4_stoffelen_bitslice() -> Circuit:
    """RECTANGLE 4-bit S-box, Stoffelen bitslice k=12."""
    c = Circuit(4)
    t0 = c.add("NOT", Signal(2))
    t1 = c.add("OR", Signal(0), t0)
    t2 = c.add("XOR", Signal(3), t1)
    y2 = c.add("XOR", t2, Signal(1))
    t4 = c.add("OR", t0, t2)
    t5 = c.add("XOR", Signal(0), t4)
    y3 = c.add("XOR", t5, y2)
    t7 = c.add("OR", t2, y3)
    t8 = c.add("XOR", t7, t5)
    y0 = c.add("XOR", t8, Signal(2))
    t10 = c.add("OR", y0, y3)
    y1 = c.add("XOR", t10, t2)
    c.set_outputs([y0, y1, y2, y3])
    return c


def lut_from_circuit(c: Circuit) -> list[int]:
    return [c.eval(x) for x in range(1 << c.n_inputs)]
