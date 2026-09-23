from __future__ import annotations

import struct
from pathlib import Path

import cv2
import numpy as np
import pytest

from pharmacode.io import save_image
from pharmacode.metadata import (
    MIN_TRUSTED_DPI,
    Resolution,
    read_resolution,
    resolution_from_bytes,
    with_resolution,
)

BLANK = np.full((40, 60), 255, dtype=np.uint8)


def _tiff_block(
    x_dpi: float, y_dpi: float, unit: int | None = 2, camera: bool = False, order: str = "<"
) -> bytes:
    """A minimal TIFF structure (as found inside an EXIF block) with resolution tags.

    ``camera`` adds an Exif sub-IFD holding a FocalLength tag, as every camera writes.
    """
    header = (b"II" if order == "<" else b"MM") + struct.pack(order + "HI", 42, 8)
    entries: list[tuple[int, int, int, bytes]] = [
        (0x011A, 5, 1, b""),
        (0x011B, 5, 1, b""),
    ]
    if unit is not None:
        entries.append((0x0128, 3, 1, struct.pack(order + "HH", unit, 0)))
    if camera:
        entries.append((0x8769, 4, 1, b""))
    ifd_size = 2 + 12 * len(entries) + 4
    data_offset = 8 + ifd_size
    rationals = struct.pack(order + "IIII", round(x_dpi * 1000), 1000, round(y_dpi * 1000), 1000)
    exif_ifd_offset = data_offset + len(rationals)
    ifd = struct.pack(order + "H", len(entries))
    for tag, kind, count, inline in entries:
        if tag == 0x011A:
            inline = struct.pack(order + "I", data_offset)
        elif tag == 0x011B:
            inline = struct.pack(order + "I", data_offset + 8)
        elif tag == 0x8769:
            inline = struct.pack(order + "I", exif_ifd_offset)
        ifd += struct.pack(order + "HHI", tag, kind, count) + inline
    ifd += struct.pack(order + "I", 0)
    exif_ifd = b""
    if camera:
        focal = exif_ifd_offset + 2 + 12 + 4
        exif_ifd = (
            struct.pack(order + "H", 1)
            + struct.pack(order + "HHII", 0x920A, 5, 1, focal)
            + struct.pack(order + "I", 0)
            + struct.pack(order + "II", 4200, 1000)
        )
    return header + ifd + rationals + exif_ifd


def _jpeg_with_exif(block: bytes, jfif_units: int = 0) -> bytes:
    """An OpenCV JPEG with its JFIF units set to ``jfif_units`` and an EXIF segment added."""
    encoded = cv2.imencode(".jpg", BLANK)[1].tobytes()
    encoded = encoded[:13] + struct.pack(">BHH", jfif_units, 300, 300) + encoded[18:]
    body = b"Exif\x00\x00" + block
    segment = b"\xff\xe1" + struct.pack(">H", len(body) + 2) + body
    return encoded[:2] + segment + encoded[2:]


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".tif"])
@pytest.mark.parametrize("dpi", [150.0, 300.0, 600.0, 1200.0])
def test_save_image_stores_a_resolution_read_resolution_finds(
    tmp_path: Path, suffix: str, dpi: float
) -> None:
    target = tmp_path / f"code{suffix}"
    save_image(target, BLANK, dpi)
    resolution = read_resolution(target)
    assert resolution.dpi == dpi
    assert resolution.source == {".png": "png-phys", ".jpg": "jpeg-jfif", ".tif": "tiff"}[suffix]


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".tif"])
def test_files_without_a_resolution(tmp_path: Path, suffix: str) -> None:
    target = tmp_path / f"code{suffix}"
    save_image(target, BLANK)
    assert read_resolution(target) == Resolution(None)


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".tif"])
def test_different_horizontal_and_vertical_resolutions_are_ignored(
    tmp_path: Path, suffix: str
) -> None:
    target = tmp_path / f"code{suffix}"
    save_image(target, BLANK, (300.0, 200.0))
    resolution = read_resolution(target)
    assert resolution.dpi is None and "differ" in (resolution.note or "")


@pytest.mark.parametrize("dpi", [72.0, 96.0])
def test_software_default_resolutions_are_ignored(tmp_path: Path, dpi: float) -> None:
    target = tmp_path / "screen.png"
    save_image(target, BLANK, dpi)
    resolution = read_resolution(target)
    assert dpi < MIN_TRUSTED_DPI
    assert resolution.dpi is None and "default" in (resolution.note or "")


def test_saved_png_and_jpeg_still_decode_as_images(tmp_path: Path) -> None:
    for suffix in (".png", ".jpg"):
        target = tmp_path / f"code{suffix}"
        save_image(target, BLANK, 300.0)
        decoded = cv2.imdecode(np.fromfile(str(target), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        assert decoded is not None and decoded.shape == BLANK.shape


@pytest.mark.parametrize("order", ["<", ">"])
def test_exif_resolution_in_a_jpeg(order: str) -> None:
    data = _jpeg_with_exif(_tiff_block(400.0, 400.0, order=order))
    assert resolution_from_bytes(data) == Resolution(400.0, "exif")


def test_exif_resolution_in_centimetres() -> None:
    data = _jpeg_with_exif(_tiff_block(118.11, 118.11, unit=3))
    assert resolution_from_bytes(data).dpi == pytest.approx(300.0, abs=0.01)


def test_exif_resolution_without_a_unit_defaults_to_inches() -> None:
    data = _jpeg_with_exif(_tiff_block(300.0, 300.0, unit=None))
    assert resolution_from_bytes(data) == Resolution(300.0, "exif")


def test_exif_resolution_with_no_absolute_unit_is_ignored() -> None:
    data = _jpeg_with_exif(_tiff_block(300.0, 300.0, unit=1))
    assert resolution_from_bytes(data) == Resolution(None)


def test_jfif_density_wins_over_exif() -> None:
    data = _jpeg_with_exif(_tiff_block(400.0, 400.0), jfif_units=1)
    assert resolution_from_bytes(data) == Resolution(300.0, "jpeg-jfif")


@pytest.mark.parametrize("jfif_units", [0, 1])
def test_camera_photo_resolution_is_ignored(jfif_units: int) -> None:
    data = _jpeg_with_exif(_tiff_block(300.0, 300.0, camera=True), jfif_units=jfif_units)
    resolution = resolution_from_bytes(data)
    assert resolution.dpi is None and "camera" in (resolution.note or "")


def test_camera_exif_in_a_png_voids_its_phys() -> None:
    png = with_resolution(cv2.imencode(".png", BLANK)[1].tobytes(), ".png", (300.0, 300.0))
    block = _tiff_block(300.0, 300.0, camera=True)
    body = b"eXIf" + block
    chunk = struct.pack(">I", len(block)) + body + struct.pack(">I", 0)
    end_of_header = 8 + 8 + 13 + 4
    data = png[:end_of_header] + chunk + png[end_of_header:]
    assert resolution_from_bytes(data).dpi is None


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image",
        b"\x89PNG\r\n\x1a\n\x00\x00",
        b"\xff\xd8\xff\xe0\x00",
        b"II*\x00\xff\xff\xff\xff",
        b"\xff\xd8" + b"\xff\xe1\x00\x10Exif\x00\x00II*\x00\x08\x00",
    ],
    ids=["empty", "text", "short-png", "short-jpeg", "bad-tiff-offset", "short-exif"],
)
def test_malformed_files_have_no_resolution(data: bytes) -> None:
    assert resolution_from_bytes(data) == Resolution(None)


def test_read_resolution_of_a_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        read_resolution(tmp_path / "missing.png")
