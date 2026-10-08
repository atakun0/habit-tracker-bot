import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, BotCommand
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from db import init_db, add_habit, get_habits, delete_habit, log_habit
from keyboards import main_kb, cancel_kb

class LogHabit(StatesGroup):
    waiting_for_habit_name = State()

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
    await message.answer("Действие отменено. Можешь продолжать работу с меню.", reply_markup=main_kb) # Убедись, что тут есть main_kb

@dp.message(F.text == "➕ Добавить привычку")
async def add_habit_start(message: Message, state: FSMContext):
    await message.answer("Отлично! Напиши название новой привычки:", reply_markup=cancel_kb)
    await state.set_state(AddHabit.waiting_for_name)

@dp.message(AddHabit.waiting_for_name)
async def add_habit_name(message: Message, state: FSMContext):
    habit_name = message.text
    user_id = message.from_user.id
    
    add_habit(user_id, habit_name)
    
    await message.answer(f"Супер! Привычка «{habit_name}» успешно добавлена и сохранена в базу!", reply_markup=main_kb)

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

async def set_default_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="help", description="Справка по боту"),
        BotCommand(command="cancel", description="Отменить текущее действие")
    ]
    await bot.set_my_commands(commands)

@dp.message(F.text == "✅ Отметить выполнение")
async def log_habit_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    habits = get_habits(user_id)
    
    if not habits:
        await message.answer("У тебя пока нет добавленных привычек. Сначала добавь их!")
        return
        
    habits_list = "\n".join([f"- {h}" for h in habits])
    await message.answer(
        f"Твои привычки:\n{habits_list}\n\nКакую привычку ты сегодня выполнил? Напиши точное название:", 
        reply_markup=cancel_kb
    )
    await state.set_state(LogHabit.waiting_for_habit_name)

@dp.message(LogHabit.waiting_for_habit_name)
async def log_habit_name(message: Message, state: FSMContext):
    habit_name = message.text
    user_id = message.from_user.id
    
    habits = get_habits(user_id)
    if habit_name not in habits:
        await message.answer("Такой привычки нет в твоем списке. Напиши точное название или нажми «Отмена».")
        return
        
    log_habit(user_id, habit_name)
    
    await message.answer(f"Отлично! Выполнение привычки «{habit_name}» записано на сегодня ✅", reply_markup=main_kb)
    await state.clear()

async def main():
    init_db()
    logger.info("Бот успешно запущен и готов к работе!")
    
    await set_default_commands(bot)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())