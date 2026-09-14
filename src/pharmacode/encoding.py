"""Pure integer math of the one-track Pharmacode format.

A code is a sequence of 2 to 16 bars, each narrow (weight 1) or wide (weight 2).
Reading from the most significant bar, the value is built as
``value = value * 2 + weight`` for every bar. The format therefore covers the
integers 3 (two narrow bars) to 131070 (sixteen wide bars).
"""

from __future__ import annotations

from collections.abc import Iterable

from pharmacode.models import BarKind

MIN_VALUE = 3
MAX_VALUE = 131070
MIN_BARS = 2
MAX_BARS = 16


def encode(value: int) -> tuple[BarKind, ...]:
    """Return the bar sequence for ``value``, most significant bar first.

    Raises ``TypeError`` for non-integers and ``ValueError`` outside
    ``[MIN_VALUE, MAX_VALUE]``.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"value must be an int, got {type(value).__name__}")
    if not MIN_VALUE <= value <= MAX_VALUE:
        raise ValueError(
            f"value {value} is outside the Pharmacode range [{MIN_VALUE}, {MAX_VALUE}]"
        )
    bars: list[BarKind] = []
    remaining = value
    while remaining > 0:
        if remaining % 2 == 1:
            bars.append(BarKind.NARROW)
            remaining = (remaining - 1) // 2
        else:
            bars.append(BarKind.WIDE)
            remaining = (remaining - 2) // 2
    bars.reverse()
    return tuple(bars)


def bars_to_value(bars: Iterable[BarKind]) -> int:
    """Return the value of a bar sequence given most significant bar first.

    Raises ``ValueError`` if the number of bars is outside ``[MIN_BARS, MAX_BARS]``.
    """
    sequence = tuple(bars)
    if not MIN_BARS <= len(sequence) <= MAX_BARS:
        raise ValueError(
            f"a Pharmacode has between {MIN_BARS} and {MAX_BARS} bars, got {len(sequence)}"
        )
    value = 0
    for bar in sequence:
        value = value * 2 + BarKind(bar).weight
    return value
