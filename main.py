import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from db import init_db, add_habit, get_habits, delete_habit  # Добавили delete_habit

class AddHabit(StatesGroup):
    waiting_for_name = State()

class DeleteHabit(StatesGroup):
    waiting_for_habit_name = State()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить привычку"), KeyboardButton(text="🗑 Удалить привычку")], # Новая кнопка
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

@dp.message(Command("cancel"))
@dp.message(F.text.lower() == "отмена")
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
        
    await state.clear()
    await message.answer("Действие отменено. Можешь продолжать работу с меню.", reply_markup=main_kb)

@dp.message(F.text == "➕ Добавить привычку")
async def add_habit_start(message: Message, state: FSMContext):
    await message.answer("Отлично! Напиши название новой привычки (или напиши «отмена», если передумал):")
    await state.set_state(AddHabit.waiting_for_name)

@dp.message(AddHabit.waiting_for_name)
async def add_habit_name(message: Message, state: FSMContext):
    habit_name = message.text
    user_id = message.from_user.id
    
    add_habit(user_id, habit_name)
    
    await message.answer(f"Супер! Привычка «{habit_name}» успешно добавлена и сохранена в базу!")
    await state.clear()

@dp.message(F.text == "📋 Мои привычки")
async def show_habits_handler(message: Message):
    user_id = message.from_user.id
    habits = get_habits(user_id)
    
    if not habits:
        await message.answer("У тебя пока нет добавленных привычек. Нажми «➕ Добавить привычку», чтобы начать!")
    else:
        # Формируем красивый список
        response = "Твои привычки:\n\n"
        for i, habit in enumerate(habits, start=1):
            response += f"{i}. {habit}\n"
        
        await message.answer(response)

async def main():
    init_db()
    logger.info("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())