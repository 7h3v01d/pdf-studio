"""
startup_splash_core.py
----------------------
Pure startup-splash calculations kept separate from PyQt so the timing and
high-DPI sizing rules can be regression-tested without a GUI environment.
"""
from __future__ import annotations

from math import ceil
from typing import Tuple

MIN_SPLASH_MS = 4_500
FADE_DURATION_MS = 350
MAX_SCREEN_FRACTION = 0.92


def remaining_display_ms(
    elapsed_ms: int | float,
    minimum_ms: int = MIN_SPLASH_MS,
) -> int:
    """Return the remaining whole milliseconds in the minimum display period."""
    if minimum_ms < 0:
        raise ValueError("minimum_ms cannot be negative")

    elapsed = max(0.0, float(elapsed_ms))
    return max(0, int(ceil(float(minimum_ms) - elapsed)))


def scaled_splash_size(
    image_width: int,
    image_height: int,
    available_width: int,
    available_height: int,
    max_screen_fraction: float = MAX_SCREEN_FRACTION,
) -> Tuple[int, int]:
    """
    Fit the splash inside the active screen while preserving its aspect ratio.

    The source artwork is never enlarged. On smaller or heavily scaled screens
    it is reduced to at most ``max_screen_fraction`` of the available geometry.
    """
    values = (image_width, image_height, available_width, available_height)
    if any(int(value) <= 0 for value in values):
        raise ValueError("image and screen dimensions must be positive")
    if not 0 < float(max_screen_fraction) <= 1:
        raise ValueError("max_screen_fraction must be greater than 0 and at most 1")

    max_width = float(available_width) * float(max_screen_fraction)
    max_height = float(available_height) * float(max_screen_fraction)
    scale = min(1.0, max_width / image_width, max_height / image_height)

    return (
        max(1, int(round(image_width * scale))),
        max(1, int(round(image_height * scale))),
    )
