from __future__ import annotations

import pytest

from pharmacode.models import DecoderConfig
from pharmacode.pipeline import decode_image
from pharmacode.rendering import Distortion, distort, render_value
from tests.conftest import single


@pytest.mark.parametrize("angle", [2.0, 3.0, 5.0])
@pytest.mark.parametrize("value", [25, 1234, 123456])
def test_small_perspective(value: int, angle: float) -> None:
    image = distort(render_value(value), Distortion(perspective_deg=angle))
    assert single(decode_image(image, DecoderConfig(dpi=300.0))).value == value


def test_perspective_with_rotation() -> None:
    image = distort(render_value(1234), Distortion(perspective_deg=3.0, rotation_deg=90))
    detection = single(decode_image(image, DecoderConfig(dpi=300.0)))
    assert 1234 in (detection.value, detection.mirror_value)
