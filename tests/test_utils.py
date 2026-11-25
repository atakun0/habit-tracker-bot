import pytest
from utils import get_streak_emoji, make_progress_bar


@pytest.mark.parametrize(
    "streak, expected",
    [
        (-1, "🧊"),
        (0, "🧊"),
        (1, "🌱"),
        (2, "🌱"),
        (3, "🌿"),
        (6, "🌿"),
        (7, "🔥"),
        (13, "🔥"),
        (14, "⚡️"),
        (20, "⚡️"),
        (21, "👑"),
        (100, "👑"),
    ],
)
def test_get_streak_emoji(streak, expected):
    assert get_streak_emoji(streak) == expected


def test_make_progress_bar_normal():
    assert make_progress_bar(0, 10) == "░░░░░░░░░░"
    assert make_progress_bar(5, 10) == "█████░░░░░"
    assert make_progress_bar(10, 10) == "██████████"


def test_make_progress_bar_bounds():
    # Перевыполнение цели не должно ломать длину шкалы
    assert make_progress_bar(50, 21) == "██████████"
    # Отрицательный прогресс и нулевая цель
    assert make_progress_bar(-5, 10) == "░░░░░░░░░░"
    assert make_progress_bar(5, 0) == "░░░░░░░░░░"