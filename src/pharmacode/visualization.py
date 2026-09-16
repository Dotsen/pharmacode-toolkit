"""Diagnostic drawing of decode results."""

from __future__ import annotations

import math

import cv2
import numpy as np

from pharmacode.models import BarKind, DecodedPharmacode, DecodeError, DecodeResult

GREEN = (0, 220, 0)  # matches RED's brightness so solid (non-antialiased) fills exceed 200
RED = (0, 0, 220)
BLUE = (220, 120, 0)
ORANGE = (0, 140, 255)
BLACK = (0, 0, 0)


def _scale(canvas: np.ndarray) -> float:
    return max(0.5, min(canvas.shape[:2]) / 600.0)


def _label(canvas: np.ndarray, text: str, x: int, y: int, colour: tuple[int, int, int]) -> None:
    scale = _scale(canvas)
    font = cv2.FONT_HERSHEY_SIMPLEX
    (width, height), _ = cv2.getTextSize(text, font, 0.6 * scale, max(1, int(scale)))
    y = max(height + 4, y)
    cv2.rectangle(canvas, (x, y - height - 4), (x + width + 4, y + 2), (255, 255, 255), -1)
    cv2.putText(
        canvas, text, (x + 2, y - 2), font, 0.6 * scale, colour, max(1, int(scale)), cv2.LINE_AA
    )


def _draw_detection(canvas: np.ndarray, detection: DecodedPharmacode) -> None:
    box = detection.bbox
    thickness = max(1, int(2 * _scale(canvas)))
    cv2.rectangle(canvas, (box.x, box.y), (box.x + box.width, box.y + box.height), GREEN, thickness)
    for kind, rect in zip(detection.bars, detection.bar_rects, strict=False):
        corners = cv2.boxPoints(((rect.cx, rect.cy), (rect.length, rect.thickness), rect.angle_deg))
        colour = ORANGE if kind is BarKind.WIDE else BLUE
        cv2.polylines(canvas, [np.int32(corners)], True, colour, thickness)
    theta = math.radians(detection.orientation_deg)
    cx, cy = box.x + box.width / 2.0, box.y + box.height / 2.0
    half = 0.4 * (box.width if abs(detection.orientation_deg) < 45 else box.height)
    start = (int(cx - math.cos(theta) * half), int(cy - math.sin(theta) * half))
    end = (int(cx + math.cos(theta) * half), int(cy + math.sin(theta) * half))
    cv2.arrowedLine(canvas, start, end, GREEN, thickness, tipLength=0.08)
    text = f"{detection.value} / {detection.mirror_value}  ({detection.confidence:.2f})"
    _label(canvas, text, box.x, box.y - 4, BLACK)


def _draw_error(canvas: np.ndarray, error: DecodeError) -> None:
    if error.bbox is None:
        return
    box = error.bbox
    thickness = max(1, int(2 * _scale(canvas)))
    cv2.rectangle(canvas, (box.x, box.y), (box.x + box.width, box.y + box.height), RED, thickness)
    _label(canvas, error.code.value, box.x, box.y - 4, RED)


def annotate(image: np.ndarray, result: DecodeResult) -> np.ndarray:
    """Return a BGR copy of ``image`` with boxes, reading arrows, values and error codes."""
    canvas = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image.copy()
    for detection in result.detections:
        _draw_detection(canvas, detection)
    for error in result.errors:
        _draw_error(canvas, error)
    return canvas
