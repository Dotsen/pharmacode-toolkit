"""Find groups of aligned bars that may be a Pharmacode. Nothing is decoded here."""

from __future__ import annotations

import math
from collections.abc import Sequence

import cv2
import numpy as np

from pharmacode.imageops import otsu_mask
from pharmacode.models import BarRect, BoundingBox, DecoderConfig, DetectionCandidate


def _angle_difference(a: float, b: float) -> float:
    """Smallest difference between two line directions, in degrees (0..90)."""
    diff = abs(a - b) % 180.0
    return min(diff, 180.0 - diff)


def find_bar_components(mask: np.ndarray, config: DecoderConfig) -> list[BarRect]:
    """Fit an oriented rectangle to every ink component that looks like a solid bar."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    bars: list[BarRect] = []
    for index in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[index])
        if max(w, h) < config.min_bar_length_px:
            continue
        ys, xs = np.nonzero(labels[y : y + h, x : x + w] == index)
        points = np.column_stack([xs + x, ys + y]).astype(np.float32)
        (cx, cy), (rw, rh), angle = cv2.minAreaRect(points)
        rw, rh = rw + 1.0, rh + 1.0  # minAreaRect spans pixel centres
        if rw >= rh:
            length, thickness, direction = rw, rh, angle
        else:
            length, thickness, direction = rh, rw, angle + 90.0
        if length < config.min_bar_length_px:
            continue
        if length / thickness < config.min_bar_aspect:
            continue
        if area / (length * thickness) < config.min_fill_ratio:
            continue
        bars.append(
            BarRect(float(cx), float(cy), float(length), float(thickness), direction % 180.0)
        )
    return bars


def estimate_stroke_px(mask: np.ndarray, config: DecoderConfig) -> float | None:
    """Widest bar-like stroke in a raw ink mask, to size the background-flattening kernel.

    Runs the same component fit as :func:`find_bar_components`, then discards
    components thicker than ``max_stroke_fraction`` of the mask's longer side
    (those are solid blobs, not bars) and returns the thickest survivor's
    thickness, or ``None`` when nothing bar-like remains.
    """
    bars = find_bar_components(mask, config)
    limit = config.max_stroke_fraction * max(mask.shape)
    thicknesses = [bar.thickness for bar in bars if bar.thickness <= limit]
    return max(thicknesses) if thicknesses else None


def _split_chains(
    aligned: list[tuple[float, BarRect]], config: DecoderConfig
) -> list[list[BarRect]]:
    """Split bars sorted along the axis wherever the edge-to-edge spacing jumps."""
    if not aligned:
        return []
    spacings = [
        (t1 - t0) - (a.thickness + b.thickness) / 2.0
        for (t0, a), (t1, b) in zip(aligned, aligned[1:], strict=False)
    ]
    smallest = max(min(spacings), 1.0) if spacings else 1.0
    median_length = float(np.median([bar.length for _, bar in aligned]))
    chains: list[list[BarRect]] = []
    current = [aligned[0][1]]
    for spacing, (_, bar) in zip(spacings, aligned[1:], strict=False):
        too_far = (
            spacing > config.max_spacing_factor * smallest
            or spacing > config.max_spacing_length_ratio * median_length
        )
        if too_far:
            chains.append(current)
            current = [bar]
        else:
            current.append(bar)
    chains.append(current)
    return chains


def group_bars(bars: Sequence[BarRect], config: DecoderConfig) -> list[list[BarRect]]:
    """Chain parallel, equally long, co-axial bars into candidate groups in axis order."""
    remaining = sorted(bars, key=lambda b: (-b.length, b.cx, b.cy))
    groups: list[list[BarRect]] = []
    while remaining:
        seed = remaining[0]
        theta = math.radians(seed.angle_deg)
        nx, ny = math.cos(theta), math.sin(theta)  # along the bar
        ux, uy = -ny, nx  # along the code axis
        if ux < -1e-9 or (abs(ux) <= 1e-9 and uy < 0):
            ux, uy = -ux, -uy  # canonical reading direction: rightward, or downward if vertical
        aligned: list[tuple[float, BarRect]] = []
        for bar in remaining:
            if _angle_difference(bar.angle_deg, seed.angle_deg) > config.max_angle_diff_deg:
                continue
            longer, shorter = max(bar.length, seed.length), min(bar.length, seed.length)
            if longer / shorter > config.max_length_ratio:
                continue
            dx, dy = bar.cx - seed.cx, bar.cy - seed.cy
            if abs(dx * nx + dy * ny) > config.max_axis_offset_ratio * seed.length:
                continue
            aligned.append((dx * ux + dy * uy, bar))
        aligned.sort(key=lambda item: item[0])
        chains = [chain for chain in _split_chains(aligned, config) if len(chain) >= 2]
        groups.extend(chains)
        consumed = {id(bar) for chain in chains for bar in chain}
        consumed.add(id(seed))
        remaining = [bar for bar in remaining if id(bar) not in consumed]
    return groups


def _mean_direction(angles_deg: Sequence[float]) -> float:
    """Circular mean of line directions (period 180 degrees)."""
    doubled = np.radians(np.asarray(angles_deg) * 2.0)
    mean = math.atan2(float(np.sin(doubled).mean()), float(np.cos(doubled).mean()))
    return math.degrees(mean / 2.0) % 180.0


def candidate_from_chain(
    chain: Sequence[BarRect], config: DecoderConfig, image_shape: tuple[int, ...]
) -> DetectionCandidate:
    """Build the candidate box around a chain, leaving room to measure the quiet zones."""
    height, width = image_shape[:2]
    bar_direction = _mean_direction([bar.angle_deg for bar in chain])
    theta = math.radians(bar_direction)
    nx, ny = math.cos(theta), math.sin(theta)
    ux, uy = -ny, nx
    if ux < -1e-9 or (abs(ux) <= 1e-9 and uy < 0):
        ux, uy = -ux, -uy
    # atan2 of a cos/sin round trip leaves ~1e-15 deg noise even for exact right
    # angles (radians(90) is an approximation of pi/2); round it away so an
    # axis-aligned code reports an exact 0.0 or 90.0, not a false tilt.
    orientation = round(math.degrees(math.atan2(uy, ux)), 9) + 0.0
    projections = [bar.cx * ux + bar.cy * uy for bar in chain]
    order = np.argsort(projections)
    ordered = [chain[i] for i in order]
    spacings = [
        (projections[order[i + 1]] - projections[order[i]])
        - (ordered[i].thickness + ordered[i + 1].thickness) / 2.0
        for i in range(len(ordered) - 1)
    ]
    length = float(np.median([bar.length for bar in chain]))
    # The window must be wide enough to hold whatever validate_quiet_zone will demand once
    # segmentation runs: 4x the wide bar width when one is known (quiet_zone_nominal_wide_ratio),
    # estimated as either the thickest bar in the chain, or 3x the thinnest for an all-narrow
    # code where no bar reaches the true wide width yet. It also has to clear the largest gap
    # already seen between bars with room to spare (4.5x: benchmarked against 200 synthetic
    # negatives, where a run with an oversized end gap needs the window to reach slightly past
    # it so the neighbouring, disqualifying ink stays inside the candidate instead of being
    # cropped away). But it must stay below the ~12 mm minimum separation Laetus leaves between
    # two codes, or the window swallows a neighbouring code's bars as a false quiet zone; with a
    # known DPI it is capped at 11 mm to leave that code's own 1 mm margin. Without DPI it falls
    # back to the same formula in millimetre-free bar-width terms.
    thicknesses = [bar.thickness for bar in chain]
    extend_axis = max(
        config.quiet_zone_nominal_wide_ratio * max(thicknesses),
        config.quiet_zone_nominal_wide_ratio * 3.0 * min(thicknesses),
        4.5 * (max(spacings) if spacings else max(thicknesses)),
    )
    physical = config.mm_to_px(config.quiet_zone_nominal_mm + 1.0)
    if physical is not None:
        extend_axis = min(max(extend_axis, physical), config.mm_to_px(11.0))
    extend_across = 0.5 * length
    corners = np.concatenate(
        [
            cv2.boxPoints(((bar.cx, bar.cy), (bar.length, bar.thickness), bar.angle_deg))
            for bar in chain
        ]
    )
    ex = abs(ux) * extend_axis + abs(nx) * extend_across
    ey = abs(uy) * extend_axis + abs(ny) * extend_across
    x0 = max(0, int(math.floor(corners[:, 0].min() - ex)))
    y0 = max(0, int(math.floor(corners[:, 1].min() - ey)))
    x1 = min(width, int(math.ceil(corners[:, 0].max() + ex)))
    y1 = min(height, int(math.ceil(corners[:, 1].max() + ey)))
    return DetectionCandidate(
        bbox=BoundingBox(x0, y0, x1 - x0, y1 - y0),
        orientation_deg=orientation,
        bars=tuple(ordered),
    )


def _bbox_iou(a: BoundingBox, b: BoundingBox) -> float:
    """Intersection over union of two axis-aligned boxes, 0.0 when they don't overlap."""
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.width, b.x + b.width), min(a.y + a.height, b.y + b.height)
    intersection = max(0, x1 - x0) * max(0, y1 - y0)
    if intersection == 0:
        return 0.0
    union = a.width * a.height + b.width * b.height - intersection
    return intersection / union if union > 0 else 0.0


