from __future__ import annotations

from pharmacode.decoding import check_bar_count, decode_bars
from pharmacode.encoding import encode
from pharmacode.models import DecoderConfig, ErrorCode


def test_decode_bars_returns_both_readings() -> None:
    assert decode_bars(encode(4)) == (4, 5)
    assert decode_bars(encode(1234)) == (1234, 1835)


def test_check_bar_count_uses_config_limits() -> None:
    config = DecoderConfig()
    assert check_bar_count(2, config) is None
    assert check_bar_count(16, config) is None
    assert check_bar_count(1, config).code is ErrorCode.TOO_FEW_BARS
    assert check_bar_count(17, config).code is ErrorCode.TOO_MANY_BARS
    strict = config.with_updates(min_bars=4, max_bars=8)
    assert check_bar_count(3, strict).code is ErrorCode.TOO_FEW_BARS
    assert check_bar_count(9, strict).code is ErrorCode.TOO_MANY_BARS
