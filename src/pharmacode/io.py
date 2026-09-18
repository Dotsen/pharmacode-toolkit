"""Reading and writing images with paths that may contain non-ASCII characters."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


class InputError(Exception):
    """The input file is missing, unreadable or not an image."""


def load_image(path: str | Path) -> np.ndarray:
    """Load PNG, JPEG or TIFF as an 8-bit grayscale array."""
    file = Path(path)
    if not file.is_file():
        raise InputError(f"input file not found: {file}")
    data = np.fromfile(str(file), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE) if data.size else None
    if image is None:
        raise InputError(f"could not decode image: {file}")
    return image


def save_image(path: str | Path, image: np.ndarray) -> None:
    """Write an image; the format follows the file suffix (PNG when absent)."""
    file = Path(path)
    suffix = file.suffix.lower() or ".png"
    if not file.parent.is_dir():
        raise InputError(f"output directory does not exist: {file.parent}")
    try:
        ok, buffer = cv2.imencode(suffix, image)
    except cv2.error as exc:
        raise InputError(f"could not encode image as {suffix}: {exc}") from exc
    if not ok:
        raise InputError(f"could not encode image as {suffix}")
    buffer.tofile(str(file))
