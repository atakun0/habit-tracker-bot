import csv
import os
from aiogram.types import FSInputFile
import asyncio
import logging
import random
from dotenv import load_dotenv
from middlewares import AntiSpamMiddleware
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import Message, BotCommand
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.session.aiohttp import AiohttpSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db import init_db, add_habit, get_habits, delete_habit, log_habit, get_habit_stats, check_habit_logged_today, get_habit_streak, get_all_users, rename_habit, get_all_logs
from keyboards import main_kb, cancel_kb, habits_kb

class LogHabit(StatesGroup):
    waiting_for_habit_name = State()

class AddHabit(StatesGroup):
    waiting_for_name = State()

class EditHabit(StatesGroup):
    waiting_for_old_name = State()
    waiting_for_new_name = State()

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
dp.message.middleware(AntiSpamMiddleware(limit_seconds=0.5))


class AddHabit(StatesGroup):
    waiting_for_name = State()

@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext):
    await state.clear() 
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

@dp.message(StateFilter(None), F.text == "✏️ Изменить")
async def edit_habit_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    habits = get_habits(user_id)
    
    if not habits:
        await message.answer("У тебя пока нет привычек для изменения.")
        return
        
    await message.answer(
        "Какую привычку хочешь переименовать?",
        reply_markup=habits_kb(habits)
    )
    await state.set_state(EditHabit.waiting_for_old_name)

@dp.message(EditHabit.waiting_for_old_name)
async def edit_habit_old_name(message: Message, state: FSMContext):
    habit_name = message.text
    user_id = message.from_user.id
    
    if habit_name not in get_habits(user_id):
        await message.answer("Такой привычки нет. Выбери из меню или нажми «Отмена».")
        return
        
    await state.update_data(old_name=habit_name)
    await message.answer("Введи новое название для этой привычки:", reply_markup=cancel_kb)
    await state.set_state(EditHabit.waiting_for_new_name)

@dp.message(EditHabit.waiting_for_new_name)
async def edit_habit_new_name(message: Message, state: FSMContext):
    new_name = message.text
    user_id = message.from_user.id
    
    data = await state.get_data()
    old_name = data['old_name']
    
    rename_habit(user_id, old_name, new_name)
    
    await message.answer(
        f"Готово! Привычка «{old_name}» переименована в «{new_name}».", 
        reply_markup=main_kb
    )
    await state.clear()

@dp.message(StateFilter(None), F.text == "❓ Помощь")
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

@dp.message(StateFilter(None), F.text == "➕ Добавить привычку")
async def add_habit_start(message: Message, state: FSMContext):
    await message.answer("Отлично! Напиши название новой привычки:", reply_markup=cancel_kb)
    await state.set_state(AddHabit.waiting_for_name)

@dp.message(AddHabit.waiting_for_name)
async def add_habit_name(message: Message, state: FSMContext):
    habit_name = message.text
    user_id = message.from_user.id
    
    add_habit(user_id, habit_name)
    
    await message.answer(f"Супер! Привычка «{habit_name}» успешно добавлена и сохранена в базу!", reply_markup=main_kb)
    await state.clear()

@dp.message(StateFilter(None), F.text == "📊 Статистика")
async def show_statistics_handler(message: Message):
    user_id = message.from_user.id
    stats = get_habit_stats(user_id)
    
    if not stats:
        await message.answer("У тебя пока нет отметок о выполнении привычек. Сделай хотя бы одну!")
        return
        
    response = "📊 <b>Твоя статистика выполнений:</b>\n\n"
    for habit_name, count in stats:
        streak = get_habit_streak(user_id, habit_name)
        streak_text = f" (🔥 {streak} дней подряд)" if streak > 1 else ""
        response += f"🔹 <b>{habit_name}</b>: {count} раз(а){streak_text}\n"
        
    await message.answer(response)

@dp.message(StateFilter(None), F.text == "📋 Мои привычки")
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

@dp.message(StateFilter(None), F.text == "🗑 Удалить привычку")
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

@dp.message(StateFilter(None), F.text == "✅ Отметить выполнение")
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
    phrases = [
        "Так держать! Продолжай в том же духе 🔥",
        "Маленькие шаги ведут к большим результатам 🚀",
        "Горжусь тобой! Одна галочка — один шаг к цели 🎯",
        "Отличная работа! Не сбавляй темп 💪",
        "Твоя дисциплина восхищает! ✨"
    ]
    motivation = random.choice(phrases)
    
    await message.answer(
        f"✅ Привычка «<b>{habit_name}</b>» выполнена!\n\n<i>{motivation}</i>", 
        reply_markup=main_kb
    )
    await state.clear()

async def send_daily_reminders():
    users = get_all_users()
    for user_id in users:
        habits = get_habits(user_id)
        if not habits:
            continue
            
        pending = [h for h in habits if not check_habit_logged_today(user_id, h)]
        
        if pending:
            await bot.send_message(
                user_id, 
                "Эй! Ты еще не выполнил все свои привычки на сегодня. Самое время это исправить! 👇",
                reply_markup=main_kb
            )

@dp.message(StateFilter(None), F.text == "📁 Экспорт данных")
async def export_data_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    
    if not logs:
        await message.answer("У тебя пока нет истории выполнений для экспорта. Отметь хотя бы одну привычку!")
        return
        
    filename = f"habits_export_{user_id}.csv"
    with open(filename, mode='w', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerow(["Привычка", "Дата выполнения"]) # Заголовки столбцов
        for row in logs:
            writer.writerow(row)
            
    document = FSInputFile(filename)
    await message.answer_document(document, caption="Твои данные готовы для анализа! 📊")
    
    os.remove(filename)

async def main():
    init_db()
    logger.info("Бот успешно запущен и готов к работе!")
    
    await set_default_commands(bot)
    
    scheduler = AsyncIOScheduler(timezone='Europe/Moscow')
    scheduler.add_job(send_daily_reminders, trigger='cron', hour=20, minute=0)
    scheduler.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())