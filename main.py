import asyncio
import logging
import math
import os
import random
from logging.handlers import RotatingFileHandler

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    ErrorEvent,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from db import (
    add_habit,
    check_habit_logged_today,
    delete_habit,
    get_all_logs,
    get_all_users,
    get_habit_stats,
    get_habit_streak,
    get_habits,
    init_db,
    log_habit,
    rename_habit,
    undo_habit_log,
)
from keyboards import cancel_kb, habits_kb, main_kb
from middlewares import AntiSpamMiddleware

# ==========================================
# 1. КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# ==========================================
logging.getLogger().handlers.clear()

file_handler = RotatingFileHandler(
    "bot_activity.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
)
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
console_handler.setLevel(logging.INFO)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)
logger.info("Система логирования успешно инициализирована.")

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
PROXY_URL = os.getenv("PROXY_URL")
TARGET_DAYS = 21  # Глобальная цель для формирования привычки

session = AiohttpSession(proxy=PROXY_URL)
bot = Bot(
    token=TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()
dp.message.middleware(AntiSpamMiddleware(limit_seconds=0.5))


# ==========================================
# 2. СОСТОЯНИЯ (FSM)
# ==========================================
class LogHabit(StatesGroup):
    waiting_for_habit_name = State()


class AddHabit(StatesGroup):
    waiting_for_name = State()


class EditHabit(StatesGroup):
    waiting_for_old_name = State()
    waiting_for_new_name = State()


class DeleteHabit(StatesGroup):
    waiting_for_habit_name = State()


# ==========================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И РАССЫЛКИ
# ==========================================
def get_logs_df(user_id: int, normalize: bool = False) -> pd.DataFrame | None:
    """Возвращает очищенный DataFrame с логами пользователя или None, если логов нет."""
    logs = get_all_logs(user_id)
    if not logs:
        return None
    df = pd.DataFrame(logs, columns=["Привычка", "Дата"])
    df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce")
    df = df.dropna(subset=["Дата"])
    if df.empty:
        return None
    if normalize:
        df["Дата"] = df["Дата"].dt.normalize()
    return df


def get_streak_emoji(streak: int) -> str:
    if streak == 0:
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
    percent = min(current / target, 1.0) if target > 0 else 0.0
    filled_blocks = int(percent * 10)
    return "█" * filled_blocks + "░" * (10 - filled_blocks)


async def set_default_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="help", description="Справка по боту"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
        # Базовая аналитика
        BotCommand(command="insights", description="Самый продуктивный день"),
        BotCommand(command="trend", description="Тренд продуктивности (WoW)"),
        BotCommand(command="winrate", description="Процент успеха привычек"),
        BotCommand(command="dist", description="Распределение активности"),
        # Продвинутые графики и матрицы
        BotCommand(command="matrix", description="Синергия привычек"),
        BotCommand(command="growth", description="График кумулятивного роста"),
        BotCommand(command="rolling", description="Сглаженный тренд (SMA)"),
        BotCommand(command="audit", description="Аудит заброшенных привычек"),
        BotCommand(command="balance", description="Радар баланса"),
        BotCommand(command="heatmap", description="Карта активности (как в GitHub)"),
        BotCommand(command="pie", description="Доля каждой привычки (Pie Chart)"),
        BotCommand(command="profile", description="Профиль и уровень"),
        BotCommand(command="export", description="Выгрузить данные в Excel"),
        BotCommand(command="streaks", description="Мои стрики и рекорды"),
    ]
    await bot.set_my_commands(commands)


async def send_morning_greeting():
    for user_id in get_all_users():
        habits = get_habits(user_id)
        if not habits:
            continue

        habit_list = "\n".join([f"🔹 {h}" for h in habits])
        try:
            await bot.send_message(
                user_id,
                f"🌅 Доброе утро! Твой план привычек на сегодня:\n\n"
                f"{habit_list}\n\n"
                f"Удачного дня на парах!",
                reply_markup=main_kb,
            )
        except Exception as e:
            logger.error(f"Не удалось отправить утреннее сообщение пользователю {user_id}: {e}")


async def send_daily_reminders():
    for user_id in get_all_users():
        habits = get_habits(user_id)
        if not habits:
            continue

        pending = [h for h in habits if not check_habit_logged_today(user_id, h)]
        if not pending:
            continue

        pending_list = "\n".join([f"🔸 {h}" for h in pending])
        try:
            await bot.send_message(
                user_id,
                f"Вечерняя сводка. До конца дня осталось выполнить:\n\n"
                f"{pending_list}\n\n"
                f"Не забудь отметить прогресс через меню.",
                reply_markup=main_kb,
            )
        except Exception as e:
            logger.error(f"Не удалось отправить вечернее напоминание пользователю {user_id}: {e}")