def _candidates_from_mask(
    mask: np.ndarray, config: DecoderConfig, image_shape: tuple[int, ...]
) -> list[DetectionCandidate]:
    bars = find_bar_components(mask, config)
    return [candidate_from_chain(chain, config, image_shape) for chain in group_bars(bars, config)]


def _crossing_line_regions(mask: np.ndarray, config: DecoderConfig) -> np.ndarray:
    """Bounding boxes of components shaped like several bars merged by one thin rule.

    Several real bars joined edge-to-edge by a rule that also crosses the gaps
    between them still form one long, thin component (it passes
    ``min_bar_length_px`` and ``min_bar_aspect``, exactly like a real bar
    would) but a sparse one (its ink covers less of that bounding box than
    ``min_fill_ratio``, because the gaps are mostly blank except for the thin
    rule) — that combination of "bar-shaped but under-filled" is what
    distinguishes it from unrelated dense clutter (a filled grid of table
    lines, disconnected text glyphs) that the fallback below must not
    mistake for a barcode. Returns a mask blanked outside those boxes, so the
    fallback only ever searches inside a region that already looks like a
    candidate merge, never the whole image.
    """
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    restricted = np.zeros_like(mask)
    for index in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[index])
        length, thickness = max(w, h), max(1, min(w, h))
        if length < config.min_bar_length_px or length / thickness < config.min_bar_aspect:
            continue
        if area / (length * thickness) >= config.min_fill_ratio:
            continue  # already dense enough to be a normal bar-shaped component
        restricted[y : y + h, x : x + w] = mask[y : y + h, x : x + w]
    return restricted


