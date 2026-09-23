from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

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
from pharmacode.rendering import RenderSpec, render_value
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


def test_generate_rejects_non_positive_scale(tmp_path: Path, capsys) -> None:
    args = ["generate", "--value", "25", "--scale-x", "0", "--output", str(tmp_path / "g.png")]
    assert main(args) == EXIT_USAGE
    assert "error:" in capsys.readouterr().err


def test_generate_rejects_negative_noise(tmp_path: Path, capsys) -> None:
    args = ["generate", "--value", "25", "--noise", "-1", "--output", str(tmp_path / "g.png")]
    assert main(args) == EXIT_USAGE
    assert "error:" in capsys.readouterr().err


def test_generate_reports_unwritable_output(tmp_path: Path) -> None:
    target = tmp_path / "missing-dir" / "x.png"
    assert main(["generate", "--value", "5", "--output", str(target)]) == EXIT_INPUT


def test_generate_unknown_suffix_is_input_error(tmp_path: Path) -> None:
    target = tmp_path / "gen.txt"
    assert main(["generate", "--value", "25", "--output", str(target)]) == EXIT_INPUT


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


def test_decode_json_into_missing_directory_is_input_error(tmp_path: Path) -> None:
    source = tmp_path / "code.png"
    save_image(source, render_value(1234))
    json_out = tmp_path / "missing" / "r.json"
    assert main(["decode", str(source), "--json", str(json_out)]) == EXIT_INPUT


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
    assert main(["decode", str(blank), "--min-bars", "1"]) == EXIT_USAGE
    capsys.readouterr()


def test_decode_rejects_out_of_range_min_confidence(tmp_path: Path, capsys) -> None:
    source = tmp_path / "code.png"
    save_image(source, render_value(1234))
    assert main(["decode", str(source), "--min-confidence", "2"]) == EXIT_USAGE
    assert "error:" in capsys.readouterr().err


def test_decode_min_confidence_rejects_a_weak_trimmed_code(tmp_path: Path, capsys) -> None:
    spec = RenderSpec()
    border = spec.px(6.0) + spec.px(2.0)
    trimmed = render_value(1234, spec)[:, border - 50 : -(border - 50)]
    source = tmp_path / "trimmed.png"
    save_image(source, trimmed)

    code = main(["decode", str(source), "--dpi", "300", "--min-confidence", "0.9"])
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_VALIDATION_FAILED
    assert payload["detections"] == []
    assert [e["code"] for e in payload["errors"]] == ["LOW_CONFIDENCE"]


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
    out = capsys.readouterr().out
    assert "correct" in out
    assert "gate: passed" in out


def test_benchmark_rejects_bad_min_correct(tmp_path: Path) -> None:
    args = [
        "benchmark",
        "--seed",
        "1",
        "--output",
        str(tmp_path / "bench"),
        "--quick",
        "--min-correct",
        "1.5",
    ]
    assert main(args) == EXIT_USAGE


def test_benchmark_rejects_negative_max_false_positives(tmp_path: Path) -> None:
    args = [
        "benchmark",
        "--seed",
        "1",
        "--output",
        str(tmp_path / "bench"),
        "--quick",
        "--max-false-positives",
        "-1",
    ]
    assert main(args) == EXIT_USAGE


def test_decode_polarity_reads_an_inverted_code(tmp_path: Path, capsys) -> None:
    target = tmp_path / "inverted.png"
    save_image(target, 255 - render_value(1234))
    assert main(["decode", str(target), "--dpi", "300"]) == EXIT_NO_CANDIDATES
    capsys.readouterr()
    assert main(["decode", str(target), "--dpi", "300", "--polarity", "auto"]) == EXIT_OK
    detection = json.loads(capsys.readouterr().out)["detections"][0]
    assert (detection["value"], detection["polarity"]) == (1234, "light")


def test_decode_rejects_unknown_polarity(tmp_path: Path) -> None:
    target = tmp_path / "code.png"
    save_image(target, render_value(1234))
    with pytest.raises(SystemExit) as raised:
        main(["decode", str(target), "--polarity", "inverse"])
    assert raised.value.code == EXIT_USAGE


def test_generate_stores_dpi_that_decode_auto_reads(tmp_path: Path, capsys) -> None:
    target = tmp_path / "all-narrow.png"
    assert main(["generate", "--value", "65535", "--dpi", "300", "--output", str(target)]) == 0
    capsys.readouterr()
    assert main(["decode", str(target), "--dpi", "auto"]) == EXIT_OK
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["image"]["dpi"] == 300.0 and payload["image"]["dpi_source"] == "png-phys"
    detection = payload["detections"][0]
    assert detection["value"] == 65535
    assert "single_width_class_no_dpi" not in detection["warnings"]
    assert captured.err == ""


def test_decode_auto_dpi_without_metadata_notes_it_and_decodes(tmp_path: Path, capsys) -> None:
    target = tmp_path / "plain.png"
    save_image(target, render_value(1234))
    assert main(["decode", str(target), "--dpi", "auto"]) == EXIT_OK
    captured = capsys.readouterr()
    assert json.loads(captured.out)["image"]["dpi"] is None
    assert "note: --dpi auto" in captured.err


def test_decode_given_dpi_is_reported_as_given(tmp_path: Path, capsys) -> None:
    target = tmp_path / "code.png"
    save_image(target, render_value(1234), 600.0)
    assert main(["decode", str(target), "--dpi", "300"]) == EXIT_OK
    image = json.loads(capsys.readouterr().out)["image"]
    assert (image["dpi"], image["dpi_source"]) == (300.0, "given")


def test_decode_rejects_a_dpi_that_is_neither_a_number_nor_auto(tmp_path: Path) -> None:
    target = tmp_path / "code.png"
    save_image(target, render_value(1234))
    with pytest.raises(SystemExit) as raised:
        main(["decode", str(target), "--dpi", "high"])
    assert raised.value.code == EXIT_USAGE
