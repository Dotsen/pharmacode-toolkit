"""Toolkit for generating, detecting and decoding one-track Pharmacode."""

from __future__ import annotations

from pharmacode.debug import DebugRecorder
from pharmacode.decoding import decode_bars
from pharmacode.detection import find_candidates
from pharmacode.encoding import MAX_BARS, MAX_VALUE, MIN_BARS, MIN_VALUE, bars_to_value, encode
from pharmacode.geometry import geometry_report
from pharmacode.io import InputError, load_image, save_image
from pharmacode.metadata import Resolution, read_resolution
from pharmacode.models import (
    BarKind,
    BarSequence,
    BoundingBox,
    DecodedPharmacode,
    DecodeError,
    DecoderConfig,
    DecodeResult,
    DetectionCandidate,
    ErrorCode,
    ImageInfo,
)
from pharmacode.pipeline import decode_file, decode_image
from pharmacode.rendering import (
    NEGATIVE_KINDS,
    Distortion,
    RenderSpec,
    compose_scene,
    distort,
    render_bars,
    render_negative,
    render_svg,
    render_value,
)
from pharmacode.segmentation import extract_bars_from_upright
from pharmacode.visualization import annotate

__version__ = "0.2.1"

__all__ = [
    "MAX_BARS",
    "MAX_VALUE",
    "MIN_BARS",
    "MIN_VALUE",
    "BarKind",
    "BarSequence",
    "BoundingBox",
    "DebugRecorder",
    "DecodeError",
    "DecodedPharmacode",
    "DecodeResult",
    "DecoderConfig",
    "DetectionCandidate",
    "Distortion",
    "ErrorCode",
    "ImageInfo",
    "InputError",
    "NEGATIVE_KINDS",
    "RenderSpec",
    "Resolution",
    "__version__",
    "annotate",
    "bars_to_value",
    "compose_scene",
    "decode_bars",
    "decode_file",
    "decode_image",
    "distort",
    "encode",
    "extract_bars_from_upright",
    "find_candidates",
    "geometry_report",
    "load_image",
    "read_resolution",
    "render_bars",
    "render_negative",
    "render_svg",
    "render_value",
    "save_image",
]
