from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pharmacode.cli import EXIT_OK, main
from pharmacode.debug import DebugRecorder
from pharmacode.io import load_image, save_image
from pharmacode.models import DecoderConfig
from pharmacode.pipeline import decode_image
from pharmacode.rendering import compose_scene, render_value


def test_recorder_keeps_every_stage_and_candidate() -> None:
    scene = compose_scene((500, 800), [(render_value(91), 20, 20), (render_value(25), 20, 280)])
    debug = DebugRecorder()
    result = decode_image(scene, DecoderConfig(dpi=300.0), debug=debug)
    assert {d.value for d in result.detections} == {91, 25}
    names = set(debug.images)
    assert {"dark-1-input.png", "dark-2-flattened.png", "dark-3-mask.png"} <= names
    assert {"dark-4-candidates.png", "dark-candidate-0.png", "dark-candidate-1.png"} <= names
    (only_pass,) = debug.passes
    outcomes = [record["outcome"] for record in only_pass["candidates"]]
    assert all("bars" in outcome for outcome in outcomes)
    assert only_pass["candidates"][0]["bar_widths_px"]


def test_recorder_records_the_error_of_a_rejected_candidate() -> None:
    code = render_value(1234)
    tight = code[:, 60:-60]  # quiet zones cut away
    debug = DebugRecorder()
    result = decode_image(tight, DecoderConfig(dpi=300.0), debug=debug)
    assert not result.detections
    outcome = debug.passes[0]["candidates"][0]["outcome"]
    assert outcome["error"] == "QUIET_ZONE_VIOLATION"


def test_auto_polarity_records_both_passes() -> None:
    debug = DebugRecorder()
    decode_image(255 - render_value(1234), DecoderConfig(polarity="auto"), debug=debug)
    assert [p["polarity"] for p in debug.passes] == ["dark", "light"]
    assert "light-candidate-0.png" in debug.images


def test_blank_image_still_records_its_stages() -> None:
    debug = DebugRecorder()
    decode_image(np.full((100, 200), 255, dtype=np.uint8), debug=debug)
    assert debug.passes == [{"polarity": "dark", "background_kernel_floor_px": 0, "candidates": []}]
    assert "dark-2-flattened.png" in debug.images


def test_save_writes_images_and_json(tmp_path: Path) -> None:
    debug = DebugRecorder()
    decode_image(render_value(1234), DecoderConfig(dpi=300.0), debug=debug)
    written = debug.save(tmp_path / "new" / "dir")
    assert {path.name for path in written} == set(debug.images) | {"debug.json"}
    panel = load_image(tmp_path / "new" / "dir" / "dark-candidate-0.png")
    assert panel.shape[0] > 100
    report = json.loads((tmp_path / "new" / "dir" / "debug.json").read_text(encoding="utf-8"))
    assert report["passes"][0]["candidates"][0]["outcome"]["confidence"] == 1.0


def test_decode_debug_dir(tmp_path: Path, capsys) -> None:
    source = tmp_path / "code.png"
    save_image(source, render_value(1234))
    assert main(["decode", str(source), "--debug-dir", str(tmp_path / "debug")]) == EXIT_OK
    assert (tmp_path / "debug" / "debug.json").is_file()
    assert (tmp_path / "debug" / "dark-4-candidates.png").is_file()
    assert json.loads(capsys.readouterr().out)["detections"][0]["value"] == 1234
