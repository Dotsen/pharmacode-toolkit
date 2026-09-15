from __future__ import annotations

import numpy as np
import pytest

from pharmacode.encoding import encode
from pharmacode.imageops import flatten_background, otsu_mask, rotate_bound
from pharmacode.models import BarKind
from pharmacode.rendering import (
    NEGATIVE_KINDS,
    Distortion,
    RenderSpec,
    compose_scene,
    distort,
    render_bars,
    render_negative,
    render_value,
)


def dark_runs(row: np.ndarray) -> list[int]:
    """Lengths of consecutive dark (< 128) runs in one image row."""
    runs: list[int] = []
    count = 0
    for pixel in row:
        if pixel < 128:
            count += 1
        elif count:
            runs.append(count)
            count = 0
    if count:
        runs.append(count)
    return runs


def test_px_rounds_physical_sizes_at_dpi() -> None:
    spec = RenderSpec(dpi=300.0)
    assert spec.px(0.5) == 6 and spec.px(1.5) == 18 and spec.px(1.0) == 12
    assert spec.px(0.01) == 1  # never below one pixel


def test_render_bars_geometry_at_300_dpi() -> None:
    spec = RenderSpec(dpi=300.0)
    image = render_bars((BarKind.NARROW, BarKind.WIDE), spec)
    border = spec.px(6.0) + spec.px(2.0)
    assert image.shape == (spec.px(8.0) + 2 * border, 6 + 12 + 18 + 2 * border)
    middle = image[image.shape[0] // 2]
    assert dark_runs(middle) == [6, 18]
    assert middle[:border].min() == 255 and middle[-border:].min() == 255
    assert image.dtype == np.uint8


def test_render_value_uses_encoding() -> None:
    image = render_value(1234)
    expected = [RenderSpec().bar_width_px(kind) for kind in encode(1234)]
    assert dark_runs(image[image.shape[0] // 2]) == expected


def test_render_is_deterministic() -> None:
    assert np.array_equal(render_value(777), render_value(777))


def test_miniature_preset() -> None:
    spec = RenderSpec.miniature(dpi=600.0)
    assert (spec.narrow_mm, spec.wide_mm, spec.gap_mm, spec.height_mm) == (0.35, 1.0, 0.65, 6.0)
    assert spec.dpi == 600.0


def test_render_rejects_empty_sequence() -> None:
    with pytest.raises(ValueError):
        render_bars(())


def test_rotate_bound_exact_quarter_turns_are_lossless() -> None:
    image = render_value(1234)
    rotated = rotate_bound(image, 90)
    assert rotated.shape == image.shape[::-1]
    assert np.array_equal(rotate_bound(rotated, -90), image)
    assert np.array_equal(rotate_bound(image, 180), image[::-1, ::-1])


def test_rotate_bound_arbitrary_angle_expands_canvas_with_white_border() -> None:
    image = render_value(1234)
    rotated = rotate_bound(image, 7.0)
    assert rotated.shape[0] > image.shape[0] and rotated.shape[1] > image.shape[1]
    assert rotated[0, 0] == 255 and rotated[-1, -1] == 255


def test_distort_is_deterministic_for_a_seed() -> None:
    image = render_value(4711)
    distortion = Distortion(blur_sigma=1.2, noise_sigma=15.0, jpeg_quality=40)
    first = distort(image, distortion, np.random.default_rng(1))
    second = distort(image, distortion, np.random.default_rng(1))
    third = distort(image, distortion, np.random.default_rng(2))
    assert np.array_equal(first, second)
    assert not np.array_equal(first, third)
    assert first.dtype == np.uint8 and first.shape == image.shape


def test_distort_noise_requires_generator() -> None:
    with pytest.raises(ValueError):
        distort(render_value(3), Distortion(noise_sigma=5.0))


def test_distort_scale_and_contrast() -> None:
    image = render_value(99)
    scaled = distort(image, Distortion(scale_x=0.5, scale_y=2.0))
    assert scaled.shape == (image.shape[0] * 2, image.shape[1] // 2)
    faded = distort(image, Distortion(contrast=0.4))
    assert faded.max() <= 180 and faded.min() >= 76


def test_distort_illumination_darkens_right_side() -> None:
    image = render_value(99)
    lit = distort(image, Distortion(illumination_gradient=0.5))
    assert lit[0, 0] == 255 and 120 <= lit[0, -1] <= 135


def test_compose_scene_clips_and_keeps_darker_pixel() -> None:
    code = render_value(3)
    scene = compose_scene((100, 100), [(code, 80, 80), (code, -20, -20)])
    assert scene.shape == (100, 100)
    assert scene.min() == 0


def test_flatten_background_removes_gradient() -> None:
    image = distort(render_value(1234), Distortion(illumination_gradient=0.6))
    flat = flatten_background(image, 0.05)
    assert flat[0, 0] >= 245 and flat[0, -1] >= 245
    assert otsu_mask(flat).max() == 255


@pytest.mark.parametrize("kind", NEGATIVE_KINDS)
def test_render_negative_kinds(kind: str, rng: np.random.Generator) -> None:
    image = render_negative(kind, rng)
    assert image.shape == (400, 800) and image.dtype == np.uint8
    if kind != "blank":
        assert (image < 128).mean() > 0.01


def test_render_negative_rejects_unknown_kind(rng: np.random.Generator) -> None:
    with pytest.raises(ValueError):
        render_negative("qr", rng)