# ==========================================
# 4. БАЗОВЫЕ КОМАНДЫ (START, HELP, CANCEL, ADMIN, BACKUP)
# ==========================================
@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я твой трекер привычек. Выбери действие ниже 👇",
        reply_markup=main_kb,
    )


@dp.message(Command("help"))
@dp.message(StateFilter(None), F.text == "❓ Помощь")
async def command_help_handler(message: Message):
    help_text = (
        "🤖 <b>Как пользоваться трекером:</b>\n\n"
        "➕ <b>Добавить привычку</b> — создать новую привычку для отслеживания.\n"
        "✅ <b>Отметить выполнение</b> — записать прогресс на сегодня.\n"
        "📋 <b>Мои привычки</b> — посмотреть весь список твоих целей.\n"
        "📊 <b>Статистика</b> — узнать, сколько раз была выполнена каждая привычка.\n"
        "🗑 <b>Удалить привычку</b> — убрать неактуальную цель.\n\n"
        "<i>💡 Если бот ждет от тебя ввода, а ты передумал — просто нажми кнопку «Отмена» или напиши команду /cancel.</i>"
    )
    await message.answer(help_text)


@dp.message(Command("cancel"))
@dp.message(F.text.lower() == "отмена")
async def cancel_handler(message: Message, state: FSMContext):
    if await state.get_state() is None:
        return
    await state.clear()
    await message.answer(
        "Действие отменено. Можешь продолжать работу с меню.",
        reply_markup=main_kb,
    )


@dp.message(Command("admin"))
async def admin_panel_handler(message: Message):
    users = get_all_users()
    await message.answer(
        f"🔧 <b>Панель администратора</b>\n\n"
        f"👥 Всего пользователей в базе: <b>{len(users)}</b>"
    )


@dp.message(Command("backup"))
async def backup_database_handler(message: Message):
    try:
        db_file = FSInputFile("habits.db")
        await message.answer_document(
            db_file,
            caption="📦 Резервная копия базы данных.\nСырые данные готовы к аналитике!",
        )
    except Exception as e:
        logger.error(f"Ошибка выгрузки бэкапа: {e}")
        await message.answer("Не удалось сформировать бэкап.")


# ==========================================
# 5. ОСНОВНОЙ ФУНКЦИОНАЛ (CRUD ПРИВЫЧЕК И ОТМЕТКИ)
# ==========================================
@dp.message(StateFilter(None), F.text == "➕ Добавить привычку")
async def add_habit_start(message: Message, state: FSMContext):
    await message.answer(
        "Отлично! Напиши название новой привычки:", reply_markup=cancel_kb
    )
    await state.set_state(AddHabit.waiting_for_name)


@dp.message(AddHabit.waiting_for_name)
async def add_habit_name(message: Message, state: FSMContext):
    habit_name = message.text
    add_habit(message.from_user.id, habit_name)
    await message.answer(
        f"Супер! Привычка «{habit_name}» успешно добавлена и сохранена в базу!",
        reply_markup=main_kb,
    )
    await state.clear()


@dp.message(StateFilter(None), F.text == "✅ Отметить выполнение")
async def log_habit_start(message: Message, state: FSMContext):
    habits = get_habits(message.from_user.id)
    if not habits:
        await message.answer("У тебя пока нет добавленных привычек. Сначала добавь их!")
        return
    await message.answer(
        "Какую привычку ты сегодня выполнил? Выбери из списка на клавиатуре:",
        reply_markup=habits_kb(habits),
    )
    await state.set_state(LogHabit.waiting_for_habit_name)


