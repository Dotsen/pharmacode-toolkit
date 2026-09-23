"""Light bars on a dark background, decoded with ``polarity`` light and auto."""

from __future__ import annotations

import numpy as np
import pytest

from pharmacode.models import DecoderConfig, ErrorCode
from pharmacode.pipeline import decode_image
from pharmacode.rendering import (
    NEGATIVE_KINDS,
    Distortion,
    RenderSpec,
    compose_scene,
    distort,
    render_negative,
    render_value,
)
from tests.conftest import single

VALUES = [4, 25, 1234, 12345, 131070]


def _inverted(value: int) -> np.ndarray:
    return 255 - render_value(value)


def _patch_on_page(value: int) -> np.ndarray:
    """An inverted code printed as a dark patch on a white page."""
    patch = _inverted(value)
    return compose_scene((patch.shape[0] + 200, patch.shape[1] + 200), [(patch, 100, 100)])


@pytest.mark.parametrize("value", VALUES)
@pytest.mark.parametrize("polarity", ["light", "auto"])
def test_inverted_code(value: int, polarity: str) -> None:
    config = DecoderConfig(dpi=300.0, polarity=polarity)
    detection = single(decode_image(_inverted(value), config))
    assert detection.value == value
    assert detection.polarity == "light"


@pytest.mark.parametrize("value", VALUES)
def test_inverted_patch_on_white_page(value: int) -> None:
    config = DecoderConfig(dpi=300.0, polarity="auto")
    detection = single(decode_image(_patch_on_page(value), config))
    assert detection.value == value and detection.polarity == "light"


def test_inverted_code_rotated_and_degraded() -> None:
    image = distort(
        _inverted(1234),
        Distortion(rotation_deg=90, blur_sigma=1.0, noise_sigma=10.0),
        np.random.default_rng(7),
    )
    detection = single(decode_image(image, DecoderConfig(dpi=300.0, polarity="auto")))
    assert 1234 in (detection.value, detection.mirror_value)


def test_dark_polarity_ignores_inverted_code() -> None:
    result = decode_image(_inverted(1234), DecoderConfig(dpi=300.0))
    assert not result.detections
    assert result.errors[0].code is ErrorCode.NO_CANDIDATES


def test_light_polarity_ignores_printed_code() -> None:
    result = decode_image(render_value(1234), DecoderConfig(dpi=300.0, polarity="light"))
    assert not result.detections


def test_auto_keeps_the_dark_result_for_a_printed_code() -> None:
    image = render_value(12345)
    dark = decode_image(image, DecoderConfig(dpi=300.0))
    auto = decode_image(image, DecoderConfig(dpi=300.0, polarity="auto"))
    assert auto == dark
    assert single(auto).polarity == "dark"


def test_auto_reports_no_candidates_on_a_blank_page() -> None:
    blank = np.full((300, 500), 250, dtype=np.uint8)
    result = decode_image(blank, DecoderConfig(polarity="auto"))
    assert [error.code for error in result.errors] == [ErrorCode.NO_CANDIDATES]


@pytest.mark.parametrize("kind", NEGATIVE_KINDS)
def test_auto_finds_nothing_in_negatives_either_way_round(kind: str, rng) -> None:
    for index in range(4):
        image = render_negative(kind, rng)
        for candidate in (image, 255 - image):
            result = decode_image(candidate, DecoderConfig(polarity="auto"))
            assert not result.detections, (kind, index, result.to_dict())


def _code_on_patch(value: int, margin_mm: float, invert: bool) -> np.ndarray:
    """A code with ``margin_mm`` of quiet zone on a patch surrounded by the opposite shade.

    Dark bars on a white patch inside a black page (a knockout on a dark carton),
    or its inverse: light bars on a black patch inside a white page.
    """
    code = render_value(value, RenderSpec(dpi=300.0, quiet_zone_mm=margin_mm, margin_mm=0.0))
    page = np.zeros((code.shape[0] + 200, code.shape[1] + 200), dtype=np.uint8)
    page[100 : 100 + code.shape[0], 100 : 100 + code.shape[1]] = code
    return 255 - page if invert else page


@pytest.mark.parametrize("invert", [False, True], ids=["knockout", "inverted"])
@pytest.mark.parametrize("value", [25, 1234, 131070])
def test_patch_edge_ends_the_quiet_zone(value: int, invert: bool) -> None:
    config = DecoderConfig(dpi=300.0, polarity="auto")
    nominal = single(decode_image(_code_on_patch(value, 6.0, invert), config))
    assert nominal.value == value
    assert "quiet_zone_below_nominal" not in nominal.warnings
    assert nominal.polarity == ("light" if invert else "dark")
    short = single(decode_image(_code_on_patch(value, 4.0, invert), config))
    assert short.value == value and "quiet_zone_below_nominal" in short.warnings
    too_short = decode_image(_code_on_patch(value, 2.0, invert), config)
    assert [error.code for error in too_short.errors] == [ErrorCode.QUIET_ZONE_VIOLATION]


@pytest.mark.parametrize("tilt", [-3, 3])
def test_patch_edge_on_a_tilted_code(tilt: float) -> None:
    image = distort(_code_on_patch(1234, 6.0, True), Distortion(rotation_deg=tilt))
    detection = single(decode_image(image, DecoderConfig(dpi=300.0, polarity="auto")))
    assert detection.value == 1234
