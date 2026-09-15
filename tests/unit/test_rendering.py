from __future__ import annotations

import numpy as np
import pytest

from pharmacode.encoding import encode
from pharmacode.models import BarKind
from pharmacode.rendering import RenderSpec, render_bars, render_value


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