@dp.message(LogHabit.waiting_for_habit_name)
async def log_habit_name(message: Message, state: FSMContext):
    habit_name = message.text
    user_id = message.from_user.id
    habits = get_habits(user_id)

    if habit_name not in habits:
        await message.answer(
            "Такой привычки нет в твоем списке. Выбери из меню или нажми «Отмена»."
        )
        return

    if check_habit_logged_today(user_id, habit_name):
        await message.answer(
            f"Ты уже отмечал привычку «{habit_name}» сегодня! Возвращайся завтра 😉",
            reply_markup=main_kb,
        )
        await state.clear()
        return

    log_habit(user_id, habit_name)
    phrases = [
        "Так держать! Продолжай в том же духе 🔥",
        "Маленькие шаги ведут к большим результатам 🚀",
        "Горжусь тобой! Одна галочка — один шаг к цели 🎯",
        "Отличная работа! Не сбавляй темп 💪",
        "Твоя дисциплина восхищает! ✨",
    ]
    undo_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Отменить", callback_data=f"undo_{habit_name}")]
        ]
    )
    await message.answer(
        f"✅ Привычка «<b>{habit_name}</b>» выполнена!\n\n<i>{random.choice(phrases)}</i>",
        reply_markup=undo_kb,
    )
    await state.clear()


@dp.callback_query(F.data.startswith("undo_"))
async def undo_callback_handler(callback: CallbackQuery):
    habit_name = callback.data.split("undo_", 1)[1]
    undo_habit_log(callback.from_user.id, habit_name)
    await callback.message.edit_text(
        f"❌ Отметка для привычки «<b>{habit_name}</b>» отменена."
    )
    await callback.answer("Действие отменено")


@dp.message(StateFilter(None), F.text == "✏️ Изменить")
async def edit_habit_start(message: Message, state: FSMContext):
    habits = get_habits(message.from_user.id)
    if not habits:
        await message.answer("У тебя пока нет привычек для изменения.")
        return
    await message.answer(
        "Какую привычку хочешь переименовать?", reply_markup=habits_kb(habits)
    )
    await state.set_state(EditHabit.waiting_for_old_name)


@dp.message(EditHabit.waiting_for_old_name)
async def edit_habit_old_name(message: Message, state: FSMContext):
    habit_name = message.text
    if habit_name not in get_habits(message.from_user.id):
        await message.answer("Такой привычки нет. Выбери из меню или нажми «Отмена».")
        return
    await state.update_data(old_name=habit_name)
    await message.answer(
        "Введи новое название для этой привычки:", reply_markup=cancel_kb
    )
    await state.set_state(EditHabit.waiting_for_new_name)


@dp.message(EditHabit.waiting_for_new_name)
async def edit_habit_new_name(message: Message, state: FSMContext):
    new_name = message.text
    data = await state.get_data()
    old_name = data["old_name"]
    rename_habit(message.from_user.id, old_name, new_name)
    await message.answer(
        f"Готово! Привычка «{old_name}» переименована в «{new_name}».",
        reply_markup=main_kb,
    )
    await state.clear()


@dp.message(StateFilter(None), F.text == "🗑 Удалить привычку")
async def delete_habit_start(message: Message, state: FSMContext):
    habits = get_habits(message.from_user.id)
    if not habits:
        await message.answer("У тебя пока нет привычек, нечего удалять!")
        return
    await message.answer(
        "Выбери привычку, которую хочешь удалить, на клавиатуре ниже:",
        reply_markup=habits_kb(habits),
    )
    await state.set_state(DeleteHabit.waiting_for_habit_name)


@dp.message(DeleteHabit.waiting_for_habit_name)
async def delete_habit_name(message: Message, state: FSMContext):
    habit_name = message.text
    user_id = message.from_user.id
    if habit_name not in get_habits(user_id):
        await message.answer(
            "Такой привычки нет в твоем списке. Выбери из меню или нажми «Отмена»."
        )
        return
    delete_habit(user_id, habit_name)
    await message.answer(
        f"Привычка «{habit_name}» успешно удалена 🗑", reply_markup=main_kb
    )
    await state.clear()


# ==========================================
# 6. СТАТИСТИКА, ПРОФИЛЬ И ЭКСПОРТ
# ==========================================
@dp.message(StateFilter(None), F.text == "📋 Мои привычки")
async def show_habits_handler(message: Message):
    user_id = message.from_user.id
    habits = get_habits(user_id)
    if not habits:
        await message.answer(
            "У тебя пока нет добавленных привычек. Нажми «➕ Добавить привычку», чтобы начать!"
        )
        return
    response = "Твои привычки и статус на сегодня:\n\n"
    for i, habit in enumerate(habits, start=1):
        status_emoji = "✅" if check_habit_logged_today(user_id, habit) else "❌"
        response += f"{i}. {habit} {status_emoji}\n"
    await message.answer(response)


