"""Regenerate the images in examples/generated from fixed parameters."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from pharmacode.io import save_image
from pharmacode.rendering import Distortion, RenderSpec, compose_scene, distort, render_value

ROOT = Path(__file__).resolve().parent.parent / "examples" / "generated"
SEED = 20260919


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
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
    print(f"wrote samples to {ROOT}")


if __name__ == "__main__":
    main()
