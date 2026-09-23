"""Reading and writing images with paths that may contain non-ASCII characters."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from pharmacode.metadata import with_resolution


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


def save_image(
    path: str | Path, image: np.ndarray, dpi: float | tuple[float, float] | None = None
) -> None:
    """Write an image; the format follows the file suffix (PNG when absent).

    ``dpi`` (one value, or horizontal and vertical) is stored in the file's
    metadata, where :func:`pharmacode.metadata.read_resolution` finds it: a
    PNG ``pHYs`` chunk, the JPEG JFIF density (whole DPI) or the TIFF
    resolution tags (whole DPI).
    """
    file = Path(path)
    suffix = file.suffix.lower() or ".png"
    if not file.parent.is_dir():
        raise InputError(f"output directory does not exist: {file.parent}")
    xy = None if dpi is None else (dpi, dpi) if isinstance(dpi, (int, float)) else dpi
    params: list[int] = []
    if xy is not None and suffix in (".tif", ".tiff"):
        params = [
            cv2.IMWRITE_TIFF_RESUNIT, 2,
            cv2.IMWRITE_TIFF_XDPI, round(xy[0]),
            cv2.IMWRITE_TIFF_YDPI, round(xy[1]),
        ]  # fmt: skip
    try:
        ok, buffer = cv2.imencode(suffix, image, params)
    except cv2.error as exc:
        raise InputError(
            f"unsupported image format {suffix!r}; use .png, .jpg/.jpeg or .tif/.tiff"
        ) from exc
    if not ok:
        raise InputError(f"unsupported image format {suffix!r}; use .png, .jpg/.jpeg or .tif/.tiff")
    data = buffer.tobytes()
    if xy is not None:
        data = with_resolution(data, suffix, xy)
    file.write_bytes(data)
