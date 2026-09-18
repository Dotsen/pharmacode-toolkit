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


def find_candidates(flat_gray: np.ndarray, config: DecoderConfig) -> list[DetectionCandidate]:
    """Run binarisation, component filtering and grouping on a background-flattened image."""
    mask = otsu_mask(flat_gray)
    ink = mask > 0
    if not ink.any() or ink.all():
        return []
    contrast = float(flat_gray[~ink].mean()) - float(flat_gray[ink].mean())
    if contrast < config.min_contrast:
        return []
    bars = find_bar_components(mask, config)
    return [
        candidate_from_chain(chain, config, flat_gray.shape) for chain in group_bars(bars, config)
    ]
