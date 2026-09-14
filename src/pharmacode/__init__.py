"""Toolkit for generating, detecting and decoding one-track Pharmacode."""

from __future__ import annotations

from pharmacode.encoding import MAX_BARS, MAX_VALUE, MIN_BARS, MIN_VALUE, bars_to_value, encode
from pharmacode.models import BarKind

__version__ = "0.1.0.dev0"

__all__ = [
    "MAX_BARS",
    "MAX_VALUE",
    "MIN_BARS",
    "MIN_VALUE",
    "BarKind",
    "__version__",
    "bars_to_value",
    "encode",
]
