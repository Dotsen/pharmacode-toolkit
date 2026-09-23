from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pharmacode.io import InputError, save_image
from pharmacode.models import DecoderConfig, ErrorCode
from pharmacode.pipeline import decode_file, decode_image
from pharmacode.rendering import Distortion, RenderSpec, distort, render_value


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


def test_decode_image_min_confidence_downgrades_a_weak_detection_to_an_error() -> None:
    # same tight-crop scene as test_quiet_zone_below_nominal_is_a_warning: it decodes with
    # confidence < 0.8 by default, so a 0.9 floor rejects it while a clean code stays intact.
    spec = RenderSpec()
    border = spec.px(6.0) + spec.px(2.0)
    code = render_value(1234, spec)
    trimmed = code[:, border - 50 : -(border - 50)]

    unfiltered = decode_image(trimmed, DecoderConfig(dpi=300.0))
    [detection] = unfiltered.detections
    assert detection.confidence < 0.9

    result = decode_image(trimmed, DecoderConfig(dpi=300.0, min_confidence=0.9))
    assert result.detections == (), result.to_dict()
    [error] = result.errors
    assert error.code is ErrorCode.LOW_CONFIDENCE
    assert error.bbox is not None
    assert "0.90" in error.message

    clean = decode_image(render_value(1234), DecoderConfig(dpi=300.0, min_confidence=0.9))
    assert clean.detections and clean.detections[0].value == 1234


def test_decode_file_auto_dpi_prefers_the_file_and_falls_back_to_config(tmp_path: Path) -> None:
    stored = tmp_path / "stored.png"
    plain = tmp_path / "plain.png"
    save_image(stored, render_value(1234), 300.0)
    save_image(plain, render_value(1234))
    fallback = DecoderConfig(dpi=250.0)
    from_file = decode_file(stored, fallback, auto_dpi=True)
    assert (from_file.image.dpi, from_file.image.dpi_source) == (300.0, "png-phys")
    assert from_file.image.path == str(stored)
    kept = decode_file(plain, fallback, auto_dpi=True)
    assert (kept.image.dpi, kept.image.dpi_source) == (250.0, "given")
    ignored = decode_file(stored, fallback)
    assert (ignored.image.dpi, ignored.image.dpi_source) == (250.0, "given")
    assert decode_file(plain).image.dpi_source is None


def test_decode_file_raises_input_error_for_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InputError):
        decode_file(tmp_path / "missing.png")
