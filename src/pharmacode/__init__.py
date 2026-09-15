"""Toolkit for generating, detecting and decoding one-track Pharmacode."""

from __future__ import annotations

from pharmacode.decoding import decode_bars
from pharmacode.encoding import MAX_BARS, MAX_VALUE, MIN_BARS, MIN_VALUE, bars_to_value, encode
from pharmacode.models import (
    BarKind,
    BoundingBox,
    DecodedPharmacode,
    DecodeError,
    DecoderConfig,
    DecodeResult,
    ErrorCode,
    ImageInfo,
)
from pharmacode.rendering import (
    NEGATIVE_KINDS,
    Distortion,
    RenderSpec,
    compose_scene,
    distort,
    render_bars,
    render_negative,
    render_value,
)

__version__ = "0.1.0.dev0"

__all__ = [
    "MAX_BARS",
    "MAX_VALUE",
    "MIN_BARS",
    "MIN_VALUE",
    "BarKind",
    "BoundingBox",
    "DecodeError",
    "DecodedPharmacode",
    "DecodeResult",
    "DecoderConfig",
    "Distortion",
    "ErrorCode",
    "ImageInfo",
    "NEGATIVE_KINDS",
    "RenderSpec",
    "__version__",
    "bars_to_value",
    "compose_scene",
    "decode_bars",
    "distort",
    "encode",
    "render_bars",
    "render_negative",
    "render_value",
]
