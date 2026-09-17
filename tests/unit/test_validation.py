# tests/unit/test_validation.py
"""Bar-count and width-class limits produce specific error codes."""

from __future__ import annotations

import numpy as np

from pharmacode.models import BarKind, DecoderConfig, ErrorCode
from pharmacode.pipeline import decode_image
from pharmacode.rendering import RenderSpec, render_bars


def strip(widths: list[int], gap: int = 12, height: int = 94, border: int = 95) -> np.ndarray:
    """Draw bars of arbitrary pixel widths, Laetus-like spacing, white border."""
    total = sum(widths) + gap * (len(widths) - 1)
    image = np.full((height + 2 * border, total + 2 * border), 255, np.uint8)
    x = border
    for width in widths:
        image[border : border + height, x : x + width] = 0
        x += width + gap
    return image


def test_seventeen_bars_is_too_many() -> None:
    result = decode_image(render_bars((BarKind.NARROW,) * 17), DecoderConfig(dpi=300.0))
    assert [e.code for e in result.errors] == [ErrorCode.TOO_MANY_BARS]


def test_single_bar_is_no_candidate() -> None:
    result = decode_image(render_bars((BarKind.WIDE,), RenderSpec()), DecoderConfig(dpi=300.0))
    assert [e.code for e in result.errors] == [ErrorCode.NO_CANDIDATES]


def test_min_bars_from_config() -> None:
    result = decode_image(render_bars((BarKind.NARROW, BarKind.WIDE)), DecoderConfig(min_bars=4))
    assert [e.code for e in result.errors] == [ErrorCode.TOO_FEW_BARS]


def test_smeared_widths_are_not_separable() -> None:
    result = decode_image(strip([6, 8, 10, 12, 14, 16, 18]), DecoderConfig(dpi=300.0))
    assert result.detections == ()
    assert result.errors and {e.code for e in result.errors} <= {
        ErrorCode.WIDTH_CLASSES_NOT_SEPARABLE,
        ErrorCode.AMBIGUOUS_WIDTH,
    }


def test_bar_on_the_boundary_is_ambiguous() -> None:
    result = decode_image(strip([6, 18, 6, 10, 18]), DecoderConfig(dpi=300.0))
    assert result.detections == ()
    assert result.errors and {e.code for e in result.errors} <= {
        ErrorCode.AMBIGUOUS_WIDTH,
        ErrorCode.WIDTH_CLASSES_NOT_SEPARABLE,
    }


def test_uneven_gaps_are_rejected() -> None:
    image = strip([6, 18, 6, 18])
    image[:, :] = 255
    x = 95
    for width, gap in ((6, 12), (18, 40), (6, 12), (18, 0)):
        image[95 : 95 + 94, x : x + width] = 0
        x += width + gap
    result = decode_image(image, DecoderConfig(dpi=300.0))
    assert result.detections == () and {e.code for e in result.errors} == {
        ErrorCode.INCONSISTENT_GAPS
    }
