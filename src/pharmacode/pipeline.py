"""Library entry point: image in, decoded codes and diagnostics out."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from pharmacode.decoding import decode_bars
from pharmacode.detection import estimate_stroke_px_past_crossing_lines, find_candidates
from pharmacode.imageops import flatten_background, otsu_mask
from pharmacode.io import load_image
from pharmacode.metadata import Resolution, read_resolution
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
    image: np.ndarray,
    config: DecoderConfig | None = None,
    path: str | None = None,
    dpi_source: str | None = None,
) -> DecodeResult:
    """Detect, segment and decode every Pharmacode in ``image`` (gray or BGR uint8).

    ``config.polarity`` picks dark bars on a light background (``"dark"``), the
    inverse (``"light"``), or ``"auto"``: the dark pass first, and the light pass
    only when the dark pass decodes nothing, so an ordinary printed code costs a
    single pass and keeps exactly the result of ``"dark"``. When neither pass
    decodes anything, ``"auto"`` reports the dark pass's errors, unless the dark
    pass found no candidate at all and the light pass did.

    ``dpi_source`` is reported as ``image.dpi_source``; it defaults to
    ``"given"`` whenever ``config.dpi`` is set.
    """
    config = DecoderConfig() if config is None else config
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    if config.dpi is None:
        dpi_source = None
    elif dpi_source is None:
        dpi_source = "given"
    info = ImageInfo(path, int(gray.shape[1]), int(gray.shape[0]), config.dpi, dpi_source)
    if gray.size == 0:
        error = DecodeError(ErrorCode.NO_CANDIDATES, "image is empty")
        return DecodeResult(info, (), (error,))
    if config.polarity == "light":
        return _decode_pass(255 - gray, config, info, "light")
    dark = _decode_pass(gray, config, info, "dark")
    if config.polarity == "dark" or dark.detections:
        return dark
    light = _decode_pass(255 - gray, config, info, "light")
    if light.detections or (_found_nothing(dark) and not _found_nothing(light)):
        return light
    return dark


def _found_nothing(result: DecodeResult) -> bool:
    return any(error.code is ErrorCode.NO_CANDIDATES for error in result.errors)


def decode_file(
    path: str | Path, config: DecoderConfig | None = None, auto_dpi: bool = False
) -> DecodeResult:
    """Load ``path`` and decode it; raises :class:`pharmacode.io.InputError` if unreadable.

    With ``auto_dpi``, the resolution stored in the file (see
    :func:`pharmacode.metadata.read_resolution`) replaces ``config.dpi``;
    when the file has no usable value, ``config.dpi`` is kept as a fallback.
    """
    return load_and_decode(path, config, auto_dpi)[0]


def load_and_decode(
    path: str | Path, config: DecoderConfig | None = None, auto_dpi: bool = False
) -> tuple[DecodeResult, np.ndarray, Resolution | None]:
    """:func:`decode_file`, also returning the loaded image and, with ``auto_dpi``, what
    was read from the file's metadata."""
    config = DecoderConfig() if config is None else config
    image = load_image(path)
    resolution = None
    source = None
    if auto_dpi:
        try:
            resolution = read_resolution(path)
        except OSError:
            resolution = Resolution(None)
        if resolution.dpi is not None:
            config = config.with_updates(dpi=resolution.dpi)
            source = resolution.source
    return decode_image(image, config, str(path), source), image, resolution


def _decode_pass(
    gray: np.ndarray, config: DecoderConfig, info: ImageInfo, polarity: str
) -> DecodeResult:
    """One pass over an image whose bars are dark; ``polarity`` labels the detections."""
    dpi_floor_px = 0
    if config.dpi is not None:
        dpi_floor_px = int(round(config.mm_to_px(config.background_kernel_min_mm)))
    raw_mask = otsu_mask(gray)
    stroke = estimate_stroke_px_past_crossing_lines(raw_mask, config)
    stroke_floor_px = int(config.background_kernel_stroke_factor * stroke) if stroke else 0
    min_kernel_px = max(dpi_floor_px, stroke_floor_px)
    flat = flatten_background(gray, config.background_kernel_fraction, min_kernel_px)
    candidates = find_candidates(flat, config)
    if not candidates:
        error = DecodeError(ErrorCode.NO_CANDIDATES, "no group of aligned bars found")
        return DecodeResult(info, (), (error,))
    detections: list[DecodedPharmacode] = []
    errors: list[DecodeError] = []
    for candidate in candidates:
        sequence = extract_bars(flat, candidate, config, gray.shape)
        if isinstance(sequence, DecodeError):
            errors.append(sequence)
            continue
        value, mirror_value = decode_bars(sequence.kinds)
        confidence = min(sequence.metrics.values()) if sequence.metrics else 0.0
        if confidence < config.min_confidence:
            errors.append(
                DecodeError(
                    ErrorCode.LOW_CONFIDENCE,
                    f"confidence {confidence:.2f} below minimum {config.min_confidence:.2f} "
                    f"(value {value}, mirror {mirror_value})",
                    candidate.bbox,
                )
            )
            continue
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
                polarity=polarity,
            )
        )
    return DecodeResult(info, tuple(detections), tuple(errors))
