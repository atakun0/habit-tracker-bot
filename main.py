import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить привычку")],
        [KeyboardButton(text="📋 Мои привычки"), KeyboardButton(text="❓ Помощь")]
    ],
    resize_keyboard=True
)

class AddHabit(StatesGroup):
    waiting_for_name = State()

@dp.message(CommandStart())
async def command_start_handler(message: Message):
    await message.answer(
        "Привет! Я твой трекер привычек. Выбери действие ниже 👇",
        reply_markup=main_kb
    )

@dp.message(Command("help"))
async def command_help_handler(message: Message):
    await message.answer("Мои команды:\n/start - Перезапуск\n/help - Справка")

@dp.message(F.text == "❓ Помощь")
async def help_button_handler(message: Message):
    await message.answer("Раздел помощи.\nПока я умею только здороваться, но скоро научусь трекать твои привычки! Выбери нужное действие в меню.")

@dp.message(F.text == "➕ Добавить привычку")
async def add_habit_start(message: Message, state: FSMContext):
    await message.answer("Отлично! Напиши название новой привычки (например, 'Зарядка' или 'Чтение'):")
    await state.set_state(AddHabit.waiting_for_name)

@dp.message(AddHabit.waiting_for_name)
async def add_habit_name(message: Message, state: FSMContext):
    habit_name = message.text
    await message.answer(f"Привычка «{habit_name}» успешно добавлена! (пока понарошку)")
    await state.clear()

async def main():
    print("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())