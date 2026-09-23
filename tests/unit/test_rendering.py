from __future__ import annotations

from xml.etree import ElementTree

import numpy as np
import pytest

from pharmacode.encoding import encode
from pharmacode.imageops import flatten_background, otsu_mask, rotate_bound
from pharmacode.models import BarKind, DecoderConfig
from pharmacode.pipeline import decode_image
from pharmacode.rendering import (
    NEGATIVE_KINDS,
    Distortion,
    RenderSpec,
    compose_scene,
    distort,
    render_bars,
    render_negative,
    render_svg,
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


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scale_x": 0.0},
        {"scale_y": 0.0},
        {"blur_sigma": -1.0},
        {"noise_sigma": -1.0},
        {"contrast": -1.0},
        {"illumination_gradient": 1.5},
        {"jpeg_quality": 0},
        {"perspective_deg": 45.0},
    ],
)
def test_distortion_rejects_invalid_parameters(kwargs: dict[str, float | int]) -> None:
    with pytest.raises(ValueError):
        Distortion(**kwargs)


def test_distortion_accepts_default_and_fully_valid_values() -> None:
    assert Distortion() == Distortion()
    Distortion(
        rotation_deg=10.0,
        scale_x=0.5,
        scale_y=2.0,
        perspective_deg=-30.0,
        blur_sigma=1.0,
        noise_sigma=5.0,
        contrast=0.5,
        illumination_gradient=0.5,
        jpeg_quality=50,
    )


SVG = "{http://www.w3.org/2000/svg}"


def _rasterise(document: str, dpi: float) -> np.ndarray:
    """Paint an SVG made of axis-aligned rects (as render_svg writes it) at ``dpi``."""
    root = ElementTree.fromstring(document)
    scale = dpi / 25.4
    _, _, width, height = (float(v) for v in root.attrib["viewBox"].split())
    canvas = np.full((round(height * scale), round(width * scale)), 255, dtype=np.uint8)
    for rect in root.iter(f"{SVG}rect"):
        x, y = float(rect.get("x", 0)), float(rect.get("y", 0))
        w, h = float(rect.attrib["width"]), float(rect.attrib["height"])
        fill = rect.get("fill") or "#000000"
        x0, y0 = round(x * scale), round(y * scale)
        canvas[y0 : y0 + round(h * scale), x0 : x0 + round(w * scale)] = int(fill[1:3], 16)
    return canvas


def test_render_svg_is_in_exact_millimetres() -> None:
    document = render_svg(encode(1234), title="Pharmacode 1234")
    root = ElementTree.fromstring(document)
    assert (root.attrib["width"], root.attrib["height"]) == ("35mm", "24mm")
    assert root.attrib["viewBox"] == "0 0 35 24"
    assert root.find(f"{SVG}title").text == "Pharmacode 1234"
    bars = list(root.find(f"{SVG}g").iter(f"{SVG}rect"))
    assert [float(bar.attrib["width"]) for bar in bars] == [
        1.5 if kind is BarKind.WIDE else 0.5 for kind in encode(1234)
    ]
    assert float(bars[1].attrib["x"]) - float(bars[0].attrib["x"]) == 1.5  # 0.5 bar + 1 mm gap


def test_render_svg_miniature_and_colours() -> None:
    spec = RenderSpec.miniature(foreground=40, background=250)
    root = ElementTree.fromstring(render_svg(encode(25), spec))
    group = root.find(f"{SVG}g")
    assert group.attrib["fill"] == "#282828"
    assert root.find(f"{SVG}rect").attrib["fill"] == "#fafafa"
    assert [float(bar.attrib["width"]) for bar in group] == [1.0, 0.35, 1.0, 0.35]


def test_render_svg_escapes_the_title() -> None:
    document = render_svg(encode(3), title="<a & b>")
    assert "<title>&lt;a &amp; b&gt;</title>" in document


def test_render_svg_rejects_an_empty_sequence() -> None:
    with pytest.raises(ValueError):
        render_svg(())


@pytest.mark.parametrize("value", [3, 25, 1234, 12345, 131070])
@pytest.mark.parametrize("miniature", [False, True], ids=["standard", "miniature"])
def test_render_svg_decodes_once_rasterised(value: int, miniature: bool) -> None:
    spec = RenderSpec.miniature() if miniature else RenderSpec()
    image = _rasterise(render_svg(encode(value), spec), 600.0)
    result = decode_image(image, DecoderConfig(dpi=600.0))
    assert [d.value for d in result.detections] == [value], result.to_dict()
