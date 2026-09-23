"""``pharmacode batch``: decode many images, one JSON Lines record and CSV row each."""

from __future__ import annotations

import csv
import glob
import json
import multiprocessing
import sys
from collections.abc import Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from pharmacode import __version__
from pharmacode.cli import EXIT_INPUT, EXIT_OK, dpi_note, exit_code_for, result_payload
from pharmacode.debug import DebugRecorder
from pharmacode.io import InputError, save_image
from pharmacode.models import DecoderConfig, ErrorCode
from pharmacode.pipeline import load_and_decode
from pharmacode.visualization import annotate

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff")
CSV_COLUMNS = (
    "path",
    "exit_code",
    "dpi",
    "dpi_source",
    "detections",
    "values",
    "mirror_values",
    "confidences",
    "errors",
    "expected_matched",
)


@dataclass(frozen=True)
class BatchOptions:
    config: DecoderConfig
    auto_dpi: bool = False
    include_geometry: bool = False
    expect: int | None = None
    annotated_dir: str | None = None
    debug_dir: str | None = None


@dataclass(frozen=True)
class BatchSummary:
    total: int
    ok: int


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def collect_inputs(inputs: Sequence[str], recursive: bool = False) -> list[Path]:
    """Expand files, directories and glob patterns into an ordered list without duplicates.

    A directory contributes its PNG, JPEG and TIFF files (``recursive`` also
    searches its subdirectories), sorted by path. A pattern (``*``, ``?`` or
    ``[``, for shells that do not expand them, such as ``cmd.exe``) contributes
    the image files it matches. Any other argument is kept as given, even when
    it does not exist, so that it is reported as unreadable instead of skipped.
    """
    found: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            walk = path.rglob("*") if recursive else path.glob("*")
            found.extend(sorted(p for p in walk if _is_image(p)))
        elif not path.exists() and any(char in item for char in "*?["):
            found.extend(
                sorted(Path(p) for p in glob.glob(item, recursive=True) if _is_image(Path(p)))
            )
        else:
            found.append(path)
    unique: dict[Path, None] = dict.fromkeys(found)
    return list(unique)


def _output_name(index: int, path: Path) -> str:
    """``0007-name``: unique even when two inputs in different directories share a name."""
    return f"{index:04d}-{path.stem}"


def _unreadable(path: Path, message: str, expect: int | None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "version": __version__,
        "image": {
            "path": str(path),
            "width": None,
            "height": None,
            "dpi": None,
            "dpi_source": None,
        },
        "detections": [],
        "errors": [{"code": ErrorCode.INPUT_UNREADABLE.value, "message": message, "bbox": None}],
    }
    if expect is not None:
        record["expected"] = {"value": expect, "matched": False, "matches": []}
    record["exit_code"] = EXIT_INPUT
    return record


def decode_one(task: tuple[int, Path, BatchOptions]) -> tuple[dict[str, Any], list[str]]:
    """Decode one file: its JSON Lines record (with ``exit_code``) and notes for stderr.

    Runs in a worker process when ``--jobs`` is above 1, so it takes and
    returns only picklable values and writes the per-image files itself.
    """
    index, path, options = task
    notes: list[str] = []
    debug = DebugRecorder() if options.debug_dir else None
    try:
        result, image, resolution = load_and_decode(path, options.config, options.auto_dpi, debug)
    except InputError as exc:
        return _unreadable(path, str(exc), options.expect), [f"{path}: {exc}"]
    note = dpi_note(resolution)
    if note is not None:
        notes.append(f"{path}: {note}")
    record = result_payload(result, options.include_geometry, options.expect)
    exit_code = exit_code_for(result, options.expect)
    name = _output_name(index, path)
    if options.annotated_dir is not None:
        target = Path(options.annotated_dir) / f"{name}.png"
        try:
            save_image(target, annotate(image, result))
            record["annotated"] = str(target)
        except InputError as exc:
            notes.append(f"{path}: {exc}")
            exit_code = EXIT_INPUT
    if debug is not None and options.debug_dir is not None:
        target = Path(options.debug_dir) / name
        try:
            debug.save(target)
            record["debug"] = str(target)
        except (InputError, OSError) as exc:
            notes.append(f"{path}: could not write debug output: {exc}")
            exit_code = EXIT_INPUT
    record["exit_code"] = exit_code
    return record, notes


def iter_batch(
    paths: Sequence[Path], options: BatchOptions, jobs: int = 1
) -> Iterator[tuple[dict[str, Any], list[str]]]:
    """:func:`decode_one` for every path, in input order, on ``jobs`` processes."""
    tasks = [(index, path, options) for index, path in enumerate(paths)]
    if jobs == 1 or len(tasks) == 1:
        yield from map(decode_one, tasks)
        return
    # spawn, as on Windows and macOS: forking a process that already runs OpenCV's worker
    # threads can deadlock the child
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=min(jobs, len(tasks)), mp_context=context) as pool:
        yield from pool.map(decode_one, tasks)


def csv_row(record: dict[str, Any]) -> dict[str, Any]:
    """One CSV summary row of a JSON Lines record; lists are joined with ``;``."""
    detections = record["detections"]
    expected = record.get("expected")
    return {
        "path": record["image"]["path"],
        "exit_code": record["exit_code"],
        "dpi": "" if record["image"]["dpi"] is None else record["image"]["dpi"],
        "dpi_source": record["image"]["dpi_source"] or "",
        "detections": len(detections),
        "values": ";".join(str(d["value"]) for d in detections),
        "mirror_values": ";".join(str(d["mirror_value"]) for d in detections),
        "confidences": ";".join(str(d["confidence"]) for d in detections),
        "errors": ";".join(e["code"] for e in record["errors"]),
        "expected_matched": "" if expected is None else str(expected["matched"]).lower(),
    }


def run_batch(
    paths: Sequence[Path],
    options: BatchOptions,
    jobs: int = 1,
    jsonl_path: str | None = None,
    csv_path: str | None = None,
) -> BatchSummary:
    """Decode ``paths`` and stream the records to ``jsonl_path`` (stdout when ``None``)
    and, optionally, the summary rows to ``csv_path``. Raises ``OSError`` when an output
    file cannot be opened or written."""
    total = ok = 0
    with ExitStack() as stack:
        jsonl: IO[str] = sys.stdout
        if jsonl_path is not None:
            jsonl = stack.enter_context(open(jsonl_path, "w", encoding="utf-8"))
        writer = None
        if csv_path is not None:
            table = stack.enter_context(open(csv_path, "w", encoding="utf-8", newline=""))
            writer = csv.DictWriter(table, fieldnames=CSV_COLUMNS)
            writer.writeheader()
        for record, notes in iter_batch(paths, options, jobs):
            for note in notes:
                print(f"note: {note}", file=sys.stderr)
            jsonl.write(json.dumps(record) + "\n")
            jsonl.flush()
            if writer is not None:
                writer.writerow(csv_row(record))
            total += 1
            ok += record["exit_code"] == EXIT_OK
    return BatchSummary(total, ok)
