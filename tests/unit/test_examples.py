"""The committed example images must decode to the committed expected JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pharmacode.io import load_image
from pharmacode.models import DecoderConfig
from pharmacode.pipeline import decode_image

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
CASES = sorted(EXAMPLES.glob("generated/*.png"))


@pytest.mark.parametrize("image_path", CASES, ids=[p.stem for p in CASES])
def test_example_matches_expected(image_path: Path) -> None:
    expected = json.loads(
        (EXAMPLES / "expected" / f"{image_path.stem}.json").read_text(encoding="utf-8")
    )
    result = decode_image(load_image(image_path), DecoderConfig(dpi=150.0)).to_dict()
    for payload in (expected, result):
        payload.pop("version", None)
        payload["image"].pop("path", None)
    assert result == expected
