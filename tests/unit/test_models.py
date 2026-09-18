from __future__ import annotations

import json

import pytest

from pharmacode.models import (
    BarKind,
    BoundingBox,
    DecodedPharmacode,
    DecodeError,
    DecoderConfig,
    DecodeResult,
    ErrorCode,
    ImageInfo,
)


def test_error_codes_are_stable_strings() -> None:
    assert {code.value for code in ErrorCode} == {
        "INPUT_UNREADABLE",
        "INVALID_ARGUMENT",
        "NO_CANDIDATES",
        "TOO_FEW_BARS",
        "TOO_MANY_BARS",
        "WIDTH_CLASSES_NOT_SEPARABLE",
        "AMBIGUOUS_WIDTH",
        "QUIET_ZONE_VIOLATION",
        "INCONSISTENT_BAR_HEIGHT",
        "INCONSISTENT_GAPS",
    }


def test_result_serialises_to_contract() -> None:
    detection = DecodedPharmacode(
        bbox=BoundingBox(10, 20, 300, 80),
        orientation_deg=0.0,
        bars=(BarKind.NARROW, BarKind.WIDE),
        bar_widths_px=(6, 18),
        value=4,
        mirror_value=5,
        confidence=0.91,
        warnings=("quiet_zone_below_nominal",),
    )
    error = DecodeError(ErrorCode.QUIET_ZONE_VIOLATION, "left quiet zone too small", None)
    result = DecodeResult(ImageInfo("a.png", 640, 480, 300.0), (detection,), (error,))
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["version"]
    assert payload["image"] == {"path": "a.png", "width": 640, "height": 480, "dpi": 300.0}
    assert payload["detections"][0] == {
        "bbox": {"x": 10, "y": 20, "width": 300, "height": 80},
        "orientation_deg": 0.0,
        "bars": ["narrow", "wide"],
        "bar_widths_px": [6, 18],
        "value": 4,
        "mirror_value": 5,
        "confidence": 0.91,
        "warnings": ["quiet_zone_below_nominal"],
    }
    assert payload["errors"] == [
        {"code": "QUIET_ZONE_VIOLATION", "message": "left quiet zone too small", "bbox": None}
    ]
    assert result.ok is False


def test_result_ok_when_detections_and_no_errors() -> None:
    result = DecodeResult(ImageInfo(None, 1, 1, None), (), ())
    assert result.ok is False
    detection = DecodedPharmacode(
        BoundingBox(0, 0, 1, 1), 0.0, (BarKind.NARROW,) * 2, (1, 1), 3, 3, 1.0, ()
    )
    assert DecodeResult(ImageInfo(None, 1, 1, None), (detection,), ()).ok is True


def test_config_defaults_derive_from_laetus_ratios() -> None:
    config = DecoderConfig()
    assert config.min_bars == 2 and config.max_bars == 16
    assert config.physical_width_boundary_mm == 0.8
    assert config.quiet_zone_nominal_mm == 6.0
    assert config.max_spacing_factor == 3.0
    tuned = config.with_updates(dpi=300.0, min_bars=4)
    assert tuned.dpi == 300.0 and tuned.min_bars == 4 and config.dpi is None


def test_config_rejects_min_bars_below_two() -> None:
    with pytest.raises(ValueError, match="min_bars"):
        DecoderConfig(min_bars=1)
