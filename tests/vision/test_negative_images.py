# tests/vision/test_negative_images.py
"""Images without a Pharmacode must never yield a value, and must say why."""

from __future__ import annotations

import numpy as np
import pytest

from pharmacode.models import DecoderConfig, ErrorCode
from pharmacode.pipeline import decode_image
from pharmacode.rendering import NEGATIVE_KINDS, render_negative

DIAGNOSTIC_CODES = {
    ErrorCode.NO_CANDIDATES,
    ErrorCode.TOO_FEW_BARS,
    ErrorCode.TOO_MANY_BARS,
    ErrorCode.WIDTH_CLASSES_NOT_SEPARABLE,
    ErrorCode.AMBIGUOUS_WIDTH,
    ErrorCode.QUIET_ZONE_VIOLATION,
    ErrorCode.INCONSISTENT_BAR_HEIGHT,
    ErrorCode.INCONSISTENT_GAPS,
}


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("kind", NEGATIVE_KINDS)
def test_negative_image_yields_no_value(kind: str, seed: int) -> None:
    image = render_negative(kind, np.random.default_rng(seed))
    result = decode_image(image, DecoderConfig())
    assert result.detections == (), [d.to_dict() for d in result.detections]
    assert result.errors and {e.code for e in result.errors} <= DIAGNOSTIC_CODES


def test_blank_page_is_no_candidates() -> None:
    result = decode_image(render_negative("blank", np.random.default_rng(3)))
    assert [e.code for e in result.errors] == [ErrorCode.NO_CANDIDATES]


def test_linear_barcode_is_rejected_for_its_geometry() -> None:
    result = decode_image(render_negative("linear_barcode", np.random.default_rng(1)))
    codes = {e.code for e in result.errors}
    assert codes & {
        ErrorCode.INCONSISTENT_GAPS,
        ErrorCode.WIDTH_CLASSES_NOT_SEPARABLE,
        ErrorCode.AMBIGUOUS_WIDTH,
        ErrorCode.TOO_MANY_BARS,
    }
