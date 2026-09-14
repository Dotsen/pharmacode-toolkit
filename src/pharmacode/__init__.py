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
    "ErrorCode",
    "ImageInfo",
    "__version__",
    "bars_to_value",
    "decode_bars",
    "encode",
]