@dp.message(StateFilter(None), F.text == "📝 Итоги дня")
async def daily_summary_handler(message: Message):
    user_id = message.from_user.id
    habits = get_habits(user_id)
    if not habits:
        await message.answer("У тебя пока нет привычек. Самое время добавить первую!")
        return

    done = [h for h in habits if check_habit_logged_today(user_id, h)]
    pending = [h for h in habits if h not in done]

    response = "📝 <b>Твои итоги на сегодня:</b>\n\n"
    if done:
        response += "<b>✅ Выполнено:</b>\n" + "".join([f" — {h}\n" for h in done]) + "\n"
    if pending:
        response += "<b>❌ Осталось сделать:</b>\n" + "".join([f" — {h}\n" for h in pending])
    else:
        response += "🎉 <b>Все привычки на сегодня закрыты! Можно смело отдыхать.</b>"
    await message.answer(response)


@dp.message(StateFilter(None), F.text == "📊 Статистика")
async def show_statistics_handler(message: Message):
    user_id = message.from_user.id
    stats = get_habit_stats(user_id)
    if not stats:
        await message.answer(
            "У тебя пока нет отметок о выполнении привычек. Сделай хотя бы одну!"
        )
        return

    response = f"📊 <b>Твоя статистика выполнений (цель: {TARGET_DAYS} дней):</b>\n\n"
    for habit_name, count in stats:
        streak = get_habit_streak(user_id, habit_name)
        emoji = get_streak_emoji(streak)
        streak_text = (
            f" ({emoji} {streak} дней подряд)"
            if streak > 0
            else " (🧊 нет активной серии)"
        )
        progress_bar = make_progress_bar(count)
        response += f"🔹 <b>{habit_name}</b>: {count}/{TARGET_DAYS}\n"
        response += f"<code>[{progress_bar}]</code>{streak_text}\n\n"
    await message.answer(response)


@dp.message(StateFilter(None), F.text == "🏆 Рекорды")
async def records_handler(message: Message):
    user_id = message.from_user.id
    stats = get_habit_stats(user_id)
    if not stats:
        await message.answer(
            "У тебя пока нет данных для рекордов. Отметь хотя бы одну привычку!"
        )
        return

    most_completed = max(stats, key=lambda x: x[1])
    best_streak_habit = None
    max_streak = 0
    for h in get_habits(user_id):
        streak = get_habit_streak(user_id, h)
        if streak > max_streak:
            max_streak = streak
            best_streak_habit = h

    response = "🏆 <b>Твои рекорды:</b>\n\n"
    response += f"🥇 <b>Самая частая:</b> «{most_completed[0]}» ({most_completed[1]} выполнений)\n"
    if max_streak > 0:
        response += f"🔥 <b>Лучший стрик:</b> «{best_streak_habit}» ({max_streak} дней подряд)\n"
    else:
        response += "🧊 <b>Лучший стрик:</b> Пока нет активных серий. Самое время начать!"
    await message.answer(response)


@dp.message(Command("profile"))
@dp.message(StateFilter(None), F.text == "👤 Мой профиль")
async def user_profile_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    habits = get_habits(user_id)
    total_completed = len(logs)
    active_habits = len(habits) if habits else 0

    if total_completed == 0:
        await message.answer(
            "У тебя пока нет опыта. Отметь первую привычку, чтобы получить 1 уровень!"
        )
        return

    current_level = math.floor(math.sqrt(total_completed))
    level_start_xp = current_level**2
    next_level_xp = (current_level + 1) ** 2

    xp_in_level = total_completed - level_start_xp
    xp_needed = next_level_xp - level_start_xp
    bar = make_progress_bar(xp_in_level, xp_needed)
    tasks_left = next_level_xp - total_completed

    if current_level < 3:
        rank = "Искатель 🔍"
    elif current_level < 5:
        rank = "Адепт рутины 🧘‍♂️"
    elif current_level < 8:
        rank = "Мастер привычек 🥷"
    else:
        rank = "Легенда 👑"

    await message.answer(
        f"👤 <b>Твой профиль:</b>\n\n"
        f"🏆 <b>Уровень: {current_level}</b> (<i>{rank}</i>)\n"
        f"Опыт: <code>[{bar}]</code> {xp_in_level}/{xp_needed}\n"
        f"<i>(До {current_level + 1} уровня осталось {tasks_left} выполнений)</i>\n\n"
        f"📊 <b>Сводка:</b>\n"
        f"Всего выполнено задач: <b>{total_completed}</b>\n"
        f"Активных привычек: <b>{active_habits}</b>"
    )


