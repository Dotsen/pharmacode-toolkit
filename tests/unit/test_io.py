from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pharmacode.io import InputError, load_image, save_image
from pharmacode.rendering import render_value


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".tif"])
def test_save_and_load_round_trip(tmp_path: Path, suffix: str) -> None:
    image = render_value(1234)
    target = tmp_path / f"код{suffix}"  # non-ASCII path must work on Windows
    save_image(target, image)
    loaded = load_image(target)
    assert loaded.shape == image.shape and loaded.dtype == np.uint8
    if suffix != ".jpg":
        assert np.array_equal(loaded, image)


def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InputError):
        load_image(tmp_path / "missing.png")


def test_load_non_image(tmp_path: Path) -> None:
    junk = tmp_path / "junk.png"
    junk.write_bytes(b"not an image")
    with pytest.raises(InputError):
        load_image(junk)


def test_save_rejects_unknown_suffix(tmp_path: Path) -> None:
    with pytest.raises(InputError):
        save_image(tmp_path / "x.txt", render_value(3))
