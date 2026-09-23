"""Resolution (DPI) stored in PNG, JPEG and TIFF files.

OpenCV discards image metadata, so the few fields that matter are read here
directly from the file bytes: the PNG ``pHYs`` chunk, the JPEG JFIF header,
and the ``XResolution``/``YResolution``/``ResolutionUnit`` tags of a TIFF
file or of the EXIF block inside a JPEG or PNG.

A stored resolution describes the scene only for a scan or a generated
image. A camera photo also carries one (72, 180, 300 or 350 DPI, depending
on the maker), but it is a print hint unrelated to how many pixels a
millimetre of the photographed package covers. So the value is ignored when
the file carries camera exposure data (EXIF ``ExposureTime``, ``FNumber`` or
``FocalLength``), when it is below :data:`MIN_TRUSTED_DPI` or above
:data:`MAX_TRUSTED_DPI`, and when the
horizontal and vertical resolutions differ.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

# Below this, a nominal 0.5 mm narrow bar is under 2 px wide, which the
# decoder does not support (see docs/limitations.md). Such a value is almost
# always a software default (72 or 96 DPI) rather than a real scan resolution.
MIN_TRUSTED_DPI = 100.0
# Above this, a stored value is not a real scan resolution (flatbed scanners resolve at most
# 4800 DPI optically), and the decoder's kernels, sized in mm, would need absurd amounts of
# memory: a file claiming 10^8 DPI would otherwise exhaust it.
MAX_TRUSTED_DPI = 4800.0

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MM_PER_INCH = 25.4
_TAG_X_RESOLUTION = 0x011A
_TAG_Y_RESOLUTION = 0x011B
_TAG_RESOLUTION_UNIT = 0x0128
_TAG_EXIF_IFD = 0x8769
_CAMERA_TAGS = {0x829A, 0x829D, 0x920A}  # ExposureTime, FNumber, FocalLength
_TIFF_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 11: 4, 12: 8}


@dataclass(frozen=True)
class Resolution:
    """Outcome of reading a file's resolution.

    ``dpi`` is ``None`` when the file has no usable value; ``note`` then says
    why, when there was a value that was rejected. ``source`` names where the
    value came from: ``"png-phys"``, ``"jpeg-jfif"``, ``"exif"`` or ``"tiff"``.
    """

    dpi: float | None
    source: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class _Found:
    x: float
    y: float
    source: str


@dataclass(frozen=True)
class _Ifd:
    resolution: tuple[float, float] | None
    camera: bool


def read_resolution(path: str | Path) -> Resolution:
    """Return the resolution stored in the image file at ``path``.

    Never raises for malformed or unsupported files: anything that cannot be
    parsed is simply reported as ``Resolution(None)``. Raises ``OSError``
    only when the file cannot be read at all.
    """
    return resolution_from_bytes(Path(path).read_bytes())


def resolution_from_bytes(data: bytes) -> Resolution:
    """:func:`read_resolution` for a file already in memory."""
    try:
        if data.startswith(_PNG_SIGNATURE):
            found, camera = _png(data)
        elif data.startswith(b"\xff\xd8"):
            found, camera = _jpeg(data)
        elif data[:4] in (b"II*\x00", b"MM\x00*"):
            ifd = _tiff(data)
            found = _Found(*ifd.resolution, "tiff") if ifd.resolution else None
            camera = ifd.camera
        else:
            return Resolution(None)
    except (struct.error, IndexError, ValueError, ZeroDivisionError):
        return Resolution(None)
    return _judge(found, camera)


def _judge(found: _Found | None, camera: bool) -> Resolution:
    if found is None:
        return Resolution(None)
    if camera:
        return Resolution(
            None,
            note=f"ignored {_dpi(found.x)} DPI ({found.source}): the file is a camera photo, "
            "whose stored resolution does not describe the photographed object",
        )
    if abs(found.x - found.y) > 0.01 * max(found.x, found.y):
        return Resolution(
            None,
            note=f"ignored {_dpi(found.x)} x {_dpi(found.y)} DPI ({found.source}): "
            "horizontal and vertical resolutions differ",
        )
    if found.x < MIN_TRUSTED_DPI:
        return Resolution(
            None,
            note=f"ignored {_dpi(found.x)} DPI ({found.source}): below {MIN_TRUSTED_DPI:g} DPI, "
            "a stored resolution is a software default, not a scan resolution",
        )
    # one decimal absorbs the PNG pixels-per-metre rounding (150 DPI is stored as 150.0124)
    if found.x > MAX_TRUSTED_DPI:
        return Resolution(
            None,
            note=f"ignored {_dpi(found.x)} DPI ({found.source}): above {MAX_TRUSTED_DPI:g} DPI, "
            "no scanner resolves that",
        )
    return Resolution(round(found.x, 1), found.source)


def _dpi(value: float) -> str:
    return f"{round(value, 1):g}"


def _png(data: bytes) -> tuple[_Found | None, bool]:
    found: _Found | None = None
    camera = False
    offset = len(_PNG_SIGNATURE)
    while offset + 8 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, offset)
        body = data[offset + 8 : offset + 8 + length]
        if kind == b"pHYs" and len(body) >= 9:
            x, y, unit = struct.unpack_from(">IIB", body)
            if unit == 1:  # pixels per metre
                found = _Found(x * _MM_PER_INCH / 1000.0, y * _MM_PER_INCH / 1000.0, "png-phys")
        elif kind == b"eXIf":
            camera = _tiff(body).camera
        elif kind in (b"IDAT", b"IEND"):
            break
        offset += 12 + length
    return found, camera


def _jpeg(data: bytes) -> tuple[_Found | None, bool]:
    jfif: _Found | None = None
    exif: _Ifd | None = None
    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            break
        marker = data[offset + 1]
        if marker == 0xFF:  # fill byte
            offset += 1
            continue
        if marker == 0xD8 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            offset += 2
            continue
        if marker in (0xDA, 0xD9):  # start of scan, end of image: no more metadata
            break
        (length,) = struct.unpack_from(">H", data, offset + 2)
        body = data[offset + 4 : offset + 2 + length]
        if marker == 0xE0 and body.startswith(b"JFIF\x00") and len(body) >= 12:
            unit, x, y = struct.unpack_from(">BHH", body, 7)
            scale = {1: 1.0, 2: 2.54}.get(unit)  # dots per inch, dots per centimetre
            if scale is not None:
                jfif = _Found(x * scale, y * scale, "jpeg-jfif")
        elif marker == 0xE1 and body.startswith(b"Exif\x00\x00") and exif is None:
            exif = _tiff(body[6:])
        offset += 2 + length
    camera = exif.camera if exif else False
    if jfif is not None:
        return jfif, camera
    if exif is not None and exif.resolution is not None:
        return _Found(*exif.resolution, "exif"), camera
    return None, camera


def _tiff(data: bytes) -> _Ifd:
    """First IFD of a TIFF structure: resolution in DPI, and whether camera tags exist
    (in that IFD or in the Exif sub-IFD it points to)."""
    order = "<" if data[:2] == b"II" else ">"
    (first,) = struct.unpack_from(order + "I", data, 4)
    tags = _ifd_entries(data, first, order)
    camera = bool(_CAMERA_TAGS & tags.keys())
    if _TAG_EXIF_IFD in tags:
        exif_tags = _ifd_entries(data, int(_value(data, tags[_TAG_EXIF_IFD], order)), order)
        camera = camera or bool(_CAMERA_TAGS & exif_tags.keys())
    resolution = None
    if _TAG_X_RESOLUTION in tags and _TAG_Y_RESOLUTION in tags:
        unit = 2  # the TIFF default unit is the inch
        if _TAG_RESOLUTION_UNIT in tags:
            unit = int(_value(data, tags[_TAG_RESOLUTION_UNIT], order))
        scale = {2: 1.0, 3: 2.54}.get(unit)  # per inch, per centimetre; 1 means no unit
        if scale is not None:
            x = _value(data, tags[_TAG_X_RESOLUTION], order) * scale
            y = _value(data, tags[_TAG_Y_RESOLUTION], order) * scale
            resolution = (x, y)
    return _Ifd(resolution, camera)


def _ifd_entries(data: bytes, offset: int, order: str) -> dict[int, tuple[int, int, int]]:
    """``{tag: (type, count, entry offset)}`` for every entry of the IFD at ``offset``."""
    (count,) = struct.unpack_from(order + "H", data, offset)
    entries: dict[int, tuple[int, int, int]] = {}
    for index in range(count):
        entry = offset + 2 + 12 * index
        tag, kind, values = struct.unpack_from(order + "HHI", data, entry)
        entries[tag] = (kind, values, entry)
    return entries


def _value(data: bytes, entry: tuple[int, int, int], order: str) -> float:
    """First value of an IFD entry of type SHORT, LONG or RATIONAL."""
    kind, count, offset = entry
    size = _TIFF_TYPE_SIZES.get(kind, 0) * count
    position = offset + 8
    if size > 4:
        (position,) = struct.unpack_from(order + "I", data, offset + 8)
    if kind == 3:
        return float(struct.unpack_from(order + "H", data, position)[0])
    if kind == 4:
        return float(struct.unpack_from(order + "I", data, position)[0])
    if kind == 5:
        numerator, denominator = struct.unpack_from(order + "II", data, position)
        return numerator / denominator
    raise ValueError(f"unsupported TIFF value type {kind}")


def with_resolution(encoded: bytes, suffix: str, dpi: tuple[float, float]) -> bytes:
    """Return a PNG or JPEG file as encoded by OpenCV, with ``(x, y)`` DPI stored in it.

    PNG gets a ``pHYs`` chunk after ``IHDR``; JPEG gets its JFIF header's
    density set (whole DPI, as JFIF stores it). Other formats are returned
    unchanged: OpenCV writes the TIFF resolution itself.
    """
    if suffix == ".png" and encoded.startswith(_PNG_SIGNATURE):
        ppm = [round(value * 1000.0 / _MM_PER_INCH) for value in dpi]
        body = b"pHYs" + struct.pack(">IIB", ppm[0], ppm[1], 1)
        chunk = struct.pack(">I", 9) + body + struct.pack(">I", zlib.crc32(body))
        end_of_header = len(_PNG_SIGNATURE) + 8 + 13 + 4  # IHDR: length, type, data, CRC
        return encoded[:end_of_header] + chunk + encoded[end_of_header:]
    if suffix in (".jpg", ".jpeg") and encoded[2:4] == b"\xff\xe0" and encoded[6:11] == b"JFIF\x00":
        density = struct.pack(">BHH", 1, *(min(65535, round(value)) for value in dpi))
        return encoded[:13] + density + encoded[18:]
    return encoded
