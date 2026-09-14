"""Specification tests for one-track Pharmacode value encoding.

Vectors were derived from the public description of the format (Laetus guide,
Wikipedia) and cross-checked against independent encoders. N = narrow, W = wide,
most significant bar on the left.
"""

from __future__ import annotations

import pytest

from pharmacode.encoding import MAX_BARS, MAX_VALUE, MIN_BARS, MIN_VALUE, bars_to_value, encode
from pharmacode.models import BarKind

VECTORS = [
    (3, "NN"),
    (4, "NW"),
    (5, "WN"),
    (6, "WW"),
    (7, "NNN"),
    (8, "NNW"),
    (9, "NWN"),
    (10, "NWW"),
    (13, "WWN"),
    (25, "WNWN"),
    (91, "NWWWNN"),
    (100, "WNNWNW"),
    (1234, "NNWWNWNNWW"),
    (12345, "WNNNNNNWWWNWN"),
    (65535, "N" * 16),
    (123456, "WWWNNNWNNWNNNNNW"),
    (131070, "W" * 16),
]


def bars(text: str) -> tuple[BarKind, ...]:
    return tuple(BarKind.WIDE if ch == "W" else BarKind.NARROW for ch in text)


def test_constants_match_public_format() -> None:
    assert (MIN_VALUE, MAX_VALUE, MIN_BARS, MAX_BARS) == (3, 131070, 2, 16)


@pytest.mark.parametrize(("value", "text"), VECTORS)
def test_encode_matches_vectors(value: int, text: str) -> None:
    assert encode(value) == bars(text)


@pytest.mark.parametrize(("value", "text"), VECTORS)
def test_bars_to_value_matches_vectors(value: int, text: str) -> None:
    assert bars_to_value(bars(text)) == value


@pytest.mark.parametrize("value", range(MIN_VALUE, 2000))
def test_round_trip_low_range(value: int) -> None:
    assert bars_to_value(encode(value)) == value


@pytest.mark.parametrize("value", [MAX_VALUE - 1, MAX_VALUE, 65536, 131069, 98304])
def test_round_trip_high_values(value: int) -> None:
    assert bars_to_value(encode(value)) == value


def test_bar_count_grows_with_value() -> None:
    assert len(encode(MIN_VALUE)) == MIN_BARS
    assert len(encode(MAX_VALUE)) == MAX_BARS
    assert all(len(encode(v)) <= MAX_BARS for v in range(MIN_VALUE, MAX_VALUE + 1, 997))


@pytest.mark.parametrize("value", [0, 1, 2, MAX_VALUE + 1, -5])
def test_encode_rejects_out_of_range(value: int) -> None:
    with pytest.raises(ValueError):
        encode(value)


@pytest.mark.parametrize("value", [3.0, "3", True, None])
def test_encode_rejects_non_integers(value: object) -> None:
    with pytest.raises(TypeError):
        encode(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("text", ["", "N", "W", "N" * 17])
def test_bars_to_value_rejects_bad_count(text: str) -> None:
    with pytest.raises(ValueError):
        bars_to_value(bars(text))
