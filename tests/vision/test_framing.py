"""Codes cropped tight to their bars, or crossed by a thin rule, from usertests/.

usertests/pharma5.png (40 px bars in a 510 px image, quiet zone cut by the crop)
and usertests/pharma6.png (a 5 px rule crossing all nine bars) exposed two
failure modes no synthetic benchmark image had triggered: a background-
flattening kernel undersized relative to the bar strokes washes wide bars out
to their edges (Problem A), and a thin rule crossing every bar merges them
into one component the plain detection pass discards (Problem B). Both are
reproduced here without any real image. Problem C (``allow_truncated_quiet_zone``)
is opt-in tolerance for the first case; it must never excuse ink that sits
inside the image, only a quiet zone cut by the image border itself.
"""

from __future__ import annotations

import numpy as np

from pharmacode.detection import find_candidates
from pharmacode.models import DecoderConfig, ErrorCode
from pharmacode.pipeline import decode_image
from pharmacode.rendering import Distortion, RenderSpec, distort, render_value


def test_code_filling_the_frame_is_never_misread() -> None:
    """A code cropped to a thin margin (bars 35 px wide in a ~500 px image, no room for the
    full quiet zone) must decode 1234 or nothing at all — never a different value read off
    the washed-out edges of its own wide bars (see usertests/pharma5.png)."""
    spec = RenderSpec(dpi=600.0)
    image = render_value(1234, spec)
    border = spec.px(spec.quiet_zone_mm) + spec.px(spec.margin_mm)
    margin = 30
    cropped = image[border - margin : -(border - margin), border - margin : -(border - margin)]
    for dpi in (None, 600.0):
        default_result = decode_image(cropped, DecoderConfig(dpi=dpi))
        if default_result.detections:
            assert len(default_result.detections) == 1, default_result.to_dict()
            assert default_result.detections[0].value == 1234, default_result.to_dict()
        else:
            assert any(
                error.code is ErrorCode.QUIET_ZONE_VIOLATION for error in default_result.errors
            ), default_result.to_dict()

        flagged = decode_image(cropped, DecoderConfig(dpi=dpi, allow_truncated_quiet_zone=True))
        assert len(flagged.detections) == 1, flagged.to_dict()
        detection = flagged.detections[0]
        assert detection.value == 1234
        assert "quiet_zone_truncated_by_image_edge" in detection.warnings
        assert detection.confidence < 1.0


def test_thin_line_crossing_the_code_is_ignored() -> None:
    """A 5 px dark rule through the bars (usertests/pharma6.png) must not turn into
    NO_CANDIDATES; the directional-opening fallback removes it and decodes normally,
    upright or rotated a quarter turn, with or without DPI."""
    spec = RenderSpec(dpi=300.0)
    for value in (25, 1234):
        image = render_value(value, spec).copy()
        mid = image.shape[0] // 2
        image[mid : mid + 5, :] = 90  # thin dark rule across the full width
        for dpi in (None, 300.0):
            result = decode_image(image, DecoderConfig(dpi=dpi))
            assert len(result.detections) == 1, (value, dpi, result.to_dict())
            assert result.detections[0].value == value

    rotated = distort(render_value(1234, spec), Distortion(rotation_deg=90))
    mid = rotated.shape[1] // 2
    rotated[:, mid : mid + 5] = 90  # rule perpendicular to the now-horizontal bars
    result = decode_image(rotated, DecoderConfig(dpi=300.0))
    assert len(result.detections) == 1, result.to_dict()
    detection = result.detections[0]
    assert 1234 in (detection.value, detection.mirror_value)


