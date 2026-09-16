from __future__ import annotations

from pharmacode.models import DecoderConfig
from pharmacode.pipeline import decode_image
from pharmacode.rendering import Distortion, compose_scene, distort, render_value


def test_three_codes_with_mixed_orientation() -> None:
    a = render_value(91)
    b = distort(render_value(25), Distortion(rotation_deg=90))
    c = render_value(131070)
    scene = compose_scene((900, 1200), [(a, 30, 30), (b, 900, 40), (c, 40, 520)])
    result = decode_image(scene, DecoderConfig(dpi=300.0))
    assert result.ok, [e.to_dict() for e in result.errors]
    readings = {frozenset((d.value, d.mirror_value)) for d in result.detections}
    assert readings == {frozenset((91, 77)), frozenset((25, 20)), frozenset((131070,))}


def test_two_codes_on_one_axis() -> None:
    a, b = render_value(1234), render_value(4321)
    scene = compose_scene(
        (a.shape[0], a.shape[1] + b.shape[1] + 40), [(a, 0, 0), (b, a.shape[1] + 40, 0)]
    )
    result = decode_image(scene, DecoderConfig(dpi=300.0))
    assert result.ok and sorted(d.value for d in result.detections) == [1234, 4321]
    assert result.detections[0].bbox.x < result.detections[1].bbox.x
