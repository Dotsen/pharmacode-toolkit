from __future__ import annotations

import json
from pathlib import Path

from pharmacode.benchmark import build_conditions, build_values, render_markdown, run_benchmark


def test_conditions_cover_every_group() -> None:
    groups = {c.group for c in build_conditions(quick=False)}
    assert groups == {
        "clean",
        "rotation",
        "dpi",
        "blur",
        "noise",
        "jpeg",
        "contrast",
        "illumination",
        "perspective",
        "scale",
        "edge",
        "multi",
        "tolerance",
    }
    assert len(build_conditions(quick=True)) < len(build_conditions(quick=False))


def test_values_are_deterministic() -> None:
    assert build_values(20260919, quick=True) == build_values(20260919, quick=True)
    assert 3 in build_values(20260919, quick=False) and 131070 in build_values(
        20260919, quick=False
    )


def test_quick_benchmark_writes_reports(tmp_path: Path) -> None:
    report = run_benchmark(seed=20260919, output_dir=tmp_path, quick=True)
    assert (tmp_path / "results.json").exists() and (tmp_path / "results.md").exists()
    saved = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert saved["seed"] == 20260919 and saved["environment"]["opencv"]
    assert saved["conditions"]["clean-300"]["correct_rate"] == 1.0
    assert 0.0 <= saved["negatives"]["false_positive_rate"] <= 1.0
    assert "| condition |" in render_markdown(report)
