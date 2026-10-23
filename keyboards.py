from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ Отметить выполнение")],
        [KeyboardButton(text="➕ Добавить привычку"), KeyboardButton(text="🗑 Удалить привычку")],
        [KeyboardButton(text="📋 Мои привычки"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="❓ Помощь")],
        [KeyboardButton(text="✏️ Изменить")],
        [KeyboardButton(text="📈 График"), KeyboardButton(text="📁 Экспорт данных")],
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