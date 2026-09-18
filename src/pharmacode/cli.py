"""Command line interface: ``pharmacode generate | decode | benchmark``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from pharmacode import __version__
from pharmacode.encoding import encode
from pharmacode.io import InputError, load_image, save_image
from pharmacode.models import DecoderConfig, DecodeResult, ErrorCode
from pharmacode.pipeline import decode_image
from pharmacode.rendering import Distortion, RenderSpec, distort, render_bars
from pharmacode.visualization import annotate

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INPUT = 3
EXIT_NO_CANDIDATES = 4
EXIT_VALIDATION_FAILED = 5
EXIT_PARTIAL = 6
EXIT_BENCHMARK_FAILED = 7


def _fail(message: str, code: int) -> int:
    print(f"error: {message}", file=sys.stderr)
    return code


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
    decode.add_argument("--dpi", type=float, default=None, help="resolution for physical checks")
    decode.add_argument("--json", default=None, help="write the result here instead of stdout")
    decode.add_argument("--annotated", default=None, help="write an annotated image here")
    decode.add_argument("--min-bars", type=int, default=2)
    decode.add_argument("--max-bars", type=int, default=16)
    decode.set_defaults(handler=run_decode)

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
        save_image(args.output, image)
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


def exit_code_for(result: DecodeResult) -> int:
    """Map a result to the documented exit codes."""
    if result.detections and not result.errors:
        return EXIT_OK
    if not result.detections:
        if any(error.code is ErrorCode.NO_CANDIDATES for error in result.errors):
            return EXIT_NO_CANDIDATES
        return EXIT_VALIDATION_FAILED
    return EXIT_PARTIAL


def run_decode(args: argparse.Namespace) -> int:
    if args.dpi is not None and args.dpi <= 0:
        return _fail("--dpi must be positive", EXIT_USAGE)
    if not 2 <= args.min_bars <= args.max_bars <= 16:
        return _fail("--min-bars and --max-bars must satisfy 2 <= min <= max <= 16", EXIT_USAGE)
    try:
        image = load_image(args.input)
    except InputError as exc:
        return _fail(str(exc), EXIT_INPUT)
    config = DecoderConfig(dpi=args.dpi, min_bars=args.min_bars, max_bars=args.max_bars)
    result = decode_image(image, config, path=str(args.input))
    payload = json.dumps(result.to_dict(), indent=2)
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
    return exit_code_for(result)


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
