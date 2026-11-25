TARGET_DAYS = 21  # Глобальная цель для формирования привычки


def get_streak_emoji(streak: int) -> str:
    if streak <= 0:
        return "🧊"
    elif streak < 3:
        return "🌱"
    elif streak < 7:
        return "🌿"
    elif streak < 14:
        return "🔥"
    elif streak < 21:
        return "⚡️"
    return "👑"


def make_progress_bar(current: int, target: int = TARGET_DAYS) -> str:
    if target <= 0:
        return "░" * 10
    percent = min(max(current / target, 0.0), 1.0)
    filled_blocks = int(percent * 10)
    return "█" * filled_blocks + "░" * (10 - filled_blocks)