from __future__ import annotations

import pytest

from pharmacode.models import DecoderConfig
from pharmacode.pipeline import decode_image
from pharmacode.rendering import Distortion, distort, render_value
from tests.conftest import single

VALUES = [4, 25, 1234, 12345, 131070]


@pytest.mark.parametrize("value", VALUES)
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_quarter_turns(value: int, rotation: int) -> None:
    image = distort(render_value(value), Distortion(rotation_deg=rotation))
    detection = single(decode_image(image, DecoderConfig(dpi=300.0)))
    assert value in (detection.value, detection.mirror_value)
    assert detection.orientation_deg == pytest.approx(
        0.0 if rotation in (0, 180) else 90.0, abs=1.0
    )
    reads_forward = rotation in (0, 270)
    assert (detection.value if reads_forward else detection.mirror_value) == value


def test_half_turn_swaps_readings() -> None:
    upright = single(decode_image(render_value(1234)))
    turned = single(decode_image(distort(render_value(1234), Distortion(rotation_deg=180))))
    assert (turned.value, turned.mirror_value) == (upright.mirror_value, upright.value)


@pytest.mark.parametrize("tilt", [-5, -3, -1, 1, 3, 5])
@pytest.mark.parametrize("value", [1234, 65535])
def test_small_tilt(value: int, tilt: float) -> None:
    image = distort(render_value(value), Distortion(rotation_deg=tilt))
    detection = single(decode_image(image, DecoderConfig(dpi=300.0)))
    assert detection.value == value
    assert detection.orientation_deg == pytest.approx(-tilt, abs=1.0)


@pytest.mark.parametrize("tilt", [87, 93])
def test_tilt_near_vertical(tilt: float) -> None:
    image = distort(render_value(1234), Distortion(rotation_deg=tilt))
    detection = single(decode_image(image, DecoderConfig(dpi=300.0)))
    assert 1234 in (detection.value, detection.mirror_value)
