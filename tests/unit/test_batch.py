from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from pharmacode import batch
from pharmacode.batch import BatchOptions, collect_inputs, iter_batch
from pharmacode.cli import (
    EXIT_BATCH_FAILURES,
    EXIT_INPUT,
    EXIT_NO_CANDIDATES,
    EXIT_OK,
    EXIT_USAGE,
    main,
)
from pharmacode.io import save_image
from pharmacode.models import DecoderConfig
from pharmacode.rendering import render_value


def _images(root: Path) -> dict[str, Path]:
    (root / "sub").mkdir(parents=True)
    files = {
        "a": root / "a.png",
        "b": root / "b.jpg",
        "nested": root / "sub" / "c.tif",
        "blank": root / "blank.png",
    }
    save_image(files["a"], render_value(1234), 300.0)
    save_image(files["b"], render_value(91), 300.0)
    save_image(files["nested"], render_value(12345), 300.0)
    save_image(files["blank"], np.full((200, 300), 255, dtype=np.uint8))
    (root / "notes.txt").write_text("not an image", encoding="utf-8")
    return files


def _records(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_collect_inputs_expands_directories_and_patterns(tmp_path: Path) -> None:
    files = _images(tmp_path)
    flat = collect_inputs([str(tmp_path)])
    assert flat == sorted([files["a"], files["b"], files["blank"]])
    assert files["nested"] in collect_inputs([str(tmp_path)], recursive=True)
    assert collect_inputs([str(tmp_path / "*.png")]) == sorted([files["a"], files["blank"]])


def test_collect_inputs_keeps_missing_files_and_drops_duplicates(tmp_path: Path) -> None:
    files = _images(tmp_path)
    missing = tmp_path / "missing.png"
    found = collect_inputs([str(files["a"]), str(missing), str(files["a"])])
    assert found == [files["a"], missing]


def test_batch_writes_jsonl_and_csv(tmp_path: Path, capsys) -> None:
    files = _images(tmp_path / "in")
    jsonl, table = tmp_path / "out.jsonl", tmp_path / "out.csv"
    args = [str(tmp_path / "in"), "--recursive", "--dpi", "auto"]
    assert main(["batch", *args, "--jsonl", str(jsonl), "--csv", str(table)]) == (
        EXIT_BATCH_FAILURES
    )
    assert "4 images, 3 decoded cleanly" in capsys.readouterr().err
    records = {Path(r["image"]["path"]): r for r in _records(jsonl.read_text(encoding="utf-8"))}
    assert records[files["a"]]["detections"][0]["value"] == 1234
    assert records[files["a"]]["image"]["dpi_source"] == "png-phys"
    assert records[files["nested"]]["exit_code"] == EXIT_OK
    assert records[files["blank"]]["exit_code"] == EXIT_NO_CANDIDATES
    with table.open(encoding="utf-8", newline="") as handle:
        rows = {Path(row["path"]): row for row in csv.DictReader(handle)}
    assert rows[files["a"]]["values"] == "1234" and rows[files["a"]]["mirror_values"] == "1835"
    assert rows[files["blank"]]["errors"] == "NO_CANDIDATES"


def test_batch_prints_jsonl_to_stdout_and_exits_0_when_all_decode(tmp_path: Path, capsys) -> None:
    files = _images(tmp_path)
    assert main(["batch", str(files["a"]), str(files["b"]), "--dpi", "300"]) == EXIT_OK
    records = _records(capsys.readouterr().out)
    assert [r["detections"][0]["value"] for r in records] == [1234, 91]


def test_batch_reports_unreadable_files_and_keeps_going(tmp_path: Path, capsys) -> None:
    files = _images(tmp_path)
    missing = tmp_path / "missing.png"
    assert main(["batch", str(missing), str(files["a"])]) == EXIT_BATCH_FAILURES
    captured = capsys.readouterr()
    first, second = _records(captured.out)
    assert first["exit_code"] == EXIT_INPUT
    assert first["errors"][0]["code"] == "INPUT_UNREADABLE"
    assert first["image"]["path"] == str(missing)
    assert second["exit_code"] == EXIT_OK
    assert "missing.png" in captured.err


def test_batch_expect_marks_each_file(tmp_path: Path, capsys) -> None:
    files = _images(tmp_path)
    assert main(["batch", str(files["a"]), str(files["b"]), "--expect", "1234"]) == (
        EXIT_BATCH_FAILURES
    )
    first, second = _records(capsys.readouterr().out)
    assert first["expected"]["matched"] is True and first["exit_code"] == EXIT_OK
    assert second["expected"]["matched"] is False and second["exit_code"] == 8


def test_batch_writes_annotated_and_debug_output(tmp_path: Path, capsys) -> None:
    files = _images(tmp_path / "in")
    annotated, debug = tmp_path / "annotated", tmp_path / "debug"
    args = ["batch", str(files["a"]), "--annotated-dir", str(annotated), "--debug-dir", str(debug)]
    assert main(args) == EXIT_OK
    record = _records(capsys.readouterr().out)[0]
    assert Path(record["annotated"]) == annotated / "0000-a.png"
    assert (annotated / "0000-a.png").is_file()
    assert Path(record["debug"]) == debug / "0000-a"
    assert (debug / "0000-a" / "debug.json").is_file()


def test_parallel_batch_matches_serial(tmp_path: Path) -> None:
    files = _images(tmp_path)
    options = BatchOptions(DecoderConfig(dpi=300.0), include_geometry=True)
    paths = [files["a"], files["b"], files["nested"], files["blank"]]
    serial = [record for record, _ in iter_batch(paths, options, jobs=1)]
    parallel = [record for record, _ in iter_batch(paths, options, jobs=2)]
    assert parallel == serial


@pytest.mark.parametrize(
    "extra", [["--jobs", "0"], ["--dpi", "-1"], ["--expect", "2"], ["--min-bars", "9"]]
)
def test_batch_usage_errors(tmp_path: Path, extra: list[str]) -> None:
    files = _images(tmp_path)
    assert main(["batch", str(files["a"]), *extra, "--max-bars", "8"]) == EXIT_USAGE


def test_batch_without_any_image_is_an_input_error(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    assert main(["batch", str(tmp_path / "empty")]) == EXIT_INPUT


def test_batch_unwritable_jsonl_is_an_input_error(tmp_path: Path) -> None:
    files = _images(tmp_path)
    target = tmp_path / "missing-dir" / "out.jsonl"
    assert main(["batch", str(files["a"]), "--jsonl", str(target)]) == EXIT_INPUT


def test_batch_records_an_unexpected_failure_and_goes_on(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _images(tmp_path)
    real = batch.load_and_decode

    def flaky(path, *args, **kwargs):
        if Path(path) == files["b"]:
            raise RuntimeError("boom")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(batch, "load_and_decode", flaky)
    paths = [str(files["a"]), str(files["b"]), str(files["nested"])]
    assert main(["batch", *paths]) == EXIT_BATCH_FAILURES
    first, second, third = _records(capsys.readouterr().out)
    assert second["exception"] == "RuntimeError: boom" and second["exit_code"] == 1
    assert second["errors"] == []
    assert first["exit_code"] == third["exit_code"] == EXIT_OK


def test_batch_annotated_write_failure_stays_with_its_image(tmp_path: Path, capsys) -> None:
    files = _images(tmp_path / "in")
    annotated = tmp_path / "annotated"
    (annotated / "0000-a.png").mkdir(parents=True)
    args = ["batch", str(files["a"]), str(files["b"]), "--annotated-dir", str(annotated)]
    assert main(args) == EXIT_BATCH_FAILURES
    first, second = _records(capsys.readouterr().out)
    assert first["exit_code"] == EXIT_INPUT and "annotated" not in first
    assert second["exit_code"] == EXIT_OK and Path(second["annotated"]).is_file()
