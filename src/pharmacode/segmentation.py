"""Turn a code region into an ordered, classified sequence of bars.

All thresholds come from :class:`pharmacode.models.DecoderConfig`; see its
docstring for the Laetus ratios behind them.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from pharmacode.decoding import check_bar_count
from pharmacode.imageops import otsu_mask, rotate_bound
from pharmacode.models import (
    BarKind,
    BarSequence,
    DecodeError,
    DecoderConfig,
    DetectionCandidate,
    ErrorCode,
)

Run = tuple[bool, int, int]
Outcome = tuple[tuple[str, ...], dict[str, float]]


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _is_tight(widths: np.ndarray, config: DecoderConfig) -> bool:
    """One width class: relative spread within the ratio, or absolute spread within 2 px."""
    spread_ratio = float(widths.max()) / max(float(widths.min()), 1e-9)
    spread_px = float(widths.max() - widths.min())
    return (
        spread_ratio <= config.max_intra_class_ratio or spread_px <= config.width_pixel_tolerance_px
    )


def _within_narrow(width: float, narrow_median: float, config: DecoderConfig) -> bool:
    return (
        width <= narrow_median * config.max_intra_class_ratio
        or width <= narrow_median + config.width_pixel_tolerance_px
    )


def _within_wide(width: float, wide_median: float, config: DecoderConfig) -> bool:
    return (
        width >= wide_median / config.max_intra_class_ratio
        or width >= wide_median - config.width_pixel_tolerance_px
    )


def _inked_block(row_ink: np.ndarray, reference: int) -> tuple[int, int]:
    """Return (top, bottom) of the contiguous run of True rows containing ``reference``.

    If ``reference`` itself is not inked, use the nearest inked row (ties
    broken towards the lower index). Returns (0, -1) when nothing is inked.
    """
    inked = np.flatnonzero(row_ink)
    if inked.size == 0:
        return 0, -1
    if not row_ink[reference]:
        reference = int(inked[np.argmin(np.abs(inked - reference))])
    top = bottom = reference
    while top > 0 and row_ink[top - 1]:
        top -= 1
    while bottom < row_ink.size - 1 and row_ink[bottom + 1]:
        bottom += 1
    return top, bottom


def bar_profile(mask: np.ndarray, band_fraction: float) -> tuple[np.ndarray, tuple[int, int]]:
    """Fraction of ink per column over the central band of the bars' own ink block.

    The block is the contiguous run of inked rows around the ROI's centre
    row, which sits inside the bars because the candidate box is built
    symmetrically around them; a caption separated from the bars by a white
    gap falls outside it and is ignored. Returns the profile and the block's
    ``(top, bottom)`` rows; an empty mask gives an all-zero profile and rows
    ``(0, -1)``.
    """
    row_ink = mask.any(axis=1)
    if not row_ink.any():
        return np.zeros(mask.shape[1], dtype=np.float32), (0, -1)
    top, bottom = _inked_block(row_ink, mask.shape[0] // 2)
    centre = (top + bottom) / 2.0
    half = max(1.0, (bottom - top + 1) * band_fraction / 2.0)
    y0 = max(top, int(round(centre - half)))
    y1 = min(bottom + 1, max(y0 + 1, int(round(centre + half))))
    profile = (mask[y0:y1] > 0).mean(axis=0).astype(np.float32)
    return profile, (top, bottom)


def runs_from_profile(profile: np.ndarray, threshold: float) -> list[Run]:
    """Run-length encode the thresholded profile as ``(is_bar, start, length)``."""
    binary = profile >= threshold
    runs: list[Run] = []
    if binary.size == 0:
        return runs
    start, current = 0, bool(binary[0])
    for index in range(1, binary.size):
        if bool(binary[index]) != current:
            runs.append((current, start, index - start))
            start, current = index, bool(binary[index])
    runs.append((current, start, binary.size - start))
    return runs


def measure_runs(runs: Sequence[Run]) -> tuple[list[tuple[int, int]], list[int], int, int]:
    """Split runs into bars ``(start, width)``, inner gap widths, leading and trailing space."""
    bars = [(start, length) for is_bar, start, length in runs if is_bar]
    leading = runs[0][2] if runs and not runs[0][0] else 0
    trailing = runs[-1][2] if len(runs) > 1 and not runs[-1][0] else 0
    gaps: list[int] = []
    for index in range(1, len(runs) - 1):
        is_bar, _, length = runs[index]
        if not is_bar and runs[index - 1][0] and runs[index + 1][0]:
            gaps.append(length)
    return bars, gaps, leading, trailing


def measure_heights(mask: np.ndarray, bars: Sequence[tuple[int, int]], centre: int) -> list[int]:
    """Vertical ink extent of each bar's own ink block around the band centre row.

    A row counts as part of the bar when at least half of the bar's columns
    are ink; the height is the contiguous run of such rows containing
    ``centre`` (see :func:`_inked_block`), so a caption connected to the bar
    only by ink outside that run — separated by a white gap — is not counted.
    """
    heights: list[int] = []
    for start, width in bars:
        rows = (mask[:, start : start + width] > 0).mean(axis=1) >= 0.5
        top, bottom = _inked_block(rows, centre)
        heights.append(bottom - top + 1)
    return heights


def validate_shape(
    heights: Sequence[int], gaps: Sequence[int], config: DecoderConfig
) -> Outcome | DecodeError:
    """Bars of one code share one height and one gap width."""
    metrics: dict[str, float] = {}
    median_height = float(np.median(heights))
    if median_height <= 0:
        return DecodeError(ErrorCode.INCONSISTENT_BAR_HEIGHT, "bars have no measurable height")
    deviation = max(abs(h - median_height) / median_height for h in heights)
    if deviation > config.max_height_deviation:
        return DecodeError(
            ErrorCode.INCONSISTENT_BAR_HEIGHT,
            f"bar heights {list(heights)} deviate {deviation:.0%} from the median, "
            f"limit {config.max_height_deviation:.0%}",
        )
    metrics["height_consistency"] = _clip01(1.0 - deviation / config.max_height_deviation)
    if gaps:
        median_gap = float(np.median(gaps))
        low, high = config.gap_ratio_range
        ratios = [g / median_gap for g in gaps]
        if min(ratios) < low or max(ratios) > high:
            return DecodeError(
                ErrorCode.INCONSISTENT_GAPS,
                f"gap widths {list(gaps)} px are not uniform (allowed {low}-{high} x median)",
            )
        worst = max(abs(r - 1.0) for r in ratios)
        metrics["gap_consistency"] = _clip01(1.0 - worst / (high - 1.0))
    return (), metrics


def classify_widths(
    bar_widths: Sequence[int], gap_widths: Sequence[int], config: DecoderConfig
) -> tuple[tuple[BarKind, ...], tuple[str, ...], dict[str, float]] | DecodeError:
    """Assign narrow/wide to every bar.

    Two classes are separated at the largest ratio jump between sorted widths.
    A bar that lies outside both classes' tolerance bands is ambiguous.
    A legal single-class code is classified against the physical boundary
    (0.8 mm) when the DPI is known, else against the median gap.
    """
    widths = np.asarray(bar_widths, dtype=np.float64)
    ordered = np.sort(widths)
    warnings: list[str] = []
    metrics: dict[str, float] = {}
    ratios = ordered[1:] / np.maximum(ordered[:-1], 1e-9)
    if ratios.size and float(ratios.max()) >= config.width_split_ratio:
        split = int(np.argmax(ratios))
        narrow_median = float(np.median(ordered[: split + 1]))
        wide_median = float(np.median(ordered[split + 1 :]))
        assigned: list[BarKind] = []
        for width in widths:
            near_narrow = _within_narrow(width, narrow_median, config)
            near_wide = _within_wide(width, wide_median, config)
            if near_narrow and near_wide:
                # bands overlap at very low DPI: take the nearer class in ratio terms
                kind = (
                    BarKind.WIDE if width * width > narrow_median * wide_median else BarKind.NARROW
                )
            elif near_narrow:
                kind = BarKind.NARROW
            elif near_wide:
                kind = BarKind.WIDE
            else:
                return DecodeError(
                    ErrorCode.AMBIGUOUS_WIDTH,
                    f"bar width {int(width)} px is neither narrow (about {narrow_median:.0f} px) "
                    f"nor wide (about {wide_median:.0f} px)",
                )
            assigned.append(kind)
        kinds = tuple(assigned)
        narrow = widths[[k is BarKind.NARROW for k in kinds]]
        wide = widths[[k is BarKind.WIDE for k in kinds]]
        if not (_is_tight(narrow, config) and _is_tight(wide, config)):
            return DecodeError(
                ErrorCode.WIDTH_CLASSES_NOT_SEPARABLE,
                f"bar widths {sorted(int(w) for w in widths)} px do not form two tight classes",
            )
        class_ratio = float(wide.mean() / narrow.mean())
        metrics["width_margin"] = _clip01(
            (class_ratio - config.max_intra_class_ratio) / (3.0 - config.max_intra_class_ratio)
        )
        if class_ratio < 2.0:
            warnings.append("width_ratio_below_nominal")
        return kinds, tuple(warnings), metrics

    if not _is_tight(ordered, config):
        return DecodeError(
            ErrorCode.WIDTH_CLASSES_NOT_SEPARABLE,
            f"bar widths {sorted(int(w) for w in widths)} px spread without a clear split",
        )
    median_width = float(np.median(widths))
    warnings.append("single_width_class")
    if config.dpi is not None:
        median_mm = median_width * 25.4 / config.dpi
        boundary_mm = config.physical_width_boundary_mm
        kind = BarKind.WIDE if median_mm > boundary_mm else BarKind.NARROW
        metrics["width_margin"] = _clip01(abs(median_mm - boundary_mm) / boundary_mm)
    else:
        ruler = float(np.median(gap_widths)) if gap_widths else median_width
        boundary = config.gap_ruler_boundary * ruler
        kind = BarKind.WIDE if median_width > boundary else BarKind.NARROW
        warnings.append("single_width_class_no_dpi")
        metrics["width_margin"] = min(
            config.single_class_no_dpi_confidence_cap,
            _clip01(abs(median_width - boundary) / (0.5 * boundary)),
        )
    return (kind,) * len(widths), tuple(warnings), metrics


def validate_quiet_zone(
    leading: int,
    trailing: int,
    bar_widths: Sequence[int],
    kinds: Sequence[BarKind],
    config: DecoderConfig,
) -> Outcome | DecodeError:
    """Both ends need blank space: 6 mm nominal, half of that as the hard limit."""
    wide_widths = [w for w, k in zip(bar_widths, kinds, strict=True) if k is BarKind.WIDE]
    wide_px = (
        float(np.mean(wide_widths))
        if wide_widths
        else 3.0 * float(np.mean(bar_widths))  # nominal wide : narrow ratio
    )
    hard = config.mm_to_px(config.quiet_zone_hard_mm)
    nominal = config.mm_to_px(config.quiet_zone_nominal_mm)
    if hard is None or nominal is None:
        hard = config.quiet_zone_hard_wide_ratio * wide_px
        nominal = config.quiet_zone_nominal_wide_ratio * wide_px
    smallest = min(leading, trailing)
    if smallest < hard:
        return DecodeError(
            ErrorCode.QUIET_ZONE_VIOLATION,
            f"quiet zone of {smallest} px is below the minimum {hard:.0f} px",
        )
    warnings: tuple[str, ...] = ()
    if smallest < nominal:
        warnings = ("quiet_zone_below_nominal",)
    return warnings, {"quiet_zone_margin": _clip01(smallest / nominal)}


def _sequence_from_mask(mask: np.ndarray, config: DecoderConfig) -> BarSequence | DecodeError:
    profile, (top, bottom) = bar_profile(mask, config.profile_band_fraction)
    runs = runs_from_profile(profile, config.profile_threshold)
    bars, gaps, leading, trailing = measure_runs(runs)
    count_error = check_bar_count(len(bars), config)
    if count_error is not None:
        return count_error
    widths = [width for _, width in bars]
    heights = measure_heights(mask, bars, (top + bottom) // 2)
    shape = validate_shape(heights, gaps, config)
    if isinstance(shape, DecodeError):
        return shape
    classified = classify_widths(widths, gaps, config)
    if isinstance(classified, DecodeError):
        return classified
    kinds, class_warnings, class_metrics = classified
    quiet = validate_quiet_zone(leading, trailing, widths, kinds, config)
    if isinstance(quiet, DecodeError):
        return quiet
    return BarSequence(
        kinds=kinds,
        bar_widths_px=tuple(widths),
        gap_widths_px=tuple(gaps),
        quiet_zone_px=(leading, trailing),
        bar_height_px=int(np.median(heights)),
        warnings=shape[0] + class_warnings + quiet[0],
        metrics={**shape[1], **class_metrics, **quiet[1]},
    )


def extract_bars_from_upright(gray: np.ndarray, config: DecoderConfig) -> BarSequence | DecodeError:
    """Segment an image that contains one horizontal code with its quiet zones."""
    return _sequence_from_mask(otsu_mask(gray), config)


def normalize_roi(gray: np.ndarray, candidate: DetectionCandidate) -> np.ndarray:
    """Crop the candidate box and rotate it so the code axis runs left to right."""
    box = candidate.bbox
    roi = gray[box.y : box.y + box.height, box.x : box.x + box.width]
    if abs(candidate.orientation_deg) < 0.05:
        return roi
    return rotate_bound(roi, candidate.orientation_deg, 255)


def extract_bars(
    gray: np.ndarray, candidate: DetectionCandidate, config: DecoderConfig
) -> BarSequence | DecodeError:
    """Segment one candidate; a failure is tagged with the candidate box."""
    outcome = _sequence_from_mask(otsu_mask(normalize_roi(gray, candidate)), config)
    if isinstance(outcome, DecodeError):
        return DecodeError(outcome.code, outcome.message, candidate.bbox)
    return outcome
