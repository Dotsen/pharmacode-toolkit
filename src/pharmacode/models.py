"""Data model for Pharmacode results."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any


class BarKind(str, Enum):
    """Width class of one bar. One-track Pharmacode uses exactly two classes."""

    NARROW = "narrow"
    WIDE = "wide"

    @property
    def weight(self) -> int:
        """Numeric weight of the bar in the encoding: narrow 1, wide 2."""
        return 2 if self is BarKind.WIDE else 1


class ErrorCode(str, Enum):
    """Stable diagnostic outcome codes. Part of the public JSON contract."""

    INPUT_UNREADABLE = "INPUT_UNREADABLE"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NO_CANDIDATES = "NO_CANDIDATES"
    TOO_FEW_BARS = "TOO_FEW_BARS"
    TOO_MANY_BARS = "TOO_MANY_BARS"
    WIDTH_CLASSES_NOT_SEPARABLE = "WIDTH_CLASSES_NOT_SEPARABLE"
    AMBIGUOUS_WIDTH = "AMBIGUOUS_WIDTH"
    QUIET_ZONE_VIOLATION = "QUIET_ZONE_VIOLATION"
    INCONSISTENT_BAR_HEIGHT = "INCONSISTENT_BAR_HEIGHT"
    INCONSISTENT_GAPS = "INCONSISTENT_GAPS"


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned box in pixel coordinates."""

    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class BarRect:
    """Oriented rectangle fitted to one bar-like connected component.

    ``angle_deg`` is the direction of the long side in image coordinates
    (x right, y down), normalised to ``[0, 180)``.
    """

    cx: float
    cy: float
    length: float
    thickness: float
    angle_deg: float


@dataclass(frozen=True)
class DetectionCandidate:
    """A group of aligned bars that may be a Pharmacode. Geometry only.

    ``orientation_deg`` is the code axis angle in ``(-90, 90]``: 0 means the
    primary reading runs left to right, 90 means top to bottom.
    """

    bbox: BoundingBox
    orientation_deg: float
    bars: tuple[BarRect, ...]


@dataclass(frozen=True)
class BarSequence:
    """Measured, classified bars of one candidate after segmentation."""

    kinds: tuple[BarKind, ...]
    bar_widths_px: tuple[int, ...]
    gap_widths_px: tuple[int, ...]
    quiet_zone_px: tuple[int, int]
    bar_height_px: int
    warnings: tuple[str, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DecodedPharmacode:
    """One successfully decoded code with both reading directions."""

    bbox: BoundingBox
    orientation_deg: float
    bars: tuple[BarKind, ...]
    bar_widths_px: tuple[int, ...]
    value: int
    mirror_value: int
    confidence: float
    warnings: tuple[str, ...] = ()
    bar_rects: tuple[BarRect, ...] = ()  # geometry for annotation; not part of the JSON contract

    def to_dict(self) -> dict[str, Any]:
        return {
            "bbox": self.bbox.to_dict(),
            "orientation_deg": round(float(self.orientation_deg), 2),
            "bars": [bar.value for bar in self.bars],
            "bar_widths_px": list(self.bar_widths_px),
            "value": self.value,
            "mirror_value": self.mirror_value,
            "confidence": round(float(self.confidence), 3),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class DecodeError:
    """A diagnostic outcome for the whole image or for one candidate."""

    code: ErrorCode
    message: str
    bbox: BoundingBox | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "bbox": self.bbox.to_dict() if self.bbox else None,
        }


@dataclass(frozen=True)
class ImageInfo:
    path: str | None
    width: int
    height: int
    dpi: float | None

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "width": self.width, "height": self.height, "dpi": self.dpi}


@dataclass(frozen=True)
class DecodeResult:
    """Everything the pipeline reports for one image."""

    image: ImageInfo
    detections: tuple[DecodedPharmacode, ...]
    errors: tuple[DecodeError, ...]

    @property
    def ok(self) -> bool:
        return bool(self.detections) and not self.errors

    def to_dict(self) -> dict[str, Any]:
        from pharmacode import __version__

        return {
            "version": __version__,
            "image": self.image.to_dict(),
            "detections": [d.to_dict() for d in self.detections],
            "errors": [e.to_dict() for e in self.errors],
        }


@dataclass(frozen=True)
class DecoderConfig:
    """All thresholds of the pipeline with their origin.

    Ratios come from the Laetus PHARMA-CODE Guide nominal dimensions
    (narrow 0.5 mm, wide 1.5 mm, gap 1.0 mm, height 8 mm, quiet zone 6 mm)
    and their tolerance ranges (narrow 0.4-0.7, wide 1.3-2.5, gap 0.9-2.5).
    """

    dpi: float | None = None
    min_bars: int = 2
    max_bars: int = 16

    # detection: background flattening and component filtering
    background_kernel_fraction: float = 0.05  # closing kernel = 5 % of the longer side
    min_bar_length_px: int = 8  # discard specks; 8 mm bars are >= 47 px even at 150 DPI
    min_bar_aspect: float = 4.0  # height / wide >= 8 / 2.5 = 3.2 at tolerance limits, 5.3 nominal
    min_fill_ratio: float = 0.75  # bars are solid rectangles; text and glyphs are not
    min_contrast: float = 30.0  # ink vs paper after flattening; below this the page is blank
    # detection: grouping
    max_angle_diff_deg: float = 10.0  # bars of one code are parallel
    max_length_ratio: float = 1.25  # bars of one code share one height
    max_axis_offset_ratio: float = 0.25  # centres lie on one axis, relative to bar length
    max_spacing_factor: float = 3.0  # legal gaps vary <= 2.8 x; codes are >= 4.8 x a gap apart
    max_spacing_length_ratio: float = 1.0  # a gap never exceeds the bar height in practice
    # segmentation
    profile_band_fraction: float = 0.6  # central band of the bar height used for the profile
    profile_threshold: float = 0.5
    width_split_ratio: float = 1.5  # nominal wide/narrow is 3; below 1.5 treat as one class
    max_intra_class_ratio: float = (
        1.35  # spread inside one width class; 0.4-0.7 mm => 1.75 max, printed codes tighter
    )
    width_pixel_tolerance_px: int = (
        2  # a class is also tight if its widths differ by <= 2 px (low DPI)
    )
    physical_width_boundary_mm: float = (
        0.8  # narrow <= 0.7 mm, wide >= 0.9 mm in both Laetus variants
    )
    gap_ruler_boundary: float = 1.0  # without DPI: narrow = 0.5 x gap, wide = 1.5 x gap nominal
    quiet_zone_hard_mm: float = 3.0  # half the nominal 6 mm
    quiet_zone_nominal_mm: float = 6.0
    quiet_zone_hard_wide_ratio: float = 2.0  # without DPI: 6 mm / 2.5 mm max wide = 2.4
    quiet_zone_nominal_wide_ratio: float = 4.0  # 6 mm / 1.5 mm
    max_height_deviation: float = 0.20  # bars of one code share one height
    gap_ratio_range: tuple[float, float] = (0.5, 2.0)  # gaps of one code are uniform
    single_class_no_dpi_confidence_cap: float = 0.5

    def with_updates(self, **changes: Any) -> DecoderConfig:
        return replace(self, **changes)

    def mm_to_px(self, mm: float) -> float | None:
        return None if self.dpi is None else mm * self.dpi / 25.4

    def px_to_mm(self, px: float) -> float | None:
        return None if self.dpi is None else px * 25.4 / self.dpi