def test_truncated_quiet_zone_flag_does_not_excuse_ink_neighbours() -> None:
    """A dark mark sitting a few pixels past the last bar, well inside the image (not at its
    border), still violates the quiet zone even with the flag on: the flag only concerns a
    zone cut by the image edge, not one shortened by real neighbouring ink."""
    height, width = 100, 300
    image = np.full((height, width), 255, np.uint8)
    top, bar_height = 40, 20
    x = 60
    image[top : top + bar_height, x : x + 2] = 0  # bar 1, narrow, 2 px
    x += 2 + 6  # a normal 6 px gap
    image[top : top + bar_height, x : x + 2] = 0  # bar 2, narrow, 2 px
    last_bar_right = x + 2
    block_x0 = last_bar_right + 5  # 5 px past the last bar, as specified
    image[top : top + bar_height, block_x0 : block_x0 + 12] = 0  # 12 px wide ink neighbour

    config = DecoderConfig(allow_truncated_quiet_zone=True)
    result = decode_image(image, config)
    assert result.detections == (), result.to_dict()
    assert [e.code for e in result.errors] == [ErrorCode.QUIET_ZONE_VIOLATION], result.to_dict()
    # the candidate never reaches the image border, so nothing here is "truncated"
    box = result.errors[0].bbox
    assert box is not None and box.x > 0 and box.x + box.width < width


def test_cropped_code_default_is_error() -> None:
    """A code cropped to 2 px margins is a QUIET_ZONE_VIOLATION by default, and decodes once
    --allow-cropped-quiet-zone (allow_truncated_quiet_zone) is set."""
    spec = RenderSpec(dpi=300.0)
    image = render_value(1234, spec)
    border = spec.px(spec.quiet_zone_mm) + spec.px(spec.margin_mm)
    margin = 2
    cropped = image[:, border - margin : -(border - margin)]

    result = decode_image(cropped, DecoderConfig(dpi=300.0))
    assert result.detections == (), result.to_dict()
    assert [e.code for e in result.errors] == [ErrorCode.QUIET_ZONE_VIOLATION]

    flagged = decode_image(cropped, DecoderConfig(dpi=300.0, allow_truncated_quiet_zone=True))
    assert len(flagged.detections) == 1, flagged.to_dict()
    assert flagged.detections[0].value == 1234


def test_negative_orientation_leading_truncation_is_the_bottom_not_the_top() -> None:
    """Rotating 1234 by 60 degrees (``Distortion(rotation_deg=60)``) yields
    orientation about -60. The canonical axis then has ``uy < 0``, so the leading
    (first-read) end of the bar chain sits at the BOTTOM of the image, not the top --
    before the fix, ``extract_bars`` always treated the top as leading, so a quiet zone
    truncated at the bottom was never excused by ``--allow-cropped-quiet-zone`` even
    though it genuinely touches the image border.

    Built from a tight, all-sides crop (so the rendered quiet zone no longer masks the
    effect) with generous headroom pasted back on the trailing (upright-right) side: after
    the 60-degree rotation this headroom becomes the trailing quiet zone, comfortably clear
    of the image border, while the tight crop becomes the leading (bottom) truncation. The
    miniature spec keeps the geometry (bar height vs. quiet zone) small enough that a crop
    tight to the bars alone already crosses the hard limit -- see
    ``tests/unit/test_segmentation.py`` for ``_truncated_sides`` itself, exercised directly
    across all four orientation signs.
    """
    spec = RenderSpec.miniature(dpi=300.0)
    image = render_value(1234, spec)
    border = spec.px(spec.quiet_zone_mm) + spec.px(spec.margin_mm)
    margin = 2
    trimmed = image[border - margin : -(border - margin), border - margin :]
    # rotate_bound expands the canvas to bound the whole rotated rectangle, so this extra
    # headroom on the trailing side becomes a generous, non-touching trailing quiet zone.
    padded = np.pad(trimmed, ((0, 0), (0, 200)), constant_values=255)
    rotated = distort(padded, Distortion(rotation_deg=60))

    config = DecoderConfig(dpi=300.0)
    candidates = find_candidates(rotated, config)
    assert len(candidates) == 1, candidates
    assert candidates[0].orientation_deg < -45  # confirms the negative-orientation case

    default_result = decode_image(rotated, config)
    assert default_result.detections == (), default_result.to_dict()
    assert [e.code for e in default_result.errors] == [ErrorCode.QUIET_ZONE_VIOLATION]

    flagged = decode_image(rotated, DecoderConfig(dpi=300.0, allow_truncated_quiet_zone=True))
    assert len(flagged.detections) == 1, flagged.to_dict()
    detection = flagged.detections[0]
    assert 1234 in (detection.value, detection.mirror_value)
    assert "quiet_zone_truncated_by_image_edge" in detection.warnings
