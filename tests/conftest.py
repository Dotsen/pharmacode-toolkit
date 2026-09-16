from __future__ import annotations

import numpy as np
import pytest

from pharmacode.models import DecodedPharmacode, DecodeResult

SEED = 20260919


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(SEED)


def single(result: DecodeResult) -> DecodedPharmacode:
    """Assert exactly one clean detection and return it."""
    assert result.ok, [e.to_dict() for e in result.errors]
    assert len(result.detections) == 1, result.to_dict()
    return result.detections[0]
