from __future__ import annotations

import numpy as np

from pharmacode.models import DecoderConfig
from pharmacode.pipeline import decode_image
from pharmacode.rendering import render_value
from pharmacode.visualization import annotate


def test_annotate_draws_on_a_copy_in_colour() -> None:
    image = render_value(1234)
    result = decode_image(image, DecoderConfig(dpi=300.0))
    canvas = annotate(image, result)
    assert canvas.shape == (*image.shape, 3) and canvas.dtype == np.uint8
    assert np.array_equal(image, render_value(1234))  # input untouched
    green = (canvas[..., 1] > 200) & (canvas[..., 0] < 100) & (canvas[..., 2] < 100)
    assert green.any()


def test_annotate_marks_errors_in_red() -> None:
    image = render_value(1234)[:, 85:-85]
    result = decode_image(image, DecoderConfig(dpi=300.0))
    canvas = annotate(image, result)
    red = (canvas[..., 2] > 200) & (canvas[..., 1] < 100) & (canvas[..., 0] < 100)
    assert red.any()
