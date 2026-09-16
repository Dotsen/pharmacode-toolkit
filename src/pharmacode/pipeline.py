"""Library entry point: image in, decoded codes and diagnostics out."""

from __future__ import annotations

import cv2
import numpy as np

from pharmacode.decoding import decode_bars
from pharmacode.detection import find_candidates
from pharmacode.imageops import flatten_background
from pharmacode.models import (
    DecodedPharmacode,
    DecodeError,
    DecoderConfig,
    DecodeResult,
    ErrorCode,
    ImageInfo,
)
from pharmacode.segmentation import extract_bars


def decode_image(
    image: np.ndarray, config: DecoderConfig | None = None, path: str | None = None
) -> DecodeResult:
    """Detect, segment and decode every Pharmacode in ``image`` (gray or BGR uint8)."""
    config = DecoderConfig() if config is None else config
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    info = ImageInfo(path, int(gray.shape[1]), int(gray.shape[0]), config.dpi)
    flat = flatten_background(gray, config.background_kernel_fraction)
    candidates = find_candidates(flat, config)
    if not candidates:
        error = DecodeError(ErrorCode.NO_CANDIDATES, "no group of aligned bars found")
        return DecodeResult(info, (), (error,))
    detections: list[DecodedPharmacode] = []
    errors: list[DecodeError] = []
    for candidate in candidates:
        sequence = extract_bars(flat, candidate, config)
        if isinstance(sequence, DecodeError):
            errors.append(sequence)
            continue
        value, mirror_value = decode_bars(sequence.kinds)
        confidence = min(sequence.metrics.values()) if sequence.metrics else 0.0
        rects = candidate.bars if len(candidate.bars) == len(sequence.kinds) else ()
        detections.append(
            DecodedPharmacode(
                bbox=candidate.bbox,
                orientation_deg=candidate.orientation_deg,
                bars=sequence.kinds,
                bar_widths_px=sequence.bar_widths_px,
                value=value,
                mirror_value=mirror_value,
                confidence=confidence,
                warnings=sequence.warnings,
                bar_rects=rects,
            )
        )
    return DecodeResult(info, tuple(detections), tuple(errors))
