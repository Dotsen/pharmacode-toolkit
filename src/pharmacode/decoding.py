"""Turn a classified bar sequence into both reading directions."""

from __future__ import annotations

from collections.abc import Sequence

from pharmacode.encoding import bars_to_value
from pharmacode.models import BarKind, DecodeError, DecoderConfig, ErrorCode


def decode_bars(kinds: Sequence[BarKind]) -> tuple[int, int]:
    """Return ``(value, mirror_value)``.

    ``value`` reads the sequence as given (most significant bar first);
    ``mirror_value`` reads it reversed. Both are computed independently and no
    heuristic prefers one over the other: the format itself does not encode
    the reading direction.
    """
    sequence = tuple(kinds)
    return bars_to_value(sequence), bars_to_value(tuple(reversed(sequence)))


def check_bar_count(count: int, config: DecoderConfig) -> DecodeError | None:
    """Return a ``DecodeError`` if ``count`` is outside the configured range."""
    if count < config.min_bars:
        return DecodeError(
            ErrorCode.TOO_FEW_BARS, f"found {count} bars, minimum is {config.min_bars}"
        )
    if count > config.max_bars:
        return DecodeError(
            ErrorCode.TOO_MANY_BARS, f"found {count} bars, maximum is {config.max_bars}"
        )
    return None
