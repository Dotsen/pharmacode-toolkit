"""Command line interface: ``pharmacode generate | decode | benchmark``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

import numpy as np

from pharmacode import __version__
from pharmacode.encoding import encode
from pharmacode.io import InputError, save_image
from pharmacode.rendering import Distortion, RenderSpec, distort, render_bars

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INPUT = 3
EXIT_NO_CANDIDATES = 4
EXIT_VALIDATION_FAILED = 5
EXIT_PARTIAL = 6


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