@dp.message(Command("export"))
@dp.message(StateFilter(None), F.text == "📁 Экспорт данных")
async def export_excel_handler(message: Message):
    user_id = message.from_user.id
    df = get_logs_df(user_id)
    if df is None:
        await message.answer("У тебя пока нет данных для экспорта.")
        return

    df = df.sort_values(by="Дата", ascending=False)
    df["Дата"] = df["Дата"].dt.strftime("%Y-%m-%d %H:%M:%S")
    filename = f"habit_backup_{user_id}.xlsx"
    df.to_excel(filename, index=False, engine="openpyxl")

    doc = FSInputFile(filename)
    await message.answer_document(
        doc,
        caption="📁 <b>Твой датасет готов!</b>\nВсе логи выгружены в Excel.",
    )
    os.remove(filename)


# ==========================================
# 7. ПРОДВИНУТАЯ АНАЛИТИКА И ГРАФИКИ
# ==========================================
@dp.message(Command("insights"))
async def data_insights_handler(message: Message):
    df = get_logs_df(message.from_user.id)
    if df is None:
        await message.answer("У тебя пока нет истории выполнений для поиска инсайтов.")
        return

    day_counts = df["Дата"].dt.dayofweek.value_counts()
    best_day_index = day_counts.idxmax()
    days_ru = {
        0: "Понедельник", 1: "Вторник", 2: "Среда",
        3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье",
    }
    best_day = days_ru.get(best_day_index, "Неизвестно")
    await message.answer(
        f"🧠 <b>Твои дата-инсайты (powered by pandas):</b>\n\n"
        f"Твой самый продуктивный день недели — <b>{best_day}</b> "
        f"({day_counts.max()} выполнений за всё время).\n\n"
        f"<i>💡 Совет: планируй самые ресурсоемкие задачи именно на этот день!</i>"
    )


@dp.message(Command("trend"))
async def productivity_trend_handler(message: Message):
    df = get_logs_df(message.from_user.id)
    if df is None:
        await message.answer("Мало данных для анализа трендов. Продолжай отмечать привычки!")
        return

    now = pd.Timestamp.now()
    this_week = len(df[(df["Дата"] >= now - pd.Timedelta(days=7)) & (df["Дата"] <= now)])
    last_week = len(
        df[(df["Дата"] >= now - pd.Timedelta(days=14)) & (df["Дата"] < now - pd.Timedelta(days=7))]
    )

    if last_week == 0:
        await message.answer(
            f"📈 <b>Твоя продуктивность:</b>\n"
            f"За последние 7 дней выполнено: <b>{this_week}</b>.\n"
            f"<i>Данных за прошлую неделю пока нет для сравнения!</i>"
        )
        return

    diff = this_week - last_week
    percent = (diff / last_week) * 100
    if diff > 0:
        trend_text = f"🟢 Рост на {percent:.1f}% (+{diff} выполнений)"
    elif diff < 0:
        trend_text = f"🔴 Спад на {abs(percent):.1f}% ({diff} выполнений)"
    else:
        trend_text = "⚪️ Стабильность (без изменений)"

    await message.answer(
        f"📈 <b>Твой тренд продуктивности (WoW):</b>\n\n"
        f"Текущие 7 дней: <b>{this_week}</b>\n"
        f"Прошлые 7 дней: <b>{last_week}</b>\n"
        f"Динамика: {trend_text}"
    )


@dp.message(Command("winrate"))
async def winrate_handler(message: Message):
    df = get_logs_df(message.from_user.id, normalize=True)
    if df is None:
        await message.answer("Мало данных для расчета Win Rate. Сделай пару отметок!")
        return

    now = pd.Timestamp.now().normalize()
    response = "🎯 <b>Твой Win Rate (Процент успеха):</b>\n\n"
    for habit, group in df.groupby("Привычка"):
        first_date = group["Дата"].min()
        total_days = (now - first_date).days + 1
        completed_days = group["Дата"].nunique()
        win_rate = (completed_days / total_days) * 100

        indicator = "🟢" if win_rate >= 80 else ("🟡" if win_rate >= 50 else "🔴")
        response += f"{indicator} <b>{habit}</b>: {win_rate:.1f}%\n"
        response += f"└ <i>Выполнено {completed_days} из {total_days} дн.</i>\n\n"
    await message.answer(response)


