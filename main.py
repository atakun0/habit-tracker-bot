import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, BotCommand
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.session.aiohttp import AiohttpSession

from db import init_db, add_habit, get_habits, delete_habit, log_habit, get_habit_stats, check_habit_logged_today
from keyboards import main_kb, cancel_kb, habits_kb

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
PROXY_URL = os.getenv("PROXY_URL")

session = AiohttpSession(proxy=PROXY_URL)
bot = Bot(
    token=TOKEN, 
    session=session, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

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


@dp.message(Command("cancel"))
@dp.message(F.text.lower() == "отмена")
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
        
    await state.clear()
    await message.answer("Действие отменено. Можешь продолжать работу с меню.", reply_markup=main_kb) # Убедись, что тут есть main_kb

@dp.message(F.text == "❓ Помощь")
@dp.message(Command("help"))
async def help_handler(message: Message):
    help_text = (
        "🤖 <b>Как пользоваться трекером:</b>\n\n"
        "➕ <b>Добавить привычку</b> — создать новую привычку для отслеживания.\n"
        "✅ <b>Отметить выполнение</b> — записать прогресс на сегодня (защита от повторов включена!).\n"
        "📋 <b>Мои привычки</b> — посмотреть весь список твоих целей.\n"
        "📊 <b>Статистика</b> — узнать, сколько раз была выполнена каждая привычка.\n"
        "🗑 <b>Удалить привычку</b> — убрать неактуальную цель.\n\n"
        "<i>💡 Если бот ждет от тебя ввода, а ты передумал — просто нажми кнопку «Отмена» или напиши команду /cancel.</i>"
    )
    
    await message.answer(help_text)

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

@dp.message(F.text == "📊 Статистика")
async def show_statistics_handler(message: Message):
    user_id = message.from_user.id
    stats = get_habit_stats(user_id)
    
    if not stats:
        await message.answer("У тебя пока нет отметок о выполнении привычек. Сделай хотя бы одну!")
        return
        
    response = "📊 Твоя статистика выполнений:\n\n"
    for habit_name, count in stats:
        response += f"🔹 {habit_name}: {count} раз(а)\n"
        
    await message.answer(response)

@dp.message(F.text == "📋 Мои привычки")
async def show_habits_handler(message: Message):
    user_id = message.from_user.id
    habits = get_habits(user_id)
    
    if not habits:
        await message.answer("У тебя пока нет добавленных привычек. Нажми «➕ Добавить привычку», чтобы начать!")
        return
        
    response = "Твои привычки и статус на сегодня:\n\n"
    for i, habit in enumerate(habits, start=1):
        is_done = check_habit_logged_today(user_id, habit)
        status_emoji = "✅" if is_done else "❌"
        
        response += f"{i}. {habit} {status_emoji}\n"
        
    await message.answer(response)

@dp.message(F.text == "🗑 Удалить привычку")
async def delete_habit_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    habits = get_habits(user_id)
    
    if not habits:
        await message.answer("У тебя пока нет привычек, нечего удалять!")
        return
        
    await message.answer(
        "Выбери привычку, которую хочешь удалить, на клавиатуре ниже:",
        reply_markup=habits_kb(habits)
    )
    await state.set_state(DeleteHabit.waiting_for_habit_name)

@dp.message(DeleteHabit.waiting_for_habit_name)
async def delete_habit_name(message: Message, state: FSMContext):
    habit_name = message.text
    user_id = message.from_user.id
    
    habits = get_habits(user_id)
    if habit_name not in habits:
        await message.answer("Такой привычки нет в твоем списке. Выбери из меню или нажми «Отмена».")
        return
        
    delete_habit(user_id, habit_name)
    await message.answer(f"Привычка «{habit_name}» успешно удалена 🗑", reply_markup=main_kb)
    await state.clear()


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
        
    await message.answer(
        "Какую привычку ты сегодня выполнил? Выбери из списка на клавиатуре:", 
        reply_markup=habits_kb(habits)
    )
    await state.set_state(LogHabit.waiting_for_habit_name)

@dp.message(LogHabit.waiting_for_habit_name)
async def log_habit_name(message: Message, state: FSMContext):
    habit_name = message.text
    user_id = message.from_user.id
    
    habits = get_habits(user_id)
    if habit_name not in habits:
        await message.answer("Такой привычки нет в твоем списке. Выбери из меню или нажми «Отмена».")
        return
        
    if check_habit_logged_today(user_id, habit_name):
        await message.answer(
            f"Ты уже отмечал привычку «{habit_name}» сегодня! Возвращайся завтра 😉", 
            reply_markup=main_kb
        )
        await state.clear()
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