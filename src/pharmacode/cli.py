"""Command line interface: ``pharmacode generate | decode | batch | benchmark``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pharmacode import __version__
from pharmacode.debug import DebugRecorder
from pharmacode.encoding import MAX_VALUE, MIN_VALUE, encode
from pharmacode.io import InputError, save_image
from pharmacode.metadata import Resolution
from pharmacode.models import POLARITIES, DecoderConfig, DecodeResult, ErrorCode
from pharmacode.pipeline import load_and_decode
from pharmacode.rendering import Distortion, RenderSpec, distort, render_bars
from pharmacode.visualization import annotate

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INPUT = 3
EXIT_NO_CANDIDATES = 4
EXIT_VALIDATION_FAILED = 5
EXIT_PARTIAL = 6
EXIT_BENCHMARK_FAILED = 7
EXIT_EXPECTATION_FAILED = 8
EXIT_BATCH_FAILURES = 9


def _fail(message: str, code: int) -> int:
    print(f"error: {message}", file=sys.stderr)
    return code


def _dpi_argument(text: str) -> float | str:
    """``--dpi`` of ``decode``: a number, or ``auto`` to read it from the file."""
    if text == "auto":
        return text
    try:
        return float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number or 'auto', got {text!r}") from None


def _add_decoder_options(command: argparse.ArgumentParser) -> None:
    """Options shared by ``decode`` and ``batch``; see :func:`decoder_setup`."""
    command.add_argument(
        "--dpi",
        type=_dpi_argument,
        default=None,
        help="resolution for physical checks, or 'auto' to read it from the file",
    )
    command.add_argument("--min-bars", type=int, default=2)
    command.add_argument("--max-bars", type=int, default=16)
    command.add_argument(
        "--allow-cropped-quiet-zone",
        action="store_true",
        help="treat a quiet zone cut by the image edge as a warning instead of "
        "QUIET_ZONE_VIOLATION",
    )
    command.add_argument(
        "--polarity",
        choices=POLARITIES,
        default="dark",
        help="dark bars on light (default), light bars on dark, or auto: try both",
    )
    command.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="reject detections below this confidence as LOW_CONFIDENCE errors (0.0..1.0)",
    )
    command.add_argument(
        "--expect",
        type=int,
        default=None,
        help="exit 0 only if a detection reads this value, in either direction; else exit 8",
    )
    command.add_argument(
        "--report-geometry",
        action="store_true",
        help="add measured bar, gap and quiet-zone sizes, with the Laetus tolerances, to the JSON",
    )


def decoder_setup(args: argparse.Namespace) -> DecoderConfig | str:
    """The decoder configuration the shared options ask for, or a usage error message."""
    auto_dpi = args.dpi == "auto"
    if not auto_dpi and args.dpi is not None and args.dpi <= 0:
        return "--dpi must be positive"
    if not 2 <= args.min_bars <= args.max_bars <= 16:
        return "--min-bars and --max-bars must satisfy 2 <= min <= max <= 16"
    if not 0.0 <= args.min_confidence <= 1.0:
        return "--min-confidence must be between 0.0 and 1.0"
    if args.expect is not None and not MIN_VALUE <= args.expect <= MAX_VALUE:
        return f"--expect must be between {MIN_VALUE} and {MAX_VALUE}"
    return DecoderConfig(
        dpi=None if auto_dpi else args.dpi,
        min_bars=args.min_bars,
        max_bars=args.max_bars,
        allow_truncated_quiet_zone=args.allow_cropped_quiet_zone,
        min_confidence=args.min_confidence,
        polarity=args.polarity,
    )


def dpi_note(resolution: Resolution | None) -> str | None:
    """What ``--dpi auto`` has to say when it found no usable DPI in the file."""
    if resolution is None or resolution.dpi is not None:
        return None
    reason = resolution.note or "the file stores no resolution"
    return f"--dpi auto: {reason}; decoding without DPI"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pharmacode",
        description="Generate, detect and decode one-track Pharmacode barcodes in images.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="render a synthetic Pharmacode image")
    generate.add_argument("--value", type=int, required=True, help="integer 3..131070")
    generate.add_argument("--output", required=True, help="PNG, JPEG or TIFF path")
    generate.add_argument("--dpi", type=float, default=300.0)
    generate.add_argument("--miniature", action="store_true", help="Laetus miniature dimensions")
    generate.add_argument("--rotation", type=float, default=0.0, help="degrees counter-clockwise")
    generate.add_argument("--scale-x", type=float, default=1.0)
    generate.add_argument("--scale-y", type=float, default=1.0)
    generate.add_argument("--perspective", type=float, default=0.0, help="tilt in degrees")
    generate.add_argument("--blur", type=float, default=0.0, help="Gaussian sigma in pixels")
    generate.add_argument("--noise", type=float, default=0.0, help="Gaussian noise sigma")
    generate.add_argument("--contrast", type=float, default=1.0, help="1.0 = full contrast")
    generate.add_argument("--illumination", type=float, default=0.0, help="0..1 brightness loss")
    generate.add_argument("--jpeg", type=int, default=None, help="JPEG quality round trip")
    generate.add_argument("--seed", type=int, default=0)
    generate.set_defaults(handler=run_generate)

    decode = commands.add_parser("decode", help="find and decode Pharmacode in an image")
    decode.add_argument("input", help="PNG, JPEG or TIFF file")
    decode.add_argument("--json", default=None, help="write the result here instead of stdout")
    decode.add_argument("--annotated", default=None, help="write an annotated image here")
    decode.add_argument(
        "--debug-dir", default=None, help="write intermediate images and measurements here"
    )
    _add_decoder_options(decode)
    decode.set_defaults(handler=run_decode)

    batch = commands.add_parser("batch", help="decode many images into JSON Lines and CSV")
    batch.add_argument(
        "inputs", nargs="+", help="image files, directories, or glob patterns such as 'scans/*.png'"
    )
    batch.add_argument(
        "--recursive", action="store_true", help="also search subdirectories of directories"
    )
    batch.add_argument("--jsonl", default=None, help="write one JSON result per line here")
    batch.add_argument("--csv", default=None, help="also write a one-row-per-image summary here")
    batch.add_argument("--annotated-dir", default=None, help="write annotated images here")
    batch.add_argument(
        "--debug-dir", default=None, help="write each image's intermediate images here"
    )
    batch.add_argument("--jobs", type=int, default=1, help="decode this many images in parallel")
    _add_decoder_options(batch)
    batch.set_defaults(handler=run_batch_command)

    benchmark = commands.add_parser("benchmark", help="run the synthetic benchmark matrix")
    benchmark.add_argument("--seed", type=int, default=20260919)
    benchmark.add_argument("--output", default="benchmark-output")
    benchmark.add_argument("--quick", action="store_true", help="small subset for CI")
    benchmark.add_argument(
        "--min-correct",
        type=float,
        default=1.0,
        help="fail unless every condition reaches this correct rate",
    )
    benchmark.add_argument("--max-false-positives", type=int, default=0)
    benchmark.set_defaults(handler=run_benchmark_command)
    return parser


def run_generate(args: argparse.Namespace) -> int:
    try:
        bars = encode(args.value)
    except (TypeError, ValueError) as exc:
        return _fail(str(exc), EXIT_USAGE)
    if args.dpi <= 0:
        return _fail("--dpi must be positive", EXIT_USAGE)
    spec = RenderSpec.miniature(dpi=args.dpi) if args.miniature else RenderSpec(dpi=args.dpi)
    image = render_bars(bars, spec)
    try:
        distortion = Distortion(
            rotation_deg=args.rotation,
            scale_x=args.scale_x,
            scale_y=args.scale_y,
            perspective_deg=args.perspective,
            blur_sigma=args.blur,
            noise_sigma=args.noise,
            contrast=args.contrast,
            illumination_gradient=args.illumination,
            jpeg_quality=args.jpeg,
        )
    except ValueError as exc:
        return _fail(str(exc), EXIT_USAGE)
    if distortion != Distortion():
        image = distort(image, distortion, np.random.default_rng(args.seed))
    try:
        save_image(args.output, image, dpi=(args.dpi * args.scale_x, args.dpi * args.scale_y))
    except InputError as exc:
        return _fail(str(exc), EXIT_INPUT)
    print(
        json.dumps(
            {
                "value": args.value,
                "bars": [bar.value for bar in bars],
                "output": str(args.output),
                "width": int(image.shape[1]),
                "height": int(image.shape[0]),
                "dpi": args.dpi,
            }
        )
    )
    return EXIT_OK


def exit_code_for(result: DecodeResult, expect: int | None = None) -> int:
    """Map a result to the documented exit codes.

    With ``expect``, the answer is only whether a detection reads that value:
    0 if one does, :data:`EXIT_EXPECTATION_FAILED` otherwise.
    """
    if expect is not None:
        return EXIT_OK if result.matches(expect) else EXIT_EXPECTATION_FAILED
    if result.detections and not result.errors:
        return EXIT_OK
    if not result.detections:
        if any(error.code is ErrorCode.NO_CANDIDATES for error in result.errors):
            return EXIT_NO_CANDIDATES
        return EXIT_VALIDATION_FAILED
    return EXIT_PARTIAL


def run_decode(args: argparse.Namespace) -> int:
    config = decoder_setup(args)
    if isinstance(config, str):
        return _fail(config, EXIT_USAGE)
    debug = DebugRecorder() if args.debug_dir else None
    try:
        result, image, resolution = load_and_decode(args.input, config, args.dpi == "auto", debug)
    except InputError as exc:
        return _fail(str(exc), EXIT_INPUT)
    note = dpi_note(resolution)
    if note is not None:
        print(f"note: {note}", file=sys.stderr)
    payload = json.dumps(result_payload(result, args.report_geometry, args.expect), indent=2)
    if args.json:
        try:
            Path(args.json).write_text(payload + "\n", encoding="utf-8")
        except OSError as exc:
            return _fail(f"could not write JSON to {args.json}: {exc}", EXIT_INPUT)
    else:
        print(payload)
    if args.annotated:
        try:
            save_image(args.annotated, annotate(image, result))
        except InputError as exc:
            return _fail(str(exc), EXIT_INPUT)
    if debug is not None:
        try:
            debug.save(args.debug_dir)
        except (InputError, OSError) as exc:
            return _fail(f"could not write debug output to {args.debug_dir}: {exc}", EXIT_INPUT)
    return exit_code_for(result, args.expect)


def run_batch_command(args: argparse.Namespace) -> int:
    from pharmacode.batch import BatchOptions, collect_inputs, run_batch

    config = decoder_setup(args)
    if isinstance(config, str):
        return _fail(config, EXIT_USAGE)
    if args.jobs < 1:
        return _fail("--jobs must be >= 1", EXIT_USAGE)
    paths = collect_inputs(args.inputs, args.recursive)
    if not paths:
        return _fail("no input images found", EXIT_INPUT)
    for directory in (args.annotated_dir, args.debug_dir):
        if directory is not None:
            try:
                Path(directory).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return _fail(f"could not create {directory}: {exc}", EXIT_INPUT)
    options = BatchOptions(
        config=config,
        auto_dpi=args.dpi == "auto",
        include_geometry=args.report_geometry,
        expect=args.expect,
        annotated_dir=args.annotated_dir,
        debug_dir=args.debug_dir,
    )
    try:
        summary = run_batch(paths, options, args.jobs, args.jsonl, args.csv)
    except OSError as exc:
        return _fail(f"could not write batch output: {exc}", EXIT_INPUT)
    print(
        f"batch: {summary.total} images, {summary.ok} decoded cleanly, "
        f"{summary.total - summary.ok} not",
        file=sys.stderr,
    )
    return EXIT_OK if summary.ok == summary.total else EXIT_BATCH_FAILURES


def result_payload(
    result: DecodeResult, include_geometry: bool = False, expect: int | None = None
) -> dict[str, Any]:
    """The JSON result, with ``geometry`` and an ``expected`` block when asked for."""
    payload = result.to_dict(include_geometry)
    if expect is not None:
        matches = result.matches(expect)
        payload["expected"] = {
            "value": expect,
            "matched": bool(matches),
            "matches": [{"detection": index, "reading": reading} for index, reading in matches],
        }
    return payload


def run_benchmark_command(args: argparse.Namespace) -> int:
    from pharmacode.benchmark import gate, render_markdown, run_benchmark

    if not 0.0 <= args.min_correct <= 1.0:
        return _fail("--min-correct must be between 0.0 and 1.0", EXIT_USAGE)
    if args.max_false_positives < 0:
        return _fail("--max-false-positives must be >= 0", EXIT_USAGE)
    report = run_benchmark(seed=args.seed, output_dir=args.output, quick=args.quick)
    print(render_markdown(report))
    violations = gate(report, args.min_correct, args.max_false_positives)
    if violations:
        for violation in violations:
            print(f"gate: {violation}", file=sys.stderr)
        return EXIT_BENCHMARK_FAILED
    print(
        f"gate: passed (min correct {args.min_correct:.0%}, "
        f"max false positives {args.max_false_positives})"
    )
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
