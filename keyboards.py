from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить привычку"), KeyboardButton(text="🗑 Удалить привычку")],
        [KeyboardButton(text="📋 Мои привычки"), KeyboardButton(text="❓ Помощь")]
    ],
    resize_keyboard=True
)