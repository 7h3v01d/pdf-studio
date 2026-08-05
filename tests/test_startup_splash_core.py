import pytest

from startup_splash_core import remaining_display_ms, scaled_splash_size


def test_remaining_display_enforces_minimum_without_sleeping():
    assert remaining_display_ms(0, 4500) == 4500
    assert remaining_display_ms(1250, 4500) == 3250
    assert remaining_display_ms(4499, 4500) == 1
    assert remaining_display_ms(4499.6, 4500) == 1


def test_remaining_display_is_zero_after_minimum_and_clamps_negative_elapsed():
    assert remaining_display_ms(4500, 4500) == 0
    assert remaining_display_ms(9000, 4500) == 0
    assert remaining_display_ms(-100, 4500) == 4500


def test_remaining_display_rejects_negative_minimum():
    with pytest.raises(ValueError, match="cannot be negative"):
        remaining_display_ms(0, -1)


def test_scaled_splash_size_preserves_ratio_fits_screen_and_never_upscales():
    assert scaled_splash_size(750, 500, 1920, 1080) == (750, 500)
    assert scaled_splash_size(750, 500, 600, 400) == (552, 368)

    with pytest.raises(ValueError, match="dimensions must be positive"):
        scaled_splash_size(0, 500, 1920, 1080)
