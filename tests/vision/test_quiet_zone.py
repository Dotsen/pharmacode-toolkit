from __future__ import annotations

from pharmacode.models import DecoderConfig, ErrorCode
from pharmacode.pipeline import decode_image
from pharmacode.rendering import RenderSpec, compose_scene, render_value
from tests.conftest import single

SPEC = RenderSpec()
BORDER = SPEC.px(6.0) + SPEC.px(2.0)


def test_code_at_image_corner_with_nominal_quiet_zone() -> None:
    code = render_value(1234)
    scene = compose_scene((code.shape[0] + 200, code.shape[1] + 300), [(code, 0, 0)])
    assert single(decode_image(scene, DecoderConfig(dpi=300.0))).value == 1234


def test_quiet_zone_below_nominal_is_a_warning() -> None:
    code = render_value(1234)
    trimmed = code[:, BORDER - 50 : -(BORDER - 50)]  # 50 px = 4.2 mm each side
    detection = single(decode_image(trimmed, DecoderConfig(dpi=300.0)))
    assert detection.value == 1234 and "quiet_zone_below_nominal" in detection.warnings
    assert detection.confidence < 0.8


def test_quiet_zone_below_half_nominal_is_an_error() -> None:
    code = render_value(1234)
    trimmed = code[:, BORDER - 20 : -(BORDER - 20)]  # 20 px = 1.7 mm each side
    result = decode_image(trimmed, DecoderConfig(dpi=300.0))
    assert not result.detections
    assert [e.code for e in result.errors] == [ErrorCode.QUIET_ZONE_VIOLATION]


def test_codes_too_close_are_not_read_as_two_values() -> None:
    code_a, code_b = render_value(4), render_value(5)
    inner_a = code_a[:, BORDER:-BORDER]
    inner_b = code_b[:, BORDER:-BORDER]
    scene = compose_scene(
        (code_a.shape[0], inner_a.shape[1] + inner_b.shape[1] + 30 + 2 * BORDER),
        [(inner_a, BORDER, BORDER), (inner_b, BORDER + inner_a.shape[1] + 30, BORDER)],
    )
    result = decode_image(scene, DecoderConfig(dpi=300.0))
    assert len(result.detections) < 2
    assert result.errors or result.detections[0].value not in (4, 5)


def test_codes_separated_by_one_gap_are_rejected_not_merged() -> None:
    code_a, code_b = render_value(4), render_value(5)
    inner_a, inner_b = code_a[:, BORDER:-BORDER], code_b[:, BORDER:-BORDER]
    scene = compose_scene(
        (code_a.shape[0], inner_a.shape[1] + inner_b.shape[1] + 20 + 2 * BORDER),
        [(inner_a, BORDER, BORDER), (inner_b, BORDER + inner_a.shape[1] + 20, BORDER)],
    )
    result = decode_image(scene, DecoderConfig(dpi=300.0))
    assert result.detections == ()
    assert {e.code for e in result.errors} == {ErrorCode.INCONSISTENT_GAPS}


def test_partial_overlap_with_a_thin_line_is_recovered_not_merged() -> None:
    """A rule thin enough to qualify for the crossing-line fallback (see
    detection.find_candidates and tests/vision/test_framing.py) decodes normally instead
    of merging every bar into one rejected component."""
    code = render_value(1234)
    scene = code.copy()
    scene[code.shape[0] // 2 : code.shape[0] // 2 + 3, :] = 0  # a rule through the code
    result = decode_image(scene, DecoderConfig(dpi=300.0))
    assert single(result).value == 1234
