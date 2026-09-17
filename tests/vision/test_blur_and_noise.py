from __future__ import annotations

import numpy as np
import pytest

from pharmacode.models import DecoderConfig
from pharmacode.pipeline import decode_image
from pharmacode.rendering import Distortion, RenderSpec, distort, render_value
from tests.conftest import SEED, single

VALUES = [25, 1234, 12345]

CONDITIONS = {
    "blur-1": Distortion(blur_sigma=1.0),
    "blur-2": Distortion(blur_sigma=2.0),
    "noise-10": Distortion(noise_sigma=10.0),
    "noise-25": Distortion(noise_sigma=25.0),
    "jpeg-50": Distortion(jpeg_quality=50),
    "jpeg-30": Distortion(jpeg_quality=30),
    "contrast-0.4": Distortion(contrast=0.4),
    "illumination-0.5": Distortion(illumination_gradient=0.5),
    "scan-like": Distortion(blur_sigma=1.0, noise_sigma=10.0, jpeg_quality=60),
    "harsh": Distortion(blur_sigma=1.5, noise_sigma=20.0, contrast=0.6, jpeg_quality=40),
}


@pytest.mark.parametrize("value", VALUES)
@pytest.mark.parametrize("name", list(CONDITIONS))
def test_degraded_code_decodes(value: int, name: str) -> None:
    image = distort(render_value(value), CONDITIONS[name], np.random.default_rng(SEED))
    detection = single(decode_image(image, DecoderConfig(dpi=300.0)))
    assert detection.value == value
    assert detection.confidence >= 0.3


@pytest.mark.parametrize("value", VALUES)
def test_mild_blur_at_150_dpi(value: int) -> None:
    image = distort(render_value(value, RenderSpec(dpi=150.0)), Distortion(blur_sigma=0.7))
    assert single(decode_image(image, DecoderConfig(dpi=150.0))).value == value


def test_degradation_lowers_confidence_monotonically() -> None:
    clean = single(decode_image(render_value(1234), DecoderConfig(dpi=300.0))).confidence
    harsh = distort(render_value(1234), CONDITIONS["harsh"], np.random.default_rng(SEED))
    degraded = single(decode_image(harsh, DecoderConfig(dpi=300.0))).confidence
    assert clean >= degraded


def test_noise_seeds_do_not_change_the_value() -> None:
    for seed in range(5):
        image = distort(
            render_value(65535), Distortion(noise_sigma=20.0), np.random.default_rng(seed)
        )
        assert single(decode_image(image, DecoderConfig(dpi=300.0))).value == 65535
