from __future__ import annotations

import numpy as np
import pytest

from pharmacode.detection import (
    candidate_from_chain,
    find_bar_components,
    find_candidates,
    group_bars,
)
from pharmacode.encoding import encode
from pharmacode.imageops import flatten_background, otsu_mask
from pharmacode.models import DecoderConfig
from pharmacode.rendering import Distortion, RenderSpec, compose_scene, distort, render_value

CONFIG = DecoderConfig()


def test_bar_components_of_clean_code() -> None:
    bars = find_bar_components(otsu_mask(render_value(1234)), CONFIG)
    assert len(bars) == len(encode(1234))
    assert all(abs(bar.angle_deg - 90.0) < 0.5 for bar in bars)
    assert all(abs(bar.length - RenderSpec().px(8.0)) <= 1.5 for bar in bars)
    thicknesses = sorted(round(bar.thickness) for bar in bars)
    assert thicknesses[0] == 6 and thicknesses[-1] == 18


def test_bar_components_after_quarter_turn_are_horizontal() -> None:
    image = distort(render_value(1234), Distortion(rotation_deg=90))
    bars = find_bar_components(otsu_mask(image), CONFIG)
    assert len(bars) == 10 and all(bar.angle_deg < 0.5 or bar.angle_deg > 179.5 for bar in bars)


def test_bar_components_reject_specks_and_blobs() -> None:
    mask = np.zeros((200, 200), np.uint8)
    mask[10:13, 10:13] = 255  # speck
    mask[50:150, 50:150] = 255  # square blob
    mask[20:180, 170:172] = 255  # a real bar
    bars = find_bar_components(mask, CONFIG)
    assert len(bars) == 1 and bars[0].length > 150


def test_group_bars_keeps_one_code_together() -> None:
    bars = find_bar_components(otsu_mask(render_value(12345)), CONFIG)
    groups = group_bars(bars, CONFIG)
    assert len(groups) == 1 and len(groups[0]) == 13
    xs = [bar.cx for bar in groups[0]]
    assert xs == sorted(xs)


def test_group_bars_separates_two_codes_on_one_axis() -> None:
    code_a, code_b = render_value(1234), render_value(4321)
    scene = compose_scene(
        (code_a.shape[0], code_a.shape[1] + code_b.shape[1] + 40),
        [(code_a, 0, 0), (code_b, code_a.shape[1] + 40, 0)],
    )
    groups = group_bars(find_bar_components(otsu_mask(scene), CONFIG), CONFIG)
    expected = sorted([len(encode(1234)), len(encode(4321))])
    assert sorted(len(group) for group in groups) == expected


def test_group_bars_separates_stacked_codes() -> None:
    code = render_value(1234)
    scene = compose_scene(
        (code.shape[0] * 2 + 20, code.shape[1]), [(code, 0, 0), (code, 0, code.shape[0] + 20)]
    )
    groups = group_bars(find_bar_components(otsu_mask(scene), CONFIG), CONFIG)
    assert len(groups) == 2


def test_group_bars_ignores_lonely_bar() -> None:
    mask = np.zeros((200, 400), np.uint8)
    mask[20:180, 100:106] = 255
    assert group_bars(find_bar_components(mask, CONFIG), CONFIG) == []


@pytest.mark.parametrize(
    ("rotation", "expected"), [(0, 0.0), (90, 90.0), (180, 0.0), (270, 90.0), (7, -7.0), (-5, 5.0)]
)
def test_candidate_orientation(rotation: float, expected: float) -> None:
    image = distort(render_value(1234), Distortion(rotation_deg=rotation))
    bars = find_bar_components(otsu_mask(image), CONFIG)
    [chain] = group_bars(bars, CONFIG)
    candidate = candidate_from_chain(chain, CONFIG, image.shape)
    assert candidate.orientation_deg == pytest.approx(expected, abs=0.6)
    box = candidate.bbox
    assert box.x >= 0 and box.y >= 0
    assert box.x + box.width <= image.shape[1] and box.y + box.height <= image.shape[0]
    assert all(box.x <= bar.cx <= box.x + box.width for bar in chain)


def test_candidate_bbox_includes_quiet_zone_room() -> None:
    image = render_value(1234)
    [chain] = group_bars(find_bar_components(otsu_mask(image), CONFIG), CONFIG)
    box = candidate_from_chain(chain, CONFIG, image.shape).bbox
    first, last = min(b.cx for b in chain), max(b.cx for b in chain)
    assert first - box.x >= RenderSpec().px(6.0) and box.x + box.width - last >= RenderSpec().px(
        6.0
    )


def test_find_candidates_on_blank_and_on_code() -> None:
    blank = np.full((300, 300), 255, np.uint8)
    assert find_candidates(flatten_background(blank, 0.05), CONFIG) == []
    noisy = np.clip(255 - np.abs(np.random.default_rng(1).normal(0, 3, (300, 300))), 0, 255).astype(
        np.uint8
    )
    assert find_candidates(flatten_background(noisy, 0.05), CONFIG) == []
    assert len(find_candidates(flatten_background(render_value(99), 0.05), CONFIG)) == 1
