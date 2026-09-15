"""Shared image helpers used by the renderer and the decoder."""

from __future__ import annotations

import cv2
import numpy as np


def rotate_bound(image: np.ndarray, angle_deg: float, border_value: int = 255) -> np.ndarray:
    """Rotate counter-clockwise (as displayed) by ``angle_deg`` and expand the canvas.

    Exact multiples of 90 degrees use ``numpy.rot90`` and are lossless.
    """
    turns = angle_deg / 90.0
    if float(turns).is_integer():
        return np.ascontiguousarray(np.rot90(image, k=int(turns) % 4))
    height, width = image.shape[:2]
    centre = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(centre, angle_deg, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_width = int(round(height * sin + width * cos))
    new_height = int(round(height * cos + width * sin))
    matrix[0, 2] += new_width / 2.0 - centre[0]
    matrix[1, 2] += new_height / 2.0 - centre[1]
    return cv2.warpAffine(
        image,
        matrix,
        (new_width, new_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )


def flatten_background(gray: np.ndarray, kernel_fraction: float) -> np.ndarray:
    """Divide by a morphological estimate of the paper to remove illumination gradients.

    A grayscale closing with a kernel larger than any bar removes the bars and
    leaves the background; dividing by it maps paper to white everywhere.
    """
    size = max(15, int(max(gray.shape) * kernel_fraction)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (size, size))
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    background = cv2.GaussianBlur(background, (size, size), 0)
    ratio = gray.astype(np.float32) / np.maximum(background.astype(np.float32), 1.0)
    return np.clip(ratio * 255.0, 0, 255).astype(np.uint8)


def otsu_mask(gray: np.ndarray) -> np.ndarray:
    """Return a 0/255 mask where 255 marks ink (dark pixels)."""
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return mask
