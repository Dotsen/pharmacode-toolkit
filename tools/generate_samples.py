"""Regenerate the images in examples/generated from fixed parameters."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from pharmacode.io import load_image, save_image
from pharmacode.models import DecoderConfig
from pharmacode.pipeline import decode_image
from pharmacode.rendering import Distortion, RenderSpec, compose_scene, distort, render_value
from pharmacode.visualization import annotate

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
ROOT = EXAMPLES / "generated"
EXPECTED = EXAMPLES / "expected"
ANNOTATED = EXAMPLES / "annotated"
SEED = 20260919


def _write_expected_and_annotated(path: Path) -> None:
    image = load_image(path)
    result = decode_image(image, DecoderConfig(dpi=150.0), path=path.name)
    payload = json.dumps(result.to_dict(), indent=2) + "\n"
    (EXPECTED / f"{path.stem}.json").write_text(payload, encoding="utf-8")
    ok, buffer = cv2.imencode(".jpg", annotate(image, result), [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    buffer.tofile(str(ANNOTATED / f"{path.stem}.jpg"))


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    EXPECTED.mkdir(parents=True, exist_ok=True)
    ANNOTATED.mkdir(parents=True, exist_ok=True)
    spec = RenderSpec(dpi=150.0)
    save_image(ROOT / "value_1234.png", render_value(1234, spec))
    rotated = distort(render_value(12345, spec), Distortion(rotation_deg=90))
    save_image(ROOT / "value_12345_rotated_90.png", rotated)
    rng = np.random.default_rng(SEED)
    scene = compose_scene(
        (520, 900),
        [
            (render_value(91, spec), 40, 40),
            (distort(render_value(25, spec), Distortion(rotation_deg=90)), 640, 60),
            (render_value(131070, spec), 60, 300),
        ],
    )
    scene = distort(scene, Distortion(blur_sigma=0.8, noise_sigma=6.0, jpeg_quality=80), rng)
    save_image(ROOT / "three_codes_scanned.png", scene)
    for path in sorted(ROOT.glob("*.png")):
        _write_expected_and_annotated(path)
    print(f"wrote samples to {ROOT}")


if __name__ == "__main__":
    main()
