from __future__ import annotations

import pytest

from pharmacode.models import DecoderConfig
from pharmacode.pipeline import decode_image
from pharmacode.rendering import Distortion, RenderSpec, distort, render_value
from tests.conftest import single

TWO_CLASS_VALUES = [25, 1234, 12345, 123456]


@pytest.mark.parametrize("dpi", [150.0, 300.0, 600.0])
@pytest.mark.parametrize("value", [3, 25, 1234, 131070])
def test_pipeline_across_dpi(value: int, dpi: float) -> None:
    detection = single(
        decode_image(render_value(value, RenderSpec(dpi=dpi)), DecoderConfig(dpi=dpi))
    )
    assert detection.value == value


@pytest.mark.parametrize("scale", [(0.7, 0.7), (1.3, 1.3), (0.7, 1.3), (1.3, 0.7)])
@pytest.mark.parametrize("value", TWO_CLASS_VALUES)
def test_non_uniform_scale_without_dpi(value: int, scale: tuple[float, float]) -> None:
    image = distort(render_value(value), Distortion(scale_x=scale[0], scale_y=scale[1]))
    assert single(decode_image(image)).value == value


def test_miniature_at_600_dpi() -> None:
    spec = RenderSpec.miniature(dpi=600.0)
    for value in (3, 1234, 131070):
        assert (
            single(decode_image(render_value(value, spec), DecoderConfig(dpi=600.0))).value == value
        )
