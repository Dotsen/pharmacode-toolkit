"""Data model for Pharmacode results."""

from __future__ import annotations

from enum import Enum


class BarKind(str, Enum):
    """Width class of one bar. One-track Pharmacode uses exactly two classes."""

    NARROW = "narrow"
    WIDE = "wide"

    @property
    def weight(self) -> int:
        """Numeric weight of the bar in the encoding: narrow 1, wide 2."""
        return 2 if self is BarKind.WIDE else 1
