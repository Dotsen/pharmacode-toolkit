"""Synthetic Pharmacode images with physical dimensions.

The renderer is the only source of test fixtures and benchmark images, so it
must be deterministic: same inputs, same pixels.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any
from xml.sax.saxutils import escape

import cv2
import numpy as np

from pharmacode.encoding import encode
from pharmacode.imageops import rotate_bound
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


def _mm(value: float) -> str:
    """A length in mm for SVG: at most 4 decimals, no trailing zeros."""
    return f"{value:.4f}".rstrip("0").rstrip(".")


def render_svg(bars: Sequence[BarKind], spec: RenderSpec | None = None, title: str = "") -> str:
    """Render a bar sequence as an SVG document in exact millimetres.

    Same layout as :func:`render_bars` (most significant bar on the left,
    quiet zone and margin on every side) but with no pixel rounding: the
    document's ``width`` and ``height`` are in mm and one user unit is 1 mm,
    so it prints at its physical size. ``spec.dpi`` is not used.
    """
    if spec is None:
        spec = RenderSpec()
    if not bars:
        raise ValueError("cannot render an empty bar sequence")
    widths = [spec.wide_mm if kind is BarKind.WIDE else spec.narrow_mm for kind in bars]
    border = spec.quiet_zone_mm + spec.margin_mm
    width = sum(widths) + spec.gap_mm * (len(widths) - 1) + 2 * border
    height = spec.height_mm + 2 * border
    foreground = f"#{spec.foreground:02x}{spec.foreground:02x}{spec.foreground:02x}"
    background = f"#{spec.background:02x}{spec.background:02x}{spec.background:02x}"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_mm(width)}mm" '
        f'height="{_mm(height)}mm" viewBox="0 0 {_mm(width)} {_mm(height)}">',
    ]
    if title:
        lines.append(f"  <title>{escape(title)}</title>")
    lines.append(f'  <rect width="{_mm(width)}" height="{_mm(height)}" fill="{background}"/>')
    lines.append(f'  <g fill="{foreground}" shape-rendering="crispEdges">')
    x = border
    for bar_width in widths:
        lines.append(
            f'    <rect x="{_mm(x)}" y="{_mm(border)}" width="{_mm(bar_width)}" '
            f'height="{_mm(spec.height_mm)}"/>'
        )
        x += bar_width + spec.gap_mm
    lines += ["  </g>", "</svg>", ""]
    return "\n".join(lines)


@dataclass(frozen=True)
class Distortion:
    """Controlled degradations applied after rendering, in this order:
    scale, perspective, rotation, contrast, illumination, blur, noise, JPEG."""

    rotation_deg: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    perspective_deg: float = 0.0
    blur_sigma: float = 0.0
    noise_sigma: float = 0.0
    contrast: float = 1.0
    illumination_gradient: float = 0.0
    jpeg_quality: int | None = None

    def __post_init__(self) -> None:
        if self.scale_x <= 0:
            raise ValueError(f"scale_x must be > 0, got {self.scale_x}")
        if self.scale_y <= 0:
            raise ValueError(f"scale_y must be > 0, got {self.scale_y}")
        if self.blur_sigma < 0:
            raise ValueError(f"blur_sigma must be >= 0, got {self.blur_sigma}")
        if self.noise_sigma < 0:
            raise ValueError(f"noise_sigma must be >= 0, got {self.noise_sigma}")
        if self.contrast < 0:
            raise ValueError(f"contrast must be >= 0, got {self.contrast}")
        if not 0 <= self.illumination_gradient <= 1:
            raise ValueError(
                f"illumination_gradient must be between 0 and 1, got {self.illumination_gradient}"
            )
        if self.jpeg_quality is not None and not 1 <= self.jpeg_quality <= 100:
            raise ValueError(f"jpeg_quality must be between 1 and 100, got {self.jpeg_quality}")
        # 45 degrees is where the projective shift reaches half the image width.
        if abs(self.perspective_deg) >= 45:
            raise ValueError(f"perspective_deg must have abs() < 45, got {self.perspective_deg}")


def distort(
    image: np.ndarray, distortion: Distortion, rng: np.random.Generator | None = None
) -> np.ndarray:
    """Apply ``distortion`` to a grayscale image. Noise needs ``rng`` for determinism."""
    d = distortion
    out = image
    if d.scale_x != 1.0 or d.scale_y != 1.0:
        shrinking = min(d.scale_x, d.scale_y) < 1.0
        interpolation = cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR
        out = cv2.resize(out, None, fx=d.scale_x, fy=d.scale_y, interpolation=interpolation)
    if d.perspective_deg:
        height, width = out.shape
        shift = 0.5 * width * math.tan(math.radians(d.perspective_deg))
        src = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
        dst = np.float32([[shift, 0], [width - shift, 0], [width, height], [0, height]])
        out = cv2.warpPerspective(
            out,
            cv2.getPerspectiveTransform(src, dst),
            (width, height),
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255,
        )
    if d.rotation_deg:
        out = rotate_bound(out, d.rotation_deg, 255)
    work = out.astype(np.float32)
    if d.contrast != 1.0:
        work = 128.0 + (work - 128.0) * d.contrast
    if d.illumination_gradient:
        ramp = np.linspace(1.0, 1.0 - d.illumination_gradient, work.shape[1], dtype=np.float32)
        work = work * ramp[np.newaxis, :]
    if d.blur_sigma:
        work = cv2.GaussianBlur(work, (0, 0), d.blur_sigma)
    if d.noise_sigma:
        if rng is None:
            raise ValueError("noise_sigma requires a numpy Generator for reproducibility")
        work = work + rng.normal(0.0, d.noise_sigma, work.shape).astype(np.float32)
    out = np.clip(work, 0, 255).astype(np.uint8)
    if d.jpeg_quality is not None:
        ok, buffer = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, int(d.jpeg_quality)])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        out = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
    return out


def compose_scene(
    size: tuple[int, int],
    placements: Sequence[tuple[np.ndarray, int, int]],
    background: int = 255,
) -> np.ndarray:
    """Paste images at ``(x, y)`` on a ``(height, width)`` canvas.

    Parts outside the canvas are clipped; overlaps keep the darker pixel.
    """
    height, width = size
    canvas = np.full((height, width), background, dtype=np.uint8)
    for image, x, y in placements:
        h, w = image.shape
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, width), min(y + h, height)
        if x1 <= x0 or y1 <= y0:
            continue
        patch = image[y0 - y : y1 - y, x0 - x : x1 - x]
        canvas[y0:y1, x0:x1] = np.minimum(canvas[y0:y1, x0:x1], patch)
    return canvas


NEGATIVE_KINDS = ("linear_barcode", "text_rows", "table", "random_stripes", "blank")


def render_negative(
    kind: str, rng: np.random.Generator, size: tuple[int, int] = (400, 800)
) -> np.ndarray:
    """Render an image that must not decode as a Pharmacode."""
    height, width = size
    canvas = np.full(size, 255, dtype=np.uint8)
    if kind == "linear_barcode":
        # Code 128 style: elements of 1..4 modules, several gap widths, one height.
        module, x = 4, 60
        while x < width - 80:
            bar = int(rng.integers(1, 5)) * module
            space = int(rng.integers(1, 5)) * module
            canvas[100:300, x : x + bar] = 0
            x += bar + space
    elif kind == "text_rows":
        y = 40
        while y < height - 60:
            glyph_height = int(rng.integers(14, 22))
            x = 40
            while x < width - 60:
                glyph_width = int(rng.integers(6, 16))
                cv2.rectangle(canvas, (x, y), (x + glyph_width, y + glyph_height), 0, 1)
                cv2.line(canvas, (x, y + glyph_height), (x + glyph_width, y), 0, 1)
                x += glyph_width + int(rng.integers(3, 10))
            y += glyph_height + int(rng.integers(8, 16))
    elif kind == "table":
        column_step = int(rng.integers(60, 120))
        row_step = int(rng.integers(30, 60))
        for x in range(40, width - 39, column_step):
            canvas[40 : height - 40, x : x + 2] = 0
        for y in range(40, height - 39, row_step):
            canvas[y : y + 2, 40 : width - 40] = 0
    elif kind == "random_stripes":
        x, tall = 30, False
        while x < width - 60:
            stripe_width = int(rng.integers(2, 40))
            stripe_height = int(rng.integers(200, 300) if tall else rng.integers(40, 120))
            y = int(rng.integers(20, height - stripe_height - 20))
            canvas[y : y + stripe_height, x : x + stripe_width] = 0
            x += stripe_width + int(rng.integers(3, 60))
            tall = not tall
    elif kind == "blank":
        canvas = np.clip(255.0 - np.abs(rng.normal(0.0, 3.0, size)), 0, 255).astype(np.uint8)
    else:
        raise ValueError(f"unknown negative kind {kind!r}; expected one of {NEGATIVE_KINDS}")
    return canvas