@dp.message(Command("dist"))
async def distribution_handler(message: Message):
    df = get_logs_df(message.from_user.id)
    if df is None:
        await message.answer("Мало данных для расчета распределения.")
        return

    dist = df["Дата"].dt.dayofweek.value_counts(normalize=True) * 100
    days_ru = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
    response = "📊 <b>Нагрузка по дням недели:</b>\n\n"
    for day_num in range(7):
        percent = dist.get(day_num, 0.0)
        blocks = int(percent / 10)
        bar = "█" * blocks + "░" * (10 - blocks)
        response += f"<b>{days_ru[day_num]}</b>: <code>[{bar}]</code> {percent:.1f}%\n"
    await message.answer(response)


@dp.message(Command("streaks"))
async def streaks_handler(message: Message):
    df = get_logs_df(message.from_user.id, normalize=True)
    if df is None:
        await message.answer("Пока нет данных для расчета серий.")
        return

    df = df.drop_duplicates(subset=["Привычка", "Дата"]).sort_values(by=["Привычка", "Дата"])
    df["Diff"] = df.groupby("Привычка")["Дата"].diff().dt.days
    df["Streak_ID"] = (df["Diff"] != 1).cumsum()

    streak_lengths = df.groupby(["Привычка", "Streak_ID"]).size().reset_index(name="Длина")
    max_streaks = streak_lengths.groupby("Привычка")["Длина"].max().to_dict()
    yesterday = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
    last_dates = df.groupby("Привычка")["Дата"].max()

    response = "🔥 <b>Твои серии (дней подряд):</b>\n\n"
    for habit, max_len in max_streaks.items():
        if last_dates.get(habit) >= yesterday:
            current_streak_id = df[df["Привычка"] == habit]["Streak_ID"].iloc[-1]
            current_len = streak_lengths[
                (streak_lengths["Привычка"] == habit)
                & (streak_lengths["Streak_ID"] == current_streak_id)
            ]["Длина"].values[0]
        else:
            current_len = 0

        fire_emoji = "🔥" * min(current_len, 5) if current_len > 0 else "❄️"
        response += f"<b>{habit}</b> {fire_emoji}\n"
        response += f"Текущая серия: <b>{current_len}</b> дн.\n"
        response += f"Абсолютный рекорд: <b>{max_len}</b> дн.\n\n"
    await message.answer(response)


@dp.message(Command("audit"))
async def habit_audit_handler(message: Message):
    user_id = message.from_user.id
    habits = get_habits(user_id)
    if not habits:
        await message.answer("У тебя пока нет привычек для аудита.")
        return

    df = get_logs_df(user_id, normalize=True)
    response = "🧹 <b>Аудит твоих привычек:</b>\n\n"
    if df is None:
        await message.answer(response + "Ты еще ничего не отмечал. Все привычки ждут первого шага!")
        return

    now = pd.Timestamp.now().normalize()
    last_logs = df.groupby("Привычка")["Дата"].max()
    zombies, active = [], []

    for h in habits:
        if h in last_logs:
            days_offline = (now - last_logs[h]).days
            if days_offline > 7:
                zombies.append((h, days_offline))
            else:
                active.append(h)
        else:
            zombies.append((h, "никогда"))

    if zombies:
        response += "⚠️ <b>В зоне риска (без активности > 7 дней):</b>\n"
        for h, days in zombies:
            detail = "еще ни одной отметки" if days == "никогда" else f"простой: {days} дн."
            response += f" — <b>{h}</b> ({detail})\n"
        response += "\n<i>💡 Совет: удали неактуальные цели через «🗑 Удалить привычку».</i>\n\n"
    else:
        response += "🌟 <b>Идеальная дисциплина!</b> У тебя нет заброшенных привычек.\n\n"

    response += f"✅ Активных привычек: <b>{len(active)}</b> из <b>{len(habits)}</b>"
    await message.answer(response)


