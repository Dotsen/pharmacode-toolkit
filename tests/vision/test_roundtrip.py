"""encode -> render -> segment -> decode on clean, upright images."""

from __future__ import annotations

import numpy as np
import pytest

from pharmacode.decoding import decode_bars
from pharmacode.encoding import MAX_VALUE, MIN_VALUE, encode
from pharmacode.models import BarSequence, DecoderConfig
from pharmacode.rendering import RenderSpec, render_value
from pharmacode.segmentation import extract_bars_from_upright

BOUNDARY_VALUES = [3, 4, 5, 6, 7, 8, 13, 25, 91, 100, 1234, 12345, 65535, 123456, 131070]
RANDOM_VALUES = sorted(
    int(v) for v in np.random.default_rng(20260919).integers(MIN_VALUE, MAX_VALUE + 1, 50)
)


@pytest.mark.parametrize("value", BOUNDARY_VALUES + RANDOM_VALUES)
@pytest.mark.parametrize("dpi", [150.0, 300.0, 600.0])
def test_clean_upright_roundtrip(value: int, dpi: float) -> None:
    image = render_value(value, RenderSpec(dpi=dpi))
    sequence = extract_bars_from_upright(image, DecoderConfig(dpi=dpi))
    assert isinstance(sequence, BarSequence), sequence
    assert sequence.kinds == encode(value)
    assert decode_bars(sequence.kinds)[0] == value


@pytest.mark.parametrize("value", BOUNDARY_VALUES)
def test_roundtrip_without_dpi(value: int) -> None:
    sequence = extract_bars_from_upright(render_value(value), DecoderConfig())
    assert isinstance(sequence, BarSequence), sequence
    assert decode_bars(sequence.kinds)[0] == value


@pytest.mark.parametrize("value", [25, 1234, 131070])
@pytest.mark.parametrize(
    "spec",
    [
        RenderSpec.miniature(dpi=600.0),
        RenderSpec(narrow_mm=0.4, wide_mm=1.3, gap_mm=0.9),
        RenderSpec(narrow_mm=0.7, wide_mm=2.5, gap_mm=2.5),
        RenderSpec(narrow_mm=0.7, wide_mm=1.3, gap_mm=1.0),
    ],
    ids=["miniature", "tolerance-min", "tolerance-max", "ratio-1.86"],
)
def test_roundtrip_across_laetus_tolerances(value: int, spec: RenderSpec) -> None:
    sequence = extract_bars_from_upright(render_value(value, spec), DecoderConfig(dpi=spec.dpi))
    assert isinstance(sequence, BarSequence), sequence
    assert decode_bars(sequence.kinds)[0] == value
