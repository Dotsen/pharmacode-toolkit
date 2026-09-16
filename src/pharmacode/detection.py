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
    orientation = math.degrees(math.atan2(uy, ux))
    projections = [bar.cx * ux + bar.cy * uy for bar in chain]
    order = np.argsort(projections)
    ordered = [chain[i] for i in order]
    spacings = [
        (projections[order[i + 1]] - projections[order[i]])
        - (ordered[i].thickness + ordered[i + 1].thickness) / 2.0
        for i in range(len(ordered) - 1)
    ]
    length = float(np.median([bar.length for bar in chain]))
    extend_axis = max(config.max_spacing_length_ratio * length, 4.0 * max(spacings))
    physical = config.mm_to_px(config.quiet_zone_nominal_mm + 1.0)
    if physical is not None:
        extend_axis = max(extend_axis, physical)
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
