"""ANF utilities for small S-boxes."""


def infer_n(lut: list[int]) -> int:
    n = 0
    while (1 << n) < len(lut):
        n += 1
    if 1 << n != len(lut):
        raise ValueError("LUT length must be a power of two")
    return n


def infer_m(lut: list[int]) -> int:
    return max(1, max(lut).bit_length())


def output_truths(lut: list[int], m: int | None = None) -> list[list[int]]:
    if m is None:
        m = infer_m(lut)
    return [[(y >> bit) & 1 for y in lut] for bit in range(m)]


def truth_to_anf(truth: list[int]) -> list[int]:
    coeff = truth[:]
    n = infer_n(truth)
    for i in range(n):
        step = 1 << i
        for mask in range(1 << n):
            if mask & step:
                coeff[mask] ^= coeff[mask ^ step]
    return [mask for mask, c in enumerate(coeff) if c]


def sbox_anf(lut: list[int], m: int | None = None) -> list[list[int]]:
    return [truth_to_anf(t) for t in output_truths(lut, m)]

