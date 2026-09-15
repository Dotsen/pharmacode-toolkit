"""Synthetic Pharmacode images with physical dimensions.

The renderer is the only source of test fixtures and benchmark images, so it
must be deterministic: same inputs, same pixels.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from pharmacode.encoding import encode
from pharmacode.models import BarKind


@dataclass(frozen=True)
class RenderSpec:
    """Physical layout of a rendered code. Defaults are the Laetus standard one-track code."""

    dpi: float = 300.0
    narrow_mm: float = 0.5
    wide_mm: float = 1.5
    gap_mm: float = 1.0
    height_mm: float = 8.0
    quiet_zone_mm: float = 6.0
    margin_mm: float = 2.0
    foreground: int = 0
    background: int = 255

    @classmethod
    def miniature(cls, **overrides: Any) -> RenderSpec:
        """Laetus miniature one-track dimensions."""
        return cls(narrow_mm=0.35, wide_mm=1.0, gap_mm=0.65, height_mm=6.0, **overrides)

    def with_updates(self, **changes: Any) -> RenderSpec:
        return replace(self, **changes)

    def px(self, mm: float) -> int:
        """Millimetres to whole pixels at this DPI, never below one pixel."""
        return max(1, round(mm * self.dpi / 25.4))

    def bar_width_px(self, kind: BarKind) -> int:
        return self.px(self.wide_mm if kind is BarKind.WIDE else self.narrow_mm)


def render_bars(bars: Sequence[BarKind], spec: RenderSpec | None = None) -> np.ndarray:
    """Render a bar sequence (most significant bar on the left) as a grayscale image.

    The canvas holds the code, the quiet zone on every side and an extra margin.
    """
    if spec is None:
        spec = RenderSpec()
    if not bars:
        raise ValueError("cannot render an empty bar sequence")
    widths = [spec.bar_width_px(kind) for kind in bars]
    gap = spec.px(spec.gap_mm)
    border = spec.px(spec.quiet_zone_mm) + spec.px(spec.margin_mm)
    height = spec.px(spec.height_mm)
    code_width = sum(widths) + gap * (len(widths) - 1)
    image = np.full((height + 2 * border, code_width + 2 * border), spec.background, dtype=np.uint8)
    x = border
    for width in widths:
        image[border : border + height, x : x + width] = spec.foreground
        x += width + gap
    return image


def render_value(value: int, spec: RenderSpec | None = None) -> np.ndarray:
    """Render the code for ``value`` (see :func:`pharmacode.encoding.encode`)."""
    if spec is None:
        spec = RenderSpec()
    return render_bars(encode(value), spec)
