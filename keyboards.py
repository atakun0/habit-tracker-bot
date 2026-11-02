from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить привычку"), KeyboardButton(text="✅ Отметить выполнение")],
        [KeyboardButton(text="📋 Мои привычки"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🗑 Удалить привычку"), KeyboardButton(text="✏️ Изменить")],
        [KeyboardButton(text="📁 Экспорт данных"), KeyboardButton(text="❓ Помощь")],
        [KeyboardButton(text="📈 График")],
        [KeyboardButton(text="📝 Итоги дня"), KeyboardButton(text="🏆 Рекорды")],
        [KeyboardButton(text="👤 Мой профиль")]
    ],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Отмена")]
    ],
    resize_keyboard=True
)

def habits_kb(habits_list: list[str]):
    buttons = [[KeyboardButton(text=habit)] for habit in habits_list]
    buttons.append([KeyboardButton(text="Отмена")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)