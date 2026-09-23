from __future__ import annotations

import pytest

from pharmacode.geometry import QUIET_ZONE_MIN_MM, geometry_report
from pharmacode.models import BarKind, BoundingBox, DecodedPharmacode, DecoderConfig
from pharmacode.pipeline import decode_image
from pharmacode.rendering import RenderSpec, render_value
from tests.conftest import single

N, W = BarKind.NARROW, BarKind.WIDE


def _detection(widths: tuple[int, ...], gaps: tuple[int, ...], quiet=(90, 90)) -> DecodedPharmacode:
    kinds = tuple(W if width > 10 else N for width in widths)
    return DecodedPharmacode(
        bbox=BoundingBox(0, 0, 10, 10),
        orientation_deg=0.0,
        bars=kinds,
        bar_widths_px=widths,
        value=0,
        mirror_value=0,
        confidence=1.0,
        gap_widths_px=gaps,
        quiet_zone_px=quiet,
        bar_height_px=94,
    )


def test_without_dpi_only_pixels_are_reported() -> None:
    report = geometry_report(_detection((6, 18), (12,)), None)
    assert report["bar_widths_px"] == [6, 18] and report["gap_widths_px"] == [12]
    assert report["bar_widths_mm"] is None and report["out_of_tolerance"] is None
    assert report["variant"] is None


def test_nominal_standard_code_is_within_tolerance() -> None:
    report = geometry_report(_detection((6, 18, 6), (12, 12)), 300.0)
    assert report["variant"] == "standard"
    assert report["out_of_tolerance"] == []
    assert report["bar_widths_mm"] == [0.508, 1.524, 0.508]
    assert report["pixel_mm"] == pytest.approx(0.085, abs=0.001)


def test_nominal_miniature_code_is_recognised() -> None:
    report = geometry_report(_detection((8, 24, 8), (15, 15), quiet=(150, 150)), 600.0)
    assert report["variant"] == "miniature" and report["out_of_tolerance"] == []


def test_oversized_bars_and_gaps_are_listed() -> None:
    report = geometry_report(_detection((9, 33, 6), (12, 31)), 300.0)
    assert report["variant"] == "standard"
    flagged = {(item["element"], item["index"]) for item in report["out_of_tolerance"]}
    assert flagged == {("narrow_bar", 0), ("wide_bar", 1), ("gap", 1)}
    assert report["out_of_tolerance"][0]["range_mm"] == [0.4, 0.7]


def test_short_quiet_zone_is_listed_per_side() -> None:
    report = geometry_report(_detection((6, 18), (12,), quiet=(90, 40)), 300.0)
    assert report["out_of_tolerance"] == [
        {"element": "quiet_zone", "index": 1, "mm": 3.387, "range_mm": [QUIET_ZONE_MIN_MM, None]}
    ]


@pytest.mark.parametrize(
    ("spec", "variant"),
    [
        (RenderSpec(dpi=600.0), "standard"),
        (RenderSpec.miniature(dpi=600.0), "miniature"),
        (RenderSpec(dpi=600.0, narrow_mm=0.6, wide_mm=2.2, gap_mm=1.8), "standard"),
    ],
    ids=["standard", "miniature", "wide-standard"],
)
def test_rendered_codes_measure_within_their_variant(spec: RenderSpec, variant: str) -> None:
    detection = single(decode_image(render_value(12345, spec), DecoderConfig(dpi=600.0)))
    report = geometry_report(detection, 600.0)
    assert report["variant"] == variant
    assert [item for item in report["out_of_tolerance"] if item["element"] != "quiet_zone"] == []
    assert report["bar_height_mm"] == pytest.approx(spec.height_mm, abs=0.1)


def test_geometry_is_only_in_the_json_on_request() -> None:
    result = decode_image(render_value(1234), DecoderConfig(dpi=300.0))
    assert "geometry" not in result.to_dict()["detections"][0]
    geometry = result.to_dict(include_geometry=True)["detections"][0]["geometry"]
    assert geometry["variant"] == "standard" and geometry["quiet_zone_px"][0] > 0
