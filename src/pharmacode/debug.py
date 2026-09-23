"""Intermediate images and measurements of a decode, for finding out why a code failed.

Pass a :class:`DebugRecorder` to :func:`pharmacode.pipeline.decode_image` (or
``decode --debug-dir DIR``) and it keeps, for every pass the pipeline runs:

- ``<polarity>-1-input.png`` — the grayscale image the pass works on
  (inverted for the ``light`` pass);
- ``<polarity>-2-flattened.png`` — after background flattening;
- ``<polarity>-3-mask.png`` — the ink mask candidates are searched in (ink black);
- ``<polarity>-4-candidates.png`` — bar-shaped components (blue) and
  candidate boxes, green when decoded and red when rejected, numbered;
- ``<polarity>-candidate-<n>.png`` — each candidate straightened: the region,
  its ink mask (ink black), and its ink profile with the bar threshold (red line) and
  the bar runs found in it (green);
- ``debug.json`` — per pass and candidate: box, orientation, measured widths,
  gaps, quiet zones, heights, confidence margins, and the outcome.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from pharmacode.detection import find_bar_components
from pharmacode.imageops import otsu_mask
from pharmacode.io import save_image
from pharmacode.models import BarSequence, DecodeError, DecoderConfig, DetectionCandidate
from pharmacode.segmentation import (
    bar_profile,
    drop_background_edges,
    normalize_roi,
    runs_from_profile,
)

GREEN = (0, 180, 0)
RED = (0, 0, 220)
BLUE = (220, 120, 0)
GRAY = (150, 150, 150)
PROFILE_HEIGHT = 100


class DebugRecorder:
    """Collects what the pipeline sees; :meth:`save` writes it to a directory."""

    def __init__(self) -> None:
        self.images: dict[str, np.ndarray] = {}
        self.passes: list[dict[str, Any]] = []

    def record_pass(
        self,
        polarity: str,
        gray: np.ndarray,
        flat: np.ndarray,
        candidates: Sequence[DetectionCandidate],
        outcomes: Sequence[BarSequence | DecodeError],
        config: DecoderConfig,
        kernel_floor_px: int,
    ) -> None:
        """Keep one pass: its images, one panel per candidate, and the measurements."""
        mask = otsu_mask(flat)
        self.images[f"{polarity}-1-input.png"] = gray
        self.images[f"{polarity}-2-flattened.png"] = flat
        self.images[f"{polarity}-3-mask.png"] = 255 - mask
        self.images[f"{polarity}-4-candidates.png"] = _overview(
            flat, mask, candidates, outcomes, config
        )
        records = []
        for index, (candidate, outcome) in enumerate(zip(candidates, outcomes, strict=True)):
            self.images[f"{polarity}-candidate-{index}.png"] = _candidate_panel(
                flat, candidate, config
            )
            records.append(_candidate_record(index, candidate, outcome))
        self.passes.append(
            {
                "polarity": polarity,
                "background_kernel_floor_px": kernel_floor_px,
                "candidates": records,
            }
        )

    def save(self, directory: str | Path) -> list[Path]:
        """Write every image and ``debug.json`` into ``directory`` (created if missing)."""
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        written = []
        for name, image in self.images.items():
            save_image(target / name, image)
            written.append(target / name)
        report = target / "debug.json"
        report.write_text(json.dumps({"passes": self.passes}, indent=2) + "\n", encoding="utf-8")
        written.append(report)
        return written


def _label(canvas: np.ndarray, text: str, x: int, y: int, colour: tuple[int, int, int]) -> None:
    font, scale = cv2.FONT_HERSHEY_SIMPLEX, 0.5
    (width, height), _ = cv2.getTextSize(text, font, scale, 1)
    y = max(height + 2, y)
    cv2.rectangle(canvas, (x, y - height - 2), (x + width + 2, y + 2), (255, 255, 255), -1)
    cv2.putText(canvas, text, (x + 1, y), font, scale, colour, 1, cv2.LINE_AA)


def _overview(
    flat: np.ndarray,
    mask: np.ndarray,
    candidates: Sequence[DetectionCandidate],
    outcomes: Sequence[BarSequence | DecodeError],
    config: DecoderConfig,
) -> np.ndarray:
    canvas = cv2.cvtColor(flat, cv2.COLOR_GRAY2BGR)
    for bar in find_bar_components(mask, config):
        corners = cv2.boxPoints(((bar.cx, bar.cy), (bar.length, bar.thickness), bar.angle_deg))
        cv2.polylines(canvas, [np.int32(corners)], True, BLUE, 1)
    for index, (candidate, outcome) in enumerate(zip(candidates, outcomes, strict=True)):
        box = candidate.bbox
        colour = RED if isinstance(outcome, DecodeError) else GREEN
        cv2.rectangle(canvas, (box.x, box.y), (box.x + box.width, box.y + box.height), colour, 1)
        text = f"#{index} {outcome.code.value}" if isinstance(outcome, DecodeError) else f"#{index}"
        _label(canvas, text, box.x, box.y - 2, colour)
    return canvas


def _candidate_panel(
    flat: np.ndarray, candidate: DetectionCandidate, config: DecoderConfig
) -> np.ndarray:
    """The straightened region, its mask and its profile, stacked at the same width."""
    roi = normalize_roi(flat, candidate)
    mask = otsu_mask(roi)
    profile, (top, bottom) = bar_profile(mask, config.profile_band_fraction)
    runs = runs_from_profile(profile, config.profile_threshold)
    kept = drop_background_edges(mask, runs, (top + bottom) // 2, config)
    plot = np.full((PROFILE_HEIGHT, roi.shape[1], 3), 255, dtype=np.uint8)
    base = PROFILE_HEIGHT - 8
    scale = PROFILE_HEIGHT - 16
    for x, fraction in enumerate(profile):
        cv2.line(plot, (x, base), (x, base - int(round(float(fraction) * scale))), GRAY, 1)
    threshold_y = base - int(round(config.profile_threshold * scale))
    cv2.line(plot, (0, threshold_y), (roi.shape[1] - 1, threshold_y), RED, 1)
    for is_bar, start, length in kept:
        if is_bar:
            plot[base + 2 :, start : start + length] = GREEN
    rows = [
        cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR),
        cv2.cvtColor(255 - mask, cv2.COLOR_GRAY2BGR),
        plot,
    ]
    separator = np.full((2, roi.shape[1], 3), (0, 200, 255), dtype=np.uint8)
    return np.vstack([rows[0], separator, rows[1], separator, rows[2]])


def _candidate_record(
    index: int, candidate: DetectionCandidate, outcome: BarSequence | DecodeError
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "index": index,
        "bbox": candidate.bbox.to_dict(),
        "orientation_deg": round(float(candidate.orientation_deg), 2),
        "components": len(candidate.bars),
    }
    if isinstance(outcome, DecodeError):
        record["outcome"] = {"error": outcome.code.value, "message": outcome.message}
        return record
    record["outcome"] = {
        "bars": [kind.value for kind in outcome.kinds],
        "confidence": round(min(outcome.metrics.values()), 3) if outcome.metrics else 0.0,
    }
    record.update(
        {
            "bar_widths_px": list(outcome.bar_widths_px),
            "gap_widths_px": list(outcome.gap_widths_px),
            "quiet_zone_px": list(outcome.quiet_zone_px),
            "bar_height_px": outcome.bar_height_px,
            "metrics": {name: round(value, 3) for name, value in outcome.metrics.items()},
            "warnings": list(outcome.warnings),
        }
    )
    return record