@dp.message(Command("matrix"))
async def correlation_matrix_handler(message: Message):
    df = get_logs_df(message.from_user.id, normalize=True)
    if df is None:
        await message.answer("Нет данных для анализа. Отметь хотя бы пару привычек!")
        return

    df = df.drop_duplicates()
    df["Выполнено"] = 1
    pivot = df.pivot_table(index="Дата", columns="Привычка", values="Выполнено", fill_value=0)
    if len(pivot.columns) < 2:
        await message.answer("Для поиска связей нужно вести хотя бы 2 разные привычки!")
        return

    corr_matrix = pivot.corr()
    pairs = []
    cols = corr_matrix.columns
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            val = corr_matrix.iloc[i, j]
            if pd.notna(val):
                pairs.append((cols[i], cols[j], val))
    pairs.sort(key=lambda x: x[2], reverse=True)

    response = "🔗 <b>Связи между твоими привычками:</b>\n\n"
    for h1, h2, corr in pairs:
        icon = "🟢 Синергия" if corr > 0.3 else ("🔴 Конфликт" if corr < -0.3 else "⚪️ Независимы")
        response += f"<b>{h1}</b> ↔️ <b>{h2}</b>\n└ {icon} (Корреляция: {corr:.2f})\n\n"
    await message.answer(response)


@dp.message(Command("heatmap"))
async def heatmap_handler(message: Message):
    df = get_logs_df(message.from_user.id, normalize=True)
    if df is None:
        await message.answer("Пока нет данных для тепловой карты. Сделай пару отметок!")
        return

    now = pd.Timestamp.now().normalize()
    all_days = pd.date_range(start=now - pd.Timedelta(days=27), end=now)
    heatmap_data = df.groupby("Дата").size().reindex(all_days, fill_value=0)

    response = "🗺 <b>Тепловая карта продуктивности (28 дней):</b>\n\n"
    for i in range(0, 28, 7):
        row = ""
        for val in heatmap_data[i : i + 7]:
            row += "⬜️" if val == 0 else ("🟨" if val == 1 else ("🟧" if val == 2 else "🟩"))
        response += row + "\n"
    response += "\n<i>Легенда: ⬜️ 0 | 🟨 1 | 🟧 2 | 🟩 3+ выполнений в день</i>"
    await message.answer(response)


@dp.message(StateFilter(None), F.text == "📈 График")
async def send_chart_handler(message: Message):
    user_id = message.from_user.id
    stats = get_habit_stats(user_id)
    if not stats:
        await message.answer("У тебя пока нет данных для построения графика.")
        return

    habits = [s[0] for s in stats]
    counts = [s[1] for s in stats]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.bar(habits, counts, color="#5c9ded")
    ax1.set_title("Прогресс выполнения (в днях)")
    ax1.set_ylabel("Количество дней")
    ax1.tick_params(axis="x", rotation=45)

    if sum(counts) > 0:
        ax2.pie(counts, labels=habits, autopct="%1.1f%%", startangle=90, colors=plt.cm.Paired.colors)
        ax2.set_title("Доля привычек")
    else:
        ax2.text(0.5, 0.5, "Пока нет выполнений", ha="center", va="center")
        ax2.axis("off")

    plt.tight_layout()
    filename = f"chart_{user_id}.png"
    plt.savefig(filename)
    plt.close()

    await message.answer_photo(FSInputFile(filename), caption="Твои данные в виде графика! 📊")
    os.remove(filename)


@dp.message(Command("growth"))
async def growth_chart_handler(message: Message):
    user_id = message.from_user.id
    df = get_logs_df(user_id, normalize=True)
    if df is None:
        await message.answer("Пока нет данных для построения графика роста.")
        return

    daily = df.groupby("Дата").size().reset_index(name="Количество")
    daily["Кумулятивно"] = daily["Количество"].cumsum()

    plt.figure(figsize=(10, 5))
    plt.plot(daily["Дата"], daily["Кумулятивно"], marker="o", color="#2ecc71", linewidth=2, markersize=6)
    plt.title("Кумулятивный рост выполненных привычек", fontsize=14)
    plt.xlabel("Дата", fontsize=12)
    plt.ylabel("Всего выполнений", fontsize=12)
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.xticks(rotation=45)
    plt.tight_layout()

    filename = f"growth_{user_id}.png"
    plt.savefig(filename)
    plt.close()

    await message.answer_photo(
        FSInputFile(filename),
        caption="📈 <b>Твой долгосрочный прогресс!</b>\nГрафик кумулятивного роста.",
    )
    os.remove(filename)


