from __future__ import annotations

import json
from pathlib import Path

from pharmacode.cli import EXIT_INPUT, EXIT_OK, EXIT_USAGE, main
from pharmacode.io import load_image
from pharmacode.models import BarSequence, DecoderConfig
from pharmacode.segmentation import extract_bars_from_upright


def test_generate_writes_decodable_png(tmp_path: Path, capsys) -> None:
    target = tmp_path / "sample.png"
    assert main(["generate", "--value", "1234", "--dpi", "300", "--output", str(target)]) == EXIT_OK
    summary = json.loads(capsys.readouterr().out)
    assert summary["value"] == 1234 and summary["bars"][0] == "narrow"
    sequence = extract_bars_from_upright(load_image(target), DecoderConfig(dpi=300.0))
    assert isinstance(sequence, BarSequence)


def test_generate_rejects_out_of_range_value(tmp_path: Path, capsys) -> None:
    assert main(["generate", "--value", "2", "--output", str(tmp_path / "x.png")]) == EXIT_USAGE
    assert "range" in capsys.readouterr().err


def test_generate_rejects_bad_dpi(tmp_path: Path) -> None:
    assert (
        main(["generate", "--value", "5", "--dpi", "0", "--output", str(tmp_path / "x.png")])
        == EXIT_USAGE
    )


def test_generate_reports_unwritable_output(tmp_path: Path) -> None:
    target = tmp_path / "missing-dir" / "x.png"
    assert main(["generate", "--value", "5", "--output", str(target)]) == EXIT_INPUT


def test_generate_with_distortions_is_seeded(tmp_path: Path) -> None:
    args = ["generate", "--value", "91", "--rotation", "90", "--noise", "12", "--seed", "7"]
    assert main([*args, "--output", str(tmp_path / "a.png")]) == EXIT_OK
    assert main([*args, "--output", str(tmp_path / "b.png")]) == EXIT_OK
    a, b = load_image(tmp_path / "a.png"), load_image(tmp_path / "b.png")
    assert a.shape == b.shape and (a == b).all()
