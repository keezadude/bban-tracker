import numpy as np
import cv2
import math

import pytest

from objects import Contour, Bey, set_smoothing_alpha, SMOOTH_ALPHA


def _dummy_contour(x: int = 0, y: int = 0, size: int = 10):
    """Return a rectangular OpenCV contour centred on (x,y)."""
    half = size // 2
    pts = np.array([
        [[x - half, y - half]],
        [[x + half, y - half]],
        [[x + half, y + half]],
        [[x - half, y + half]],
    ], dtype=np.int32)
    return pts


def test_set_smoothing_alpha_clamps():
    # Values outside valid range should be clamped silently
    set_smoothing_alpha(-1.0)
    assert math.isclose(SMOOTH_ALPHA, 0.0)
    set_smoothing_alpha(2.0)
    assert math.isclose(SMOOTH_ALPHA, 1.0)
    # Nominal value
    set_smoothing_alpha(0.3)
    assert math.isclose(SMOOTH_ALPHA, 0.3)


def test_bey_position_smoothing():
    # Use moderate smoothing for test clarity (alpha=0.5 => equal blend)
    set_smoothing_alpha(0.5)

    # First frame – reference Bey at (100,100)
    c1 = Contour(_dummy_contour(100, 100))
    bey_prev = Bey(c1)
    bey_prev.setFrame(0)
    bey_prev.setId(1)

    # Simulate next frame measurement with large displacement to (150,150)
    c2 = Contour(_dummy_contour(150, 150))
    bey_curr = Bey(c2)
    bey_curr.setFrame(1)

    # Associate with previous and run smoothing
    bey_curr.setPreBey(bey_prev)

    # Expected position: halfway between 150 (measurement) and Kalman estimate (~100)
    # Kalman after one predict/update with constant velocity should still be close to 100.
    # So smoothed pos should be noticeably less than 150.
    x, y = bey_curr.getPos()
    assert x < 150 and y < 150, "Position should be smoothed towards previous state"
    assert x > 100 and y > 100, "Position should still move forward from previous measurement" 