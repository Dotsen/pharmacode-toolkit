"""Measured bar, gap and quiet-zone dimensions of a detection, against the Laetus tolerances.

This is a diagnostic report, not a print-quality grade: widths come from the
thresholded ink profile the decoder uses (see docs/algorithm.md, section 3),
so blur, ink spread and the camera's resolution all shift them, and a pixel
is the smallest step they can take (``pixel_mm`` in the report).
"""

from __future__ import annotations

import math
from typing import Any

from pharmacode.models import DecodedPharmacode

# Laetus PHARMA-CODE Guide, sections 1.2 and 1.3: (min, max) in mm; see docs/algorithm.md
TOLERANCES_MM: dict[str, dict[str, tuple[float, float]]] = {
    "standard": {"narrow": (0.4, 0.7), "wide": (1.3, 2.5), "gap": (0.9, 2.5)},
    "miniature": {"narrow": (0.3, 0.45), "wide": (0.9, 1.7), "gap": (0.55, 1.65)},
}
NOMINAL_MM: dict[str, dict[str, float]] = {
    "standard": {"narrow": 0.5, "wide": 1.5, "gap": 1.0},
    "miniature": {"narrow": 0.35, "wide": 1.0, "gap": 0.65},
}
QUIET_ZONE_MIN_MM = 6.0  # section 2.2.1, both variants


def _mm(px: float, dpi: float) -> float:
    return round(px * 25.4 / dpi, 3)


def _elements(detection: DecodedPharmacode, dpi: float) -> list[tuple[str, int, float]]:
    """``(element, index, mm)`` for every bar and gap, element being narrow_bar/wide_bar/gap."""
    elements = [
        (f"{kind.value}_bar", index, _mm(width, dpi))
        for index, (kind, width) in enumerate(
            zip(detection.bars, detection.bar_widths_px, strict=True)
        )
    ]
    elements += [
        ("gap", index, _mm(width, dpi)) for index, width in enumerate(detection.gap_widths_px)
    ]
    return elements


def _violations(elements: list[tuple[str, int, float]], variant: str) -> list[dict[str, Any]]:
    found = []
    for element, index, mm in elements:
        low, high = TOLERANCES_MM[variant][element.removesuffix("_bar")]
        if not low <= mm <= high:
            found.append({"element": element, "index": index, "mm": mm, "range_mm": [low, high]})
    return found


def _distance_to_nominal(elements: list[tuple[str, int, float]], variant: str) -> float:
    """Sum of squared log ratios to the variant's nominal sizes; breaks a tie between variants."""
    return sum(
        math.log(max(mm, 1e-6) / NOMINAL_MM[variant][element.removesuffix("_bar")]) ** 2
        for element, _, mm in elements
    )


def geometry_report(detection: DecodedPharmacode, dpi: float | None) -> dict[str, Any]:
    """Dimensions of ``detection`` in px and, when ``dpi`` is known, in mm with tolerances.

    ``variant`` is the Laetus variant (standard or miniature) whose tolerances
    the most bars and gaps satisfy, the one nearer its nominal sizes on a tie;
    ``out_of_tolerance`` lists every bar and gap outside that variant's range
    and every quiet zone below 6 mm. The quiet zone is measured only as far as
    the candidate window reaches (7 to 11 mm with DPI), so a wider one reads as
    the window's extent.
    """
    report: dict[str, Any] = {
        "bar_widths_px": list(detection.bar_widths_px),
        "gap_widths_px": list(detection.gap_widths_px),
        "bar_height_px": detection.bar_height_px,
        "quiet_zone_px": list(detection.quiet_zone_px),
        "pixel_mm": None,
        "bar_widths_mm": None,
        "gap_widths_mm": None,
        "bar_height_mm": None,
        "quiet_zone_mm": None,
        "variant": None,
        "out_of_tolerance": None,
    }
    if dpi is None:
        return report
    elements = _elements(detection, dpi)
    variant = min(
        TOLERANCES_MM,
        key=lambda name: (len(_violations(elements, name)), _distance_to_nominal(elements, name)),
    )
    quiet_zone_mm = [_mm(px, dpi) for px in detection.quiet_zone_px]
    out_of_tolerance = _violations(elements, variant)
    for index, mm in enumerate(quiet_zone_mm):
        if mm < QUIET_ZONE_MIN_MM:
            out_of_tolerance.append(
                {
                    "element": "quiet_zone",
                    "index": index,
                    "mm": mm,
                    "range_mm": [QUIET_ZONE_MIN_MM, None],
                }
            )
    report.update(
        {
            "pixel_mm": _mm(1, dpi),
            "bar_widths_mm": [_mm(w, dpi) for w in detection.bar_widths_px],
            "gap_widths_mm": [_mm(w, dpi) for w in detection.gap_widths_px],
            "bar_height_mm": None
            if detection.bar_height_px is None
            else _mm(detection.bar_height_px, dpi),
            "quiet_zone_mm": quiet_zone_mm,
            "variant": variant,
            "out_of_tolerance": out_of_tolerance,
        }
    )
    return report
