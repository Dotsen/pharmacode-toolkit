from __future__ import annotations

import numpy as np

from pharmacode.models import DecoderConfig, ErrorCode
from pharmacode.pipeline import decode_image
from pharmacode.rendering import Distortion, distort, render_value


def test_decode_image_clean_code() -> None:
    result = decode_image(render_value(1234), DecoderConfig(dpi=300.0), path="x.png")
    assert result.ok and result.image.path == "x.png" and result.image.dpi == 300.0
    [detection] = result.detections
    assert (detection.value, detection.mirror_value) == (1234, 1835)
    assert detection.confidence > 0.8 and detection.orientation_deg == 0.0
    assert len(detection.bar_rects) == 10


def test_decode_image_accepts_bgr_input() -> None:
    gray = render_value(25)
    bgr = np.stack([gray] * 3, axis=-1)
    assert decode_image(bgr).detections[0].value == 25


def test_decode_image_blank_reports_no_candidates() -> None:
    result = decode_image(np.full((200, 300), 255, np.uint8))
    assert not result.ok and [e.code for e in result.errors] == [ErrorCode.NO_CANDIDATES]


def test_decode_image_quarter_turn_swaps_readings() -> None:
    upright = decode_image(render_value(4)).detections[0]
    turned = decode_image(distort(render_value(4), Distortion(rotation_deg=90))).detections[0]
    assert (upright.value, upright.mirror_value) == (4, 5)
    assert (turned.value, turned.mirror_value) == (5, 4)
    assert turned.orientation_deg == 90.0


def test_decode_image_error_carries_candidate_bbox() -> None:
    image = render_value(1234)[:, 85:-85]  # keeps 10 px beyond the bars
    result = decode_image(image, DecoderConfig(dpi=300.0))
    assert not result.detections
    [error] = result.errors
    assert error.code is ErrorCode.QUIET_ZONE_VIOLATION and error.bbox is not None