@dp.message(Command("rolling"))
async def rolling_average_handler(message: Message):
    user_id = message.from_user.id
    df = get_logs_df(user_id, normalize=True)
    if df is None:
        await message.answer("Пока нет данных для построения графика.")
        return

    daily_counts = df.groupby("Дата").size()
    all_days = pd.date_range(start=daily_counts.index.min(), end=pd.Timestamp.now().normalize())
    daily = daily_counts.reindex(all_days, fill_value=0).reset_index()
    daily.columns = ["Дата", "Количество"]
    daily["SMA_7"] = daily["Количество"].rolling(window=7, min_periods=1).mean()

    plt.figure(figsize=(10, 5))
    plt.bar(daily["Дата"], daily["Количество"], color="#bdc3c7", alpha=0.6, label="Факт")
    plt.plot(daily["Дата"], daily["SMA_7"], color="#e74c3c", linewidth=3, label="Тренд (SMA-7)")
    plt.title("Тренд продуктивности (Скользящая средняя за 7 дней)", fontsize=14)
    plt.xlabel("Дата", fontsize=12)
    plt.ylabel("Выполнено привычек", fontsize=12)
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.xticks(rotation=45)
    plt.tight_layout()

    filename = f"rolling_{user_id}.png"
    plt.savefig(filename)
    plt.close()

    await message.answer_photo(
        FSInputFile(filename),
        caption="📉 <b>Твой сглаженный тренд!</b>\nКрасная линия показывает реальную динамику без учета дневных скачков.",
    )
    os.remove(filename)


@dp.message(Command("balance"))
async def balance_radar_handler(message: Message):
    user_id = message.from_user.id
    df = get_logs_df(user_id)
    if df is None:
        await message.answer("Пока нет данных для построения радара.")
        return

    counts = df["Привычка"].value_counts()
    if len(counts) < 3:
        await message.answer("Для построения радара баланса нужно вести минимум 3 разные привычки!")
        return

    categories = counts.index.tolist()
    values = counts.values.tolist() + [counts.values[0]]
    angles = [n / float(len(categories)) * 2 * np.pi for n in range(len(categories))]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    ax.plot(angles, values, color="#8e44ad", linewidth=2, linestyle="solid")
    ax.fill(angles, values, color="#8e44ad", alpha=0.3)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=12, fontweight="bold")
    ax.set_yticks([])
    plt.title("Радар баланса привычек", size=16, y=1.1, fontweight="bold")

    filename = f"radar_{user_id}.png"
    plt.savefig(filename, bbox_inches="tight")
    plt.close()

    await message.answer_photo(
        FSInputFile(filename),
        caption="🕸 <b>Твой баланс привычек!</b>\nЧем ровнее фигура, тем гармоничнее твоя рутина.",
    )
    os.remove(filename)


@dp.message(Command("pie"))
async def pie_chart_handler(message: Message):
    user_id = message.from_user.id
    df = get_logs_df(user_id)
    if df is None:
        await message.answer("Пока нет данных для построения графика.")
        return

    counts = df["Привычка"].value_counts()
    plt.figure(figsize=(8, 8))
    plt.pie(
        counts.values,
        labels=counts.index,
        autopct="%1.1f%%",
        startangle=140,
        colors=plt.cm.Set3.colors,
        explode=[0.05] * len(counts),
        textprops={"fontsize": 12, "fontweight": "bold"},
    )
    plt.title("Долевое распределение твоих усилий", fontsize=16, fontweight="bold", y=1.05)
    plt.axis("equal")
    plt.tight_layout()

    filename = f"pie_{user_id}.png"
    plt.savefig(filename, bbox_inches="tight")
    plt.close()

    await message.answer_photo(
        FSInputFile(filename),
        caption="🍩 <b>Твоя круговая диаграмма!</b>\nНаглядно показывает, какие рутины забирают максимум твоего фокуса.",
    )
    os.remove(filename)


# ==========================================
# 8. ОБРАБОТКА ОШИБОК И ЗАПУСК
# ==========================================
@dp.error()
async def global_error_handler(event: ErrorEvent):
    logger.critical(
        "Необработанное исключение при обработке апдейта %s: %s",
        event.update.update_id,
        event.exception,
        exc_info=True,
    )
    try:
        if event.update.message:
            await event.update.message.answer(
                "⚠️ Произошла внутренняя ошибка при обработке команды. Детали записаны в лог."
            )
        elif event.update.callback_query:
            await event.update.callback_query.answer(
                "⚠️ Ошибка при обработке нажатия.", show_alert=True
            )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение об ошибке: {e}")


async def main():
    init_db()
    logger.info("Бот успешно запущен и готов к работе!")

    await set_default_commands(bot)

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_morning_greeting, trigger="cron", hour=8, minute=0)
    scheduler.add_job(send_daily_reminders, trigger="cron", hour=20, minute=0)
    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())