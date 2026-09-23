"""Synthetic benchmark: a matrix of conditions, never a single headline number."""

from __future__ import annotations

import json
import platform
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from pharmacode import __version__
from pharmacode.encoding import MAX_VALUE, MIN_VALUE
from pharmacode.io import save_image
from pharmacode.models import DecoderConfig
from pharmacode.pipeline import decode_image
from pharmacode.rendering import (
    NEGATIVE_KINDS,
    Distortion,
    RenderSpec,
    compose_scene,
    distort,
    render_negative,
    render_value,
)
from pharmacode.visualization import annotate

BOUNDARY_VALUES = [3, 4, 5, 6, 7, 8, 13, 25, 91, 100, 1234, 12345, 65535, 123456, 131070]


@dataclass(frozen=True)
class Condition:
    name: str
    group: str
    dpi: float
    distortion: Distortion = Distortion()
    spec: RenderSpec | None = None
    multi: bool = False
    edge: bool = False
    use_dpi: bool = True
    # "knockout": dark bars on a white patch inside a black page; "inverted": light bars on
    # a black patch inside a white page. Either way the patch leaves only the nominal 6 mm
    # quiet zone, so its edge lies inside the candidate window.
    patch: str | None = None
    polarity: str = "dark"

    def render_spec(self) -> RenderSpec:
        return self.spec if self.spec is not None else RenderSpec(dpi=self.dpi)


def build_conditions(quick: bool) -> list[Condition]:
    conditions = [
        Condition("clean-300", "clean", 300.0),
        Condition("rotation-90", "rotation", 300.0, Distortion(rotation_deg=90)),
        Condition("rotation-180", "rotation", 300.0, Distortion(rotation_deg=180)),
        Condition("rotation-270", "rotation", 300.0, Distortion(rotation_deg=270)),
        Condition("tilt-plus-3", "rotation", 300.0, Distortion(rotation_deg=3)),
        Condition("tilt-minus-3", "rotation", 300.0, Distortion(rotation_deg=-3)),
        Condition("dpi-150", "dpi", 150.0),
        Condition("dpi-600", "dpi", 600.0),
        Condition("blur-1", "blur", 300.0, Distortion(blur_sigma=1.0)),
        Condition("blur-2", "blur", 300.0, Distortion(blur_sigma=2.0)),
        Condition("noise-10", "noise", 300.0, Distortion(noise_sigma=10.0)),
        Condition("noise-25", "noise", 300.0, Distortion(noise_sigma=25.0)),
        Condition("jpeg-50", "jpeg", 300.0, Distortion(jpeg_quality=50)),
        Condition("jpeg-30", "jpeg", 300.0, Distortion(jpeg_quality=30)),
        Condition("contrast-0.4", "contrast", 300.0, Distortion(contrast=0.4)),
        Condition("illumination-0.5", "illumination", 300.0, Distortion(illumination_gradient=0.5)),
        Condition("perspective-3", "perspective", 300.0, Distortion(perspective_deg=3.0)),
        Condition(
            "scale-0.7x1.3", "scale", 300.0, Distortion(scale_x=0.7, scale_y=1.3), use_dpi=False
        ),
        Condition("edge-corner", "edge", 300.0, edge=True),
        Condition("multi-3", "multi", 300.0, multi=True),
        Condition("miniature-600", "tolerance", 600.0, spec=RenderSpec.miniature(dpi=600.0)),
        Condition(
            "tolerance-max-gap",
            "tolerance",
            300.0,
            spec=RenderSpec(narrow_mm=0.7, wide_mm=2.5, gap_mm=2.5),
        ),
        Condition("dpi-150-blur-1", "blur", 150.0, Distortion(blur_sigma=1.0)),
        Condition("inverted-auto", "patch", 300.0, patch="inverted", polarity="auto"),
        Condition("knockout-dark", "patch", 300.0, patch="knockout"),
    ]
    if quick:
        # One condition per group (the first that appears), so a slice can't silently drop
        # a whole group from CI coverage; rotation-180 is added on top for a second angle.
        keep = {"clean", "rotation", "blur", "noise", "multi", "scale", "tolerance", "patch"}
        selected: list[Condition] = []
        seen: set[str] = set()
        for c in conditions:
            if c.group in keep and c.group not in seen:
                selected.append(c)
                seen.add(c.group)
            if c.group == "rotation" and c.name == "rotation-180":
                selected.append(c)
        conditions = selected
    return conditions


def build_values(seed: int, quick: bool) -> list[int]:
    rng = np.random.default_rng(seed)
    count = 8 if quick else 40
    random_values = sorted(int(v) for v in rng.integers(MIN_VALUE, MAX_VALUE + 1, count))
    return (BOUNDARY_VALUES[:6] if quick else BOUNDARY_VALUES) + random_values