def _opened_variants(mask: np.ndarray, config: DecoderConfig) -> list[np.ndarray]:
    """Vertical- and horizontal-opened versions of the mask's crossing-line regions.

    A vertical element preserves tall bars and erases a horizontal rule
    thinner than it (and vice versa for a horizontal element); trying both
    covers a crossing rule regardless of the code's own orientation.
    """
    restricted = _crossing_line_regions(mask, config)
    if not restricted.any():
        return []
    span = config.crossing_line_max_px + 1
    vertical = cv2.getStructuringElement(cv2.MORPH_RECT, (1, span))
    horizontal = cv2.getStructuringElement(cv2.MORPH_RECT, (span, 1))
    return [
        cv2.morphologyEx(restricted, cv2.MORPH_OPEN, kernel) for kernel in (vertical, horizontal)
    ]


def estimate_stroke_px_past_crossing_lines(mask: np.ndarray, config: DecoderConfig) -> float | None:
    """``estimate_stroke_px``, retried on the mask opened by :func:`_opened_variants`.

    When a thin rule crosses every bar of a code, the raw mask holds no
    isolated bar-shaped component for :func:`estimate_stroke_px` to measure
    (they are all one low-fill blob) — the same problem :func:`find_candidates`
    solves for detection. Reusing that opening here keeps the
    background-flattening kernel (see ``pipeline.decode_image``) sized from
    the true bar width even on an image that also needs the crossing-line
    fallback.
    """
    stroke = estimate_stroke_px(mask, config)
    if stroke is not None:
        return stroke
    candidates = [estimate_stroke_px(opened, config) for opened in _opened_variants(mask, config)]
    thicknesses = [t for t in candidates if t is not None]
    return max(thicknesses) if thicknesses else None


def _crossing_line_fallback(
    mask: np.ndarray, config: DecoderConfig, image_shape: tuple[int, ...]
) -> list[DetectionCandidate]:
    """Recover bars merged by a thin rule crossing them, by opening the mask lengthwise.

    Only ``_crossing_line_regions`` of the mask are searched, so this cannot
    turn unrelated dense ink (a table grid, disconnected text) into a false
    code.
    """
    candidates: list[DetectionCandidate] = []
    for opened in _opened_variants(mask, config):
        for candidate in _candidates_from_mask(opened, config, image_shape):
            # a 2-bar chain can never fail _split_chains' own spacing test (with a single
            # inter-bar gap, that gap is always "the smallest", so it is always <= itself):
            # two isolated recovered strokes are far weaker evidence of a real merge than
            # a longer run, and are exactly what a single text glyph's own outline produces.
            if len(candidate.bars) < config.fallback_min_bars:
                continue
            if not any(_bbox_iou(candidate.bbox, kept.bbox) > 0.5 for kept in candidates):
                candidates.append(candidate)
    return candidates


def find_candidates(flat_gray: np.ndarray, config: DecoderConfig) -> list[DetectionCandidate]:
    """Run binarisation, component filtering and grouping on a background-flattened image.

    If that plain pass finds nothing, two more passes try to recover a code
    whose bars were merged into one component by a thin rule crossing all of
    them (see :func:`_crossing_line_fallback`); this fallback only runs when
    the plain pass is empty, so it never changes the result of an image that
    already decodes.
    """
    mask = otsu_mask(flat_gray)
    ink = mask > 0
    if not ink.any() or ink.all():
        return []
    contrast = float(flat_gray[~ink].mean()) - float(flat_gray[ink].mean())
    if contrast < config.min_contrast:
        return []
    candidates = _candidates_from_mask(mask, config, flat_gray.shape)
    if candidates:
        return candidates
    return _crossing_line_fallback(mask, config, flat_gray.shape)
