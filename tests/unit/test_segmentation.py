from __future__ import annotations

import numpy as np
import pytest

from pharmacode.encoding import encode
from pharmacode.models import BarKind, BarSequence, DecodeError, DecoderConfig, ErrorCode
from pharmacode.rendering import RenderSpec, render_bars, render_value
from pharmacode.segmentation import (
    bar_profile,
    classify_widths,
    extract_bars_from_upright,
    measure_runs,
    runs_from_profile,
    validate_quiet_zone,
    validate_shape,
)

N, W = BarKind.NARROW, BarKind.WIDE


def test_runs_from_profile_alternates_bars_and_spaces() -> None:
    profile = np.array([0, 0, 1, 1, 1, 0, 1, 0, 0], dtype=np.float32)
    runs = runs_from_profile(profile, 0.5)
    assert runs == [(False, 0, 2), (True, 2, 3), (False, 5, 1), (True, 6, 1), (False, 7, 2)]
    bars, gaps, leading, trailing = measure_runs(runs)
    assert bars == [(2, 3), (6, 1)] and gaps == [1] and (leading, trailing) == (2, 2)


def test_measure_runs_profile_starting_with_a_bar() -> None:
    runs = runs_from_profile(np.array([1, 1, 0, 1, 0, 0], dtype=np.float32), 0.5)
    bars, gaps, leading, trailing = measure_runs(runs)
    assert bars == [(0, 2), (3, 1)] and gaps == [1] and (leading, trailing) == (0, 2)


def test_measure_runs_single_run() -> None:
    assert measure_runs(runs_from_profile(np.zeros(5, dtype=np.float32), 0.5)) == ([], [], 5, 0)
    ones_runs = runs_from_profile(np.ones(5, dtype=np.float32), 0.5)
    assert measure_runs(ones_runs) == ([(0, 5)], [], 0, 0)


def test_bar_profile_uses_central_band() -> None:
    mask = np.zeros((20, 10), dtype=np.uint8)
    mask[2:18, 3:5] = 255
    mask[0:2, 7:9] = 255  # a speck above the bars must not count
    profile, rows = bar_profile(mask, 0.6)
    assert rows == (0, 17)
    assert profile[3] == 1.0 and profile[4] == 1.0 and profile[7] == 0.0


def test_classify_two_classes() -> None:
    kinds, warnings, metrics = classify_widths([6, 18, 6, 18, 18], [12] * 4, DecoderConfig())
    assert kinds == (N, W, N, W, W)
    assert warnings == () and metrics["width_margin"] > 0.9


def test_classify_single_class_with_dpi_uses_physical_boundary() -> None:
    config = DecoderConfig(dpi=300.0)
    kinds, warnings, _ = classify_widths([6, 6, 6], [12, 12], config)
    assert kinds == (N, N, N) and "single_width_class" in warnings
    kinds, _, _ = classify_widths([18, 18], [12], config)
    assert kinds == (W, W)


def test_classify_single_class_without_dpi_uses_gap_ruler() -> None:
    kinds, warnings, metrics = classify_widths([6, 6, 6], [12, 12], DecoderConfig())
    assert kinds == (N, N, N) and "single_width_class_no_dpi" in warnings
    assert metrics["width_margin"] <= 0.5
    kinds, _, _ = classify_widths([18, 18], [12], DecoderConfig())
    assert kinds == (W, W)


def test_classify_rejects_smeared_widths() -> None:
    result = classify_widths([6, 8, 10, 13, 16, 18], [12] * 5, DecoderConfig())
    assert isinstance(result, DecodeError)
    assert result.code in (ErrorCode.WIDTH_CLASSES_NOT_SEPARABLE, ErrorCode.AMBIGUOUS_WIDTH)


def test_classify_flags_bar_on_boundary() -> None:
    result = classify_widths([6, 18, 10, 11], [12] * 3, DecoderConfig())
    assert isinstance(result, DecodeError)


def test_classify_flags_bar_between_classes_as_ambiguous() -> None:
    result = classify_widths([6, 18, 6, 10, 18], [12] * 4, DecoderConfig())
    assert isinstance(result, DecodeError) and result.code is ErrorCode.AMBIGUOUS_WIDTH
    assert "10 px" in result.message


def test_classify_assigns_low_dpi_widths_by_pixel_tolerance() -> None:
    kinds, _, _ = classify_widths([2, 3, 8, 9, 3], [6] * 4, DecoderConfig())
    assert kinds == (N, N, W, W, N)


def test_validate_shape_rejects_ragged_heights_and_gaps() -> None:
    config = DecoderConfig()
    error = validate_shape([90, 90, 60], [12, 12], config)
    assert isinstance(error, DecodeError) and error.code is ErrorCode.INCONSISTENT_BAR_HEIGHT
    error = validate_shape([90, 90, 90], [12, 40], config)
    assert isinstance(error, DecodeError) and error.code is ErrorCode.INCONSISTENT_GAPS
    # a 1.7x outlier gap among otherwise-uniform gaps: accepted under the old
    # (0.5, 2.0) window, rejected once it is tightened to (0.6, 1.5) (see
    # DecoderConfig.gap_ratio_range)
    assert isinstance(validate_shape([90, 90, 90, 90], [12, 12, 20], config), DecodeError)
    warnings, metrics = validate_shape([90, 92, 89], [12, 13], config)
    assert (
        warnings == () and metrics["height_consistency"] > 0.8 and metrics["gap_consistency"] > 0.8
    )


def test_validate_quiet_zone_with_and_without_dpi() -> None:
    error = validate_quiet_zone(10, 90, [6, 18], (N, W), DecoderConfig())
    assert isinstance(error, DecodeError) and error.code is ErrorCode.QUIET_ZONE_VIOLATION
    warnings, metrics = validate_quiet_zone(40, 90, [6, 18], (N, W), DecoderConfig())
    assert "quiet_zone_below_nominal" in warnings and metrics["quiet_zone_margin"] < 1.0
    warnings, metrics = validate_quiet_zone(95, 95, [6, 18], (N, W), DecoderConfig(dpi=300.0))
    assert warnings == () and metrics["quiet_zone_margin"] == 1.0


def test_extract_bars_from_upright_clean_render() -> None:
    image = render_value(1234)
    sequence = extract_bars_from_upright(image, DecoderConfig(dpi=300.0))
    assert isinstance(sequence, BarSequence)
    assert sequence.kinds == encode(1234)
    assert sequence.bar_widths_px == tuple(RenderSpec().bar_width_px(k) for k in encode(1234))
    assert sequence.quiet_zone_px == (95, 95)


def test_extract_bars_reports_tight_crop_as_quiet_zone_violation() -> None:
    image = render_value(1234)
    cropped = image[:, 90:-90]
    error = extract_bars_from_upright(cropped, DecoderConfig())
    assert isinstance(error, DecodeError) and error.code is ErrorCode.QUIET_ZONE_VIOLATION


def test_extract_bars_on_blank_image_is_too_few_bars() -> None:
    error = extract_bars_from_upright(np.full((50, 200), 255, np.uint8), DecoderConfig())
    assert isinstance(error, DecodeError) and error.code is ErrorCode.TOO_FEW_BARS


@pytest.mark.parametrize("count", [17, 20])
def test_extract_bars_too_many(count: int) -> None:
    image = render_bars((N,) * count)
    error = extract_bars_from_upright(image, DecoderConfig())
    assert isinstance(error, DecodeError) and error.code is ErrorCode.TOO_MANY_BARS