def _make_image(condition: Condition, value: int, rng: np.random.Generator) -> np.ndarray:
    spec = condition.render_spec()
    code = render_value(value, spec)
    if condition.multi:
        others = [render_value(int(v), spec) for v in rng.integers(MIN_VALUE, MAX_VALUE + 1, 2)]
        turned = distort(others[0], Distortion(rotation_deg=90))
        canvas = (
            code.shape[0] * 2 + turned.shape[0] + 200,
            code.shape[1] + turned.shape[1] + others[1].shape[1] + 300,
        )
        code = compose_scene(
            canvas,
            [
                (code, 50, 50),
                (turned, code.shape[1] + 150, 60),
                (others[1], 80, code.shape[0] + turned.shape[0] + 120),
            ],
        )
    if condition.edge:
        code = compose_scene((code.shape[0] + 150, code.shape[1] + 150), [(code, 0, 0)])
    if condition.patch is not None:
        code = render_value(value, spec.with_updates(margin_mm=0.0))
        page = np.zeros((code.shape[0] + 150, code.shape[1] + 150), dtype=np.uint8)
        page[75 : 75 + code.shape[0], 75 : 75 + code.shape[1]] = code
        code = 255 - page if condition.patch == "inverted" else page
    return (
        distort(code, condition.distortion, rng) if condition.distortion != Distortion() else code
    )


def _environment() -> dict[str, str]:
    return {
        "toolkit": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "opencv": cv2.__version__,
    }


def run_benchmark(seed: int, output_dir: str | Path, quick: bool = False) -> dict[str, Any]:
    """Render, decode and score every condition; write reports and failure images."""
    output = Path(output_dir)
    failures = output / "failures"
    failures.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    values = build_values(seed, quick)
    report: dict[str, Any] = {
        "seed": seed,
        "quick": quick,
        "environment": _environment(),
        "config": asdict(DecoderConfig()),
        "values": values,
        "conditions": {},
        "negatives": {},
    }
    for condition in build_conditions(quick):
        detected = correct = 0
        elapsed: list[float] = []
        failed: list[dict[str, Any]] = []
        config = DecoderConfig(
            dpi=condition.dpi if condition.use_dpi else None, polarity=condition.polarity
        )
        for value in values:
            image = _make_image(condition, value, rng)
            start = time.perf_counter()
            result = decode_image(image, config)
            elapsed.append((time.perf_counter() - start) * 1000.0)
            found = bool(result.detections)
            hit = any(value in (d.value, d.mirror_value) for d in result.detections)
            detected += found
            correct += hit
            if not hit:
                target = failures / condition.name
                target.mkdir(parents=True, exist_ok=True)
                save_image(target / f"{value}.png", annotate(image, result))
                failed.append({"value": value, "errors": [e.to_dict() for e in result.errors]})
        report["conditions"][condition.name] = {
            "group": condition.group,
            "images": len(values),
            "detected": detected,
            "detected_rate": detected / len(values),
            "correct": correct,
            "correct_rate": correct / len(values),
            "mean_ms": float(np.mean(elapsed)),
            "failures": failed,
        }
    negative_count = 40 if quick else 200
    false_positives: list[dict[str, Any]] = []
    # every negative is decoded as rendered and inverted, both with polarity "auto", which
    # runs the light pass whenever the dark pass finds nothing: that covers the dark and
    # the light pass on both the rendered clutter and its inverse
    negative_config = DecoderConfig(polarity="auto")
    for index in range(negative_count):
        kind = NEGATIVE_KINDS[index % len(NEGATIVE_KINDS)]
        rendered = render_negative(kind, rng)
        for inverted, image in ((False, rendered), (True, 255 - rendered)):
            result = decode_image(image, negative_config)
            if result.detections:
                name = f"{kind}-{index}{'-inverted' if inverted else ''}"
                target = failures / "negatives"
                target.mkdir(parents=True, exist_ok=True)
                save_image(target / f"{name}.png", annotate(image, result))
                false_positives.append(
                    {
                        "kind": kind,
                        "index": index,
                        "inverted": inverted,
                        "values": [d.value for d in result.detections],
                    }
                )
    report["negatives"] = {
        "images": 2 * negative_count,
        "false_positives": len(false_positives),
        "false_positive_rate": len(false_positives) / negative_count,
        "cases": false_positives,
    }
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "results.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def gate(report: dict[str, Any], min_correct: float, max_false_positives: int) -> list[str]:
    """Return one message per violated threshold; empty means the benchmark passed."""
    violations: list[str] = []
    for name, row in report["conditions"].items():
        if row["correct_rate"] < min_correct:
            violations.append(
                f"{name}: correct rate {row['correct_rate']:.1%} below {min_correct:.1%}"
            )
    false_positives = report["negatives"]["false_positives"]
    if false_positives > max_false_positives:
        violations.append(
            f"negatives: {false_positives} false positives, maximum {max_false_positives}"
        )
    return violations


def render_markdown(report: dict[str, Any]) -> str:
    env = report["environment"]
    lines = [
        f"# Benchmark (seed {report['seed']}, {'quick' if report['quick'] else 'full'})",
        "",
        f"Python {env['python']}, numpy {env['numpy']}, OpenCV {env['opencv']}, {env['platform']}",
        "",
        "| condition | group | images | detected | correct | mean ms |",
        "|---|---|---|---|---|---|",
    ]
    for name, row in report["conditions"].items():
        lines.append(
            f"| {name} | {row['group']} | {row['images']} | {row['detected_rate']:.1%} | "
            f"{row['correct_rate']:.1%} | {row['mean_ms']:.1f} |"
        )
    negatives = report["negatives"]
    lines += [
        "",
        f"Negatives: {negatives['images']} images (each rendered negative also inverted, "
        f"polarity auto), {negatives['false_positives']} false positives "
        f"({negatives['false_positive_rate']:.1%}).",
        "",
    ]
    return "\n".join(lines)
