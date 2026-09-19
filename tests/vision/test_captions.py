"""A human-readable caption printed under (or above) a code shares its candidate box.

The box extends 0.5 x the bar length across the code axis (see
``detection.candidate_from_chain``), so a caption close to the bars falls
inside it. As long as a white gap separates the caption from the bars, the
fixed ``measure_heights``/``bar_profile`` must ignore it; a caption that
touches the bars is a documented limitation and must fail cleanly instead of
decoding a wrong value.
"""

from __future__ import annotations

import cv2
import numpy as np

from pharmacode.models import DecoderConfig
from pharmacode.pipeline import decode_image
from pharmacode.rendering import RenderSpec, render_value
from tests.conftest import single

VALUE = 123456
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 1.2
FONT_THICKNESS = 2


def _caption_ink_offsets(text: str) -> tuple[int, int]:
    """Blank padding, in rows, between cv2.putText's nominal box and the glyphs' actual ink.

    Returns ``(top_offset, bottom_offset)``: rows of white space cv2.putText
    leaves above the topmost inked row, and below the bottom-most inked row,
    of its nominal ``(width, height)`` box. Digits carry no ascenders or
    descenders, so HERSHEY_SIMPLEX leaves several blank rows on both sides —
    real pixel gaps must account for this to place a caption within a
    specific distance of the bars.
    """
    (width, height), baseline = cv2.getTextSize(text, FONT, FONT_SCALE, FONT_THICKNESS)
    pad = 4
    probe = np.full((height + baseline + 2 * pad, width + 2 * pad), 255, dtype=np.uint8)
    cv2.putText(probe, text, (pad, pad + height), FONT, FONT_SCALE, 0, FONT_THICKNESS, cv2.LINE_AA)
    ink_rows = np.flatnonzero((probe < 128).any(axis=1))
    top_offset = int(ink_rows[0]) - pad
    bottom_offset = (pad + height + baseline - 1) - int(ink_rows[-1])
    return top_offset, bottom_offset


def _with_caption(gap_mm: float, *, above: bool) -> np.ndarray:
    """Render VALUE's bars with its own decimal value printed as a caption.

    The caption is horizontally centred and its actual ink (not cv2's padded
    nominal text box) is separated from the bars' actual ink by ``gap_mm`` of
    white space, below them or above (``gap_mm=0`` makes the caption touch
    the bars with no white gap at all).
    """
    spec = RenderSpec()
    image = render_value(VALUE, spec).copy()
    text = str(VALUE)
    (text_width, text_height), baseline = cv2.getTextSize(text, FONT, FONT_SCALE, FONT_THICKNESS)
    top_offset, bottom_offset = _caption_ink_offsets(text)
    gap_px = spec.px(gap_mm) if gap_mm > 0 else 0
    bar_top = spec.px(spec.quiet_zone_mm) + spec.px(spec.margin_mm)
    bar_bottom = bar_top + spec.px(spec.height_mm) - 1
    x = (image.shape[1] - text_width) // 2
    if above:
        y = bar_top - gap_px - baseline + bottom_offset
    else:
        y = bar_bottom + 1 + gap_px + text_height - top_offset
    cv2.putText(image, text, (x, y), FONT, FONT_SCALE, 0, FONT_THICKNESS, cv2.LINE_AA)
    return image


def test_caption_below_bars_separated_by_a_gap_decodes_normally() -> None:
    image = _with_caption(gap_mm=1.5, above=False)
    for config in (DecoderConfig(dpi=300.0), DecoderConfig()):
        detection = single(decode_image(image, config))
        assert detection.value == VALUE
        assert not any("quiet_zone" in warning for warning in detection.warnings)


def test_caption_above_bars_separated_by_a_gap_decodes_normally() -> None:
    image = _with_caption(gap_mm=1.5, above=True)
    for config in (DecoderConfig(dpi=300.0), DecoderConfig()):
        detection = single(decode_image(image, config))
        assert detection.value == VALUE
        assert not any("quiet_zone" in warning for warning in detection.warnings)


def test_caption_touching_bars_with_no_gap_fails_cleanly() -> None:
    """Documented limitation: a caption with no white gap is measured as part of the bar."""
    image = _with_caption(gap_mm=0.0, above=False)
    result = decode_image(image, DecoderConfig(dpi=300.0))
    assert not result.detections, [d.to_dict() for d in result.detections]
    assert result.errors, "expected a DecodeError, got neither a detection nor an error"
