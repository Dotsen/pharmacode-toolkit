from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pharmacode.cli import (
    EXIT_INPUT,
    EXIT_NO_CANDIDATES,
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_USAGE,
    EXIT_VALIDATION_FAILED,
    exit_code_for,
    main,
)
from pharmacode.io import load_image, save_image
from pharmacode.models import (
    BarSequence,
    BoundingBox,
    DecodedPharmacode,
    DecodeError,
    DecoderConfig,
    DecodeResult,
    ErrorCode,
    ImageInfo,
)
from pharmacode.rendering import render_value
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


def test_decode_command_success(tmp_path: Path, capsys) -> None:
    source = tmp_path / "code.png"
    save_image(source, render_value(1234))
    json_out, annotated = tmp_path / "r.json", tmp_path / "r.png"
    code = main(
        [
            "decode",
            str(source),
            "--dpi",
            "300",
            "--json",
            str(json_out),
            "--annotated",
            str(annotated),
        ]
    )
    assert code == EXIT_OK
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["detections"][0]["value"] == 1234 and payload["image"]["dpi"] == 300.0
    assert annotated.exists() and capsys.readouterr().out == ""


def test_decode_command_prints_json_to_stdout(tmp_path: Path, capsys) -> None:
    source = tmp_path / "code.png"
    save_image(source, render_value(25))
    assert main(["decode", str(source)]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["detections"][0]["mirror_value"] == 20


def test_decode_command_exit_codes(tmp_path: Path, capsys) -> None:
    blank = tmp_path / "blank.png"
    save_image(blank, np.full((200, 300), 255, np.uint8))
    assert main(["decode", str(blank)]) == EXIT_NO_CANDIDATES
    tight = tmp_path / "tight.png"
    save_image(tight, render_value(1234)[:, 85:-85])
    assert main(["decode", str(tight), "--dpi", "300"]) == EXIT_VALIDATION_FAILED
    assert main(["decode", str(tmp_path / "missing.png")]) == EXIT_INPUT
    assert main(["decode", str(blank), "--dpi", "-1"]) == EXIT_USAGE
    assert main(["decode", str(blank), "--min-bars", "9", "--max-bars", "4"]) == EXIT_USAGE
    capsys.readouterr()


def test_exit_code_for_partial_result() -> None:
    detection = DecodedPharmacode(BoundingBox(0, 0, 1, 1), 0.0, (), (), 3, 3, 1.0, ())
    error = DecodeError(ErrorCode.INCONSISTENT_GAPS, "x", None)
    result = DecodeResult(ImageInfo(None, 1, 1, None), (detection,), (error,))
    assert exit_code_for(result) == EXIT_PARTIAL


def test_benchmark_command_quick(tmp_path: Path, capsys) -> None:
    assert (
        main(["benchmark", "--seed", "1", "--output", str(tmp_path / "bench"), "--quick"])
        == EXIT_OK
    )
    assert (tmp_path / "bench" / "results.md").exists()
    assert "correct" in capsys.readouterr().out
