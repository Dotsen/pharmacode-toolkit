from __future__ import annotations

import random

from pharmacode.decoding import decode_bars
from pharmacode.encoding import MAX_VALUE, MIN_VALUE, encode


def test_mirror_of_mirror_is_identity() -> None:
    rng = random.Random(20260919)
    for _ in range(500):
        value = rng.randint(MIN_VALUE, MAX_VALUE)
        primary, mirror = decode_bars(encode(value))
        assert primary == value
        assert decode_bars(encode(mirror)) == (mirror, value)


def test_palindromes_have_equal_readings() -> None:
    for value in (3, 6, 7, 9, 65535, 131070):
        primary, mirror = decode_bars(encode(value))
        assert primary == mirror == value


def test_reverse_reading_is_independent_of_plausibility() -> None:
    primary, mirror = decode_bars(encode(8))
    assert (primary, mirror) == (8, 11)


def test_laetus_guide_direction_example() -> None:
    """Laetus guide: one pattern reads 25 left-to-right and 20 right-to-left."""
    assert decode_bars(encode(25)) == (25, 20)
    assert decode_bars(encode(20)) == (20, 25)
