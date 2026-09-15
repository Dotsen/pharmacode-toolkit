from __future__ import annotations

import numpy as np
import pytest

SEED = 20260919


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(SEED)
