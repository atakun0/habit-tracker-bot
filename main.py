import pandas as pd
import os
import asyncio
import logging
import random
import matplotlib.pyplot as plt
import numpy as np

from aiogram.types import Message, FSInputFile, ErrorEvent, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.session.aiohttp import AiohttpSession

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

import logging
from logging.handlers import RotatingFileHandler

logging.getLogger().handlers.clear()

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')

file_handler = RotatingFileHandler(
    'bot_activity.log', 
    maxBytes=5 * 1024 * 1024, 
    backupCount=3, 
    encoding='utf-8'
)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
console_handler.setLevel(logging.INFO)

# Применяем настройки глобально
logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)

logger.info("Система логирования успешно инициализирована.")

from middlewares import AntiSpamMiddleware
from db import (
    init_db, add_habit, get_habits, delete_habit, log_habit, 
    get_habit_stats, check_habit_logged_today, get_habit_streak, 
    get_all_users, rename_habit, get_all_logs, undo_habit_log
)
from keyboards import main_kb, cancel_kb, habits_kb

# ==========================================
# 1. КОНФИГУРАЦИЯ И НАСТРОЙКИ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
PROXY_URL = os.getenv("PROXY_URL")
TARGET_DAYS = 21  # Глобальная цель для формирования привычки

session = AiohttpSession(proxy=PROXY_URL)
bot = Bot(
    token=TOKEN, 
    session=session, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
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
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def get_streak_emoji(streak: int) -> str:
    if streak == 0: return "🧊"
    elif streak < 3: return "🌱"
    elif streak < 7: return "🌿"
    elif streak < 14: return "🔥"
    elif streak < 21: return "⚡️"
    else: return "👑"

def make_progress_bar(current: int, target: int = TARGET_DAYS) -> str:
    percent = min(current / target, 1.0)
    filled_blocks = int(percent * 10)
    empty_blocks = 10 - filled_blocks
    return "█" * filled_blocks + "░" * empty_blocks

async def set_default_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="help", description="Справка по боту"),
        BotCommand(command="cancel", description="Отменить текущее действие")
    ]
    await bot.set_my_commands(commands)

async def send_morning_greeting():
    users = get_all_users()
    for user_id in users:
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
                reply_markup=main_kb
            )
        except Exception as e:
            logger.error(f"Не удалось отправить утреннее сообщение пользователю {user_id}: {e}")

async def send_daily_reminders():
    users = get_all_users()
    for user_id in users:
        habits = get_habits(user_id)
        if not habits:
            continue
            
        pending = [h for h in habits if not check_habit_logged_today(user_id, h)]
        
        if pending:
            pending_list = "\n".join([f"🔸 {h}" for h in pending])
            
            await bot.send_message(
                user_id, 
                f"Вечернее сводка. До конца дня осталось выполнить:\n\n"
                f"{pending_list}\n\n"
                f"Не забудь отметить прогресс через меню.",
                reply_markup=main_kb
            )

# ==========================================
# 4. БАЗОВЫЕ КОМАНДЫ (START, HELP, CANCEL, ADMIN)
# ==========================================
@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext):
    await state.clear() 
    await message.answer(
        "Привет! Я твой трекер привычек. Выбери действие ниже 👇",
        reply_markup=main_kb
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
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer("Действие отменено. Можешь продолжать работу с меню.", reply_markup=main_kb)

@dp.message(Command("trend"))
async def productivity_trend_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    
    if not logs:
        await message.answer("Мало данных для анализа трендов. Продолжай отмечать привычки!")
        return
        
    df = pd.DataFrame(logs, columns=["Привычка", "Дата"])
    df['Дата'] = pd.to_datetime(df['Дата'], errors='coerce')
    df = df.dropna(subset=['Дата'])
    
    now = pd.Timestamp.now()
    this_week = df[(df['Дата'] >= now - pd.Timedelta(days=7)) & (df['Дата'] <= now)]
    last_week = df[(df['Дата'] >= now - pd.Timedelta(days=14)) & (df['Дата'] < now - pd.Timedelta(days=7))]
    
    this_week_count = len(this_week)
    last_week_count = len(last_week)
    
    if last_week_count == 0:
        await message.answer(
            f"📈 <b>Твоя продуктивность:</b>\n"
            f"За последние 7 дней выполнено: <b>{this_week_count}</b>.\n"
            f"<i>Данных за прошлую неделю пока нет для сравнения!</i>"
        )
        return
        
    diff = this_week_count - last_week_count
    percent = (diff / last_week_count) * 100
    
    if diff > 0:
        trend_text = f"🟢 Рост на {percent:.1f}% (+{diff} выполнений)"
    elif diff < 0:
        trend_text = f"🔴 Спад на {abs(percent):.1f}% ({diff} выполнений)"
    else:
        trend_text = "⚪️ Стабильность (без изменений)"
        
    await message.answer(
        f"📈 <b>Твой тренд продуктивности (WoW):</b>\n\n"
        f"Текущие 7 дней: <b>{this_week_count}</b>\n"
        f"Прошлые 7 дней: <b>{last_week_count}</b>\n"
        f"Динамика: {trend_text}"
    )

@dp.message(Command("dist"))
async def distribution_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    
    if not logs:
        await message.answer("Мало данных для расчета распределения.")
        return
        
    df = pd.DataFrame(logs, columns=["Привычка", "Дата"])
    df['Дата'] = pd.to_datetime(df['Дата'], errors='coerce')
    df = df.dropna(subset=['Дата'])
    
    # Извлекаем день недели и считаем процентное распределение
    df['День_недели'] = df['Дата'].dt.dayofweek
    # normalize=True сразу выдает доли (от 0 до 1), умножаем на 100 для процентов
    dist = df['День_недели'].value_counts(normalize=True) * 100
    
    days_ru = {
        0: 'Пн', 1: 'Вт', 2: 'Ср', 
        3: 'Чт', 4: 'Пт', 5: 'Сб', 6: 'Вс'
    }
    
    response = "📊 <b>Нагрузка по дням недели:</b>\n\n"
    
    # Проходим по всем 7 дням, даже если в какие-то дни активности еще не было
    for day_num in range(7):
        percent = dist.get(day_num, 0.0)
        # 1 блок = 10%
        blocks = int(percent / 10)
        bar = "█" * blocks + "░" * (10 - blocks)
        
        response += f"<b>{days_ru[day_num]}</b>: <code>[{bar}]</code> {percent:.1f}%\n"
        
    await message.answer(response)

@dp.message(Command("winrate"))
async def winrate_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    
    if not logs:
        await message.answer("Мало данных для расчета Win Rate. Сделай пару отметок!")
        return
        
    df = pd.DataFrame(logs, columns=["Привычка", "Дата"])
    df['Дата'] = pd.to_datetime(df['Дата'], errors='coerce')
    df = df.dropna(subset=['Дата'])
    
    now = pd.Timestamp.now().normalize()
    response = "🎯 <b>Твой Win Rate (Процент успеха):</b>\n\n"
    
    for habit, group in df.groupby("Привычка"):
        first_date = group['Дата'].min().normalize()
        total_days_since_start = (now - first_date).days + 1
        completed_days = group['Дата'].nunique() 
        win_rate = (completed_days / total_days_since_start) * 100
        
        if win_rate >= 80:
            indicator = "🟢"
        elif win_rate >= 50:
            indicator = "🟡"
        else:
            indicator = "🔴"
            
        response += f"{indicator} <b>{habit}</b>: {win_rate:.1f}%\n"
        response += f"└ <i>Выполнено {completed_days} из {total_days_since_start} дн.</i>\n\n"
        
    await message.answer(response)

@dp.message(Command("insights"))
async def data_insights_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    if not logs:
        await message.answer("У тебя пока нет истории выполнений для поиска инсайтов.")
        return
    df = pd.DataFrame(logs, columns=["Привычка", "Дата"])
    df['Дата'] = pd.to_datetime(df['Дата'], errors='coerce')
    df = df.dropna(subset=['Дата'])
    df['День_недели'] = df['Дата'].dt.dayofweek
    day_counts = df['День_недели'].value_counts()
    best_day_index = day_counts.idxmax()
    days_ru = {
        0: 'Понедельник', 1: 'Вторник', 2: 'Среда', 
        3: 'Четверг', 4: 'Пятница', 5: 'Суббота', 6: 'Воскресенье'
    }
    best_day = days_ru.get(best_day_index, "Неизвестно")
    total_best_day = day_counts.max()
    response = (
        f"🧠 <b>Твои дата-инсайты (powered by pandas):</b>\n\n"
        f"Твой самый продуктивный день недели — <b>{best_day}</b> "
        f"({total_best_day} выполнений за всё время).\n\n"
        f"<i>💡 Совет: планируй самые ресурсоемкие задачи, вроде математики, именно на этот день!</i>"
    )   
    await message.answer(response)

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
            caption="📦 Резервная копия базы данных.\nСырые данные готовы к аналитике!"
        )
    except Exception as e:
        logger.error(f"Ошибка выгрузки бэкапа: {e}")
        await message.answer("Не удалось сформировать бэкап.")

@dp.message(Command("matrix"))
async def correlation_matrix_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    
    if not logs:
        await message.answer("Нет данных для анализа. Отметь хотя бы пару привычек!")
        return
        
    df = pd.DataFrame(logs, columns=["Привычка", "Дата"])
    df['Дата'] = pd.to_datetime(df['Дата'], errors='coerce').dt.normalize()
    df = df.dropna(subset=['Дата'])
    
    df = df.drop_duplicates()
    
    df['Выполнено'] = 1
    
    pivot = df.pivot_table(index='Дата', columns='Привычка', values='Выполнено', fill_value=0)
    
    if len(pivot.columns) < 2:
        await message.answer("Для поиска связей нужно вести хотя бы 2 разные привычки!")
        return
        
    corr_matrix = pivot.corr()
    
    response = "🔗 <b>Связи между твоими привычками:</b>\n\n"
    
    pairs = []
    cols = corr_matrix.columns
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            habit1, habit2 = cols[i], cols[j]
            corr_value = corr_matrix.iloc[i, j]
            if pd.notna(corr_value):
                pairs.append((habit1, habit2, corr_value))
                
    pairs.sort(key=lambda x: x[2], reverse=True)
    
    for h1, h2, corr in pairs:
        if corr > 0.3:
            icon = "🟢 Синергия"
        elif corr < -0.3:
            icon = "🔴 Конфликт"
        else:
            icon = "⚪️ Независимы"
            
        response += f"<b>{h1}</b> ↔️ <b>{h2}</b>\n"
        response += f"└ {icon} (Корреляция: {corr:.2f})\n\n"
        
    await message.answer(response)

@dp.message(Command("growth"))
async def growth_chart_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    
    if not logs:
        await message.answer("Пока нет данных для построения графика роста.")
        return
        
    df = pd.DataFrame(logs, columns=["Привычка", "Дата"])
    df['Дата'] = pd.to_datetime(df['Дата'], errors='coerce').dt.normalize()
    df = df.dropna(subset=['Дата'])
    
    daily_counts = df.groupby('Дата').size().reset_index(name='Количество')
    
    daily_counts['Кумулятивно'] = daily_counts['Количество'].cumsum()
    
    plt.figure(figsize=(10, 5))
    plt.plot(
        daily_counts['Дата'], 
        daily_counts['Кумулятивно'], 
        marker='o', 
        color='#2ecc71', 
        linewidth=2, 
        markersize=6
    )
    
    plt.title('Кумулятивный рост выполненных привычек', fontsize=14)
    plt.xlabel('Дата', fontsize=12)
    plt.ylabel('Всего выполнений', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    filename = f"growth_{user_id}.png"
    plt.savefig(filename)
    plt.close()
    
    photo = FSInputFile(filename)
    await message.answer_photo(
        photo, 
        caption="📈 <b>Твой долгосрочный прогресс!</b>\nГрафик кумулятивного роста."
    )
    
    os.remove(filename)

@dp.message(Command("rolling"))
async def rolling_average_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    
    if not logs:
        await message.answer("Пока нет данных для построения графика.")
        return
        
    df = pd.DataFrame(logs, columns=["Привычка", "Дата"])
    df['Дата'] = pd.to_datetime(df['Дата'], errors='coerce').dt.normalize()
    df = df.dropna(subset=['Дата'])
    
    daily_counts = df.groupby('Дата').size()
    
    all_days = pd.date_range(start=daily_counts.index.min(), end=pd.Timestamp.now().normalize())
    daily_counts = daily_counts.reindex(all_days, fill_value=0).reset_index()
    daily_counts.columns = ['Дата', 'Количество']
    
    daily_counts['SMA_7'] = daily_counts['Количество'].rolling(window=7, min_periods=1).mean()
    
    plt.figure(figsize=(10, 5))
    
    plt.bar(daily_counts['Дата'], daily_counts['Количество'], color='#bdc3c7', alpha=0.6, label='Факт')
    # Яркая линия сглаженного математического тренда
    plt.plot(daily_counts['Дата'], daily_counts['SMA_7'], color='#e74c3c', linewidth=3, label='Тренд (SMA-7)')
    
    plt.title('Тренд продуктивности (Скользящая средняя за 7 дней)', fontsize=14)
    plt.xlabel('Дата', fontsize=12)
    plt.ylabel('Выполнено привычек', fontsize=12)
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.4)
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    filename = f"rolling_{user_id}.png"
    plt.savefig(filename)
    plt.close()
    
    photo = FSInputFile(filename)
    await message.answer_photo(
        photo, 
        caption="📉 <b>Твой сглаженный тренд!</b>\nКрасная линия показывает реальную динамику без учета дневных скачков."
    )
    
    os.remove(filename)

@dp.message(Command("audit"))
async def habit_audit_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    habits = get_habits(user_id)
    
    if not habits:
        await message.answer("У тебя пока нет привычек для аудита.")
        return
        
    response = "🧹 <b>Аудит твоих привычек:</b>\n\n"
    
    if not logs:
        response += "Ты еще ничего не отмечал. Все привычки ждут первого шага!"
        await message.answer(response)
        return
        
    df = pd.DataFrame(logs, columns=["Привычка", "Дата"])
    df['Дата'] = pd.to_datetime(df['Дата'], errors='coerce').dt.normalize()
    now = pd.Timestamp.now().normalize()
    
    last_logs = df.groupby('Привычка')['Дата'].max()
    
    zombies = []
    active = []
    
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
            if days == "никогда":
                response += f" — <b>{h}</b> (еще ни одной отметки)\n"
            else:
                response += f" — <b>{h}</b> (простой: {days} дн.)\n"
        response += "\n<i>💡 Совет: удали неактуальные цели через «🗑 Удалить привычку», чтобы сфокусироваться на главном.</i>\n\n"
    else:
        response += "🌟 <b>Идеальная дисциплина!</b> У тебя нет заброшенных привычек.\n\n"
        
    response += f"✅ Активных привычек: <b>{len(active)}</b> из <b>{len(habits)}</b>"
    
    await message.answer(response)

@dp.message(Command("balance"))
async def balance_radar_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    
    if not logs:
        await message.answer("Пока нет данных для построения радара.")
        return
        
    df = pd.DataFrame(logs, columns=["Привычка", "Дата"])
    counts = df['Привычка'].value_counts()
    
    if len(counts) < 3:
        await message.answer("Для построения радара баланса нужно вести минимум 3 разные привычки!")
        return
        
    categories = counts.index.tolist()
    values = counts.values.tolist()
    
    values += values[:1]
    
    angles = [n / float(len(categories)) * 2 * np.pi for n in range(len(categories))]
    angles += angles[:1]
    
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    
    ax.plot(angles, values, color='#8e44ad', linewidth=2, linestyle='solid')
    ax.fill(angles, values, color='#8e44ad', alpha=0.3)
    
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=12, fontweight='bold')
    ax.set_yticks([]) 
    
    plt.title('Радар баланса привычек', size=16, y=1.1, fontweight='bold')
    
    filename = f"radar_{user_id}.png"
    plt.savefig(filename, bbox_inches='tight')
    plt.close()
    
    photo = FSInputFile(filename)
    await message.answer_photo(
        photo, 
        caption="🕸 <b>Твой баланс привычек!</b>\nЧем ровнее фигура, тем гармоничнее твоя рутина."
    )
    
    os.remove(filename)

@dp.message(Command("heatmap"))
async def heatmap_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    
    if not logs:
        await message.answer("Пока нет данных для тепловой карты. Сделай пару отметок!")
        return
        
    df = pd.DataFrame(logs, columns=["Привычка", "Дата"])
    df['Дата'] = pd.to_datetime(df['Дата'], errors='coerce').dt.normalize()
    df = df.dropna(subset=['Дата'])
    
    daily_counts = df.groupby('Дата').size()
    
    now = pd.Timestamp.now().normalize()
    start_date = now - pd.Timedelta(days=27)
    all_days = pd.date_range(start=start_date, end=now)
    
    heatmap_data = daily_counts.reindex(all_days, fill_value=0)
    
    response = "🗺 <b>Тепловая карта продуктивности (28 дней):</b>\n\n"
    
    chunks = [heatmap_data[i:i+7] for i in range(0, 28, 7)]
    
    for chunk in chunks:
        row_str = ""
        for val in chunk:
            if val == 0:
                row_str += "⬜️"
            elif val == 1:
                row_str += "🟨"
            elif val == 2:
                row_str += "🟧"
            else:
                row_str += "🟩"
        response += row_str + "\n"
        
    response += "\n<i>Легенда: ⬜️ 0 | 🟨 1 | 🟧 2 | 🟩 3+ выполнений в день</i>"
    
    await message.answer(response)

# ==========================================
# 5. ОСНОВНОЙ ФУНКЦИОНАЛ (CRUD ПРИВЫЧЕК И ОТМЕТКИ)
# ==========================================
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
    undo_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ Отменить", callback_data=f"undo_{habit_name}")]]
    )
    await message.answer(
        f"✅ Привычка «<b>{habit_name}</b>» выполнена!\n\n<i>{motivation}</i>", 
        reply_markup=undo_kb
    )
    await state.clear()

@dp.callback_query(F.data.startswith("undo_"))
async def undo_callback_handler(callback: CallbackQuery):
    habit_name = callback.data.split("undo_")[1]
    user_id = callback.from_user.id
    undo_habit_log(user_id, habit_name)
    await callback.message.edit_text(f"❌ Отметка для привычки «<b>{habit_name}</b>» отменена.")
    await callback.answer("Действие отменено")

@dp.message(StateFilter(None), F.text == "✏️ Изменить")
async def edit_habit_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    habits = get_habits(user_id)
    if not habits:
        await message.answer("У тебя пока нет привычек для изменения.")
        return
    await message.answer("Какую привычку хочешь переименовать?", reply_markup=habits_kb(habits))
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
    await message.answer(f"Готово! Привычка «{old_name}» переименована в «{new_name}».", reply_markup=main_kb)
    await state.clear()

@dp.message(StateFilter(None), F.text == "🗑 Удалить привычку")
async def delete_habit_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    habits = get_habits(user_id)
    if not habits:
        await message.answer("У тебя пока нет привычек, нечего удалять!")
        return
    await message.answer("Выбери привычку, которую хочешь удалить, на клавиатуре ниже:", reply_markup=habits_kb(habits))
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

# ==========================================
# 6. АНАЛИТИКА И ОТОБРАЖЕНИЕ ДАННЫХ
# ==========================================
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

@dp.message(StateFilter(None), F.text == "📝 Итоги дня")
async def daily_summary_handler(message: Message):
    user_id = message.from_user.id
    habits = get_habits(user_id)
    if not habits:
        await message.answer("У тебя пока нет привычек. Самое время добавить первую!")
        return
        
    done, pending = [], []
    for h in habits:
        if check_habit_logged_today(user_id, h):
            done.append(h)
        else:
            pending.append(h)
            
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
        await message.answer("У тебя пока нет отметок о выполнении привычек. Сделай хотя бы одну!")
        return
        
    response = f"📊 <b>Твоя статистика выполнений (цель: {TARGET_DAYS} дней):</b>\n\n"
    for habit_name, count in stats:
        streak = get_habit_streak(user_id, habit_name)
        emoji = get_streak_emoji(streak)
        streak_text = f" ({emoji} {streak} дней подряд)" if streak > 0 else " (🧊 нет активной серии)"
        progress_bar = make_progress_bar(count)
        
        response += f"🔹 <b>{habit_name}</b>: {count}/{TARGET_DAYS}\n"
        response += f"<code>[{progress_bar}]</code>{streak_text}\n\n"
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
    ax1.bar(habits, counts, color='#5c9ded')
    ax1.set_title('Прогресс выполнения (в днях)')
    ax1.set_ylabel('Количество дней')
    ax1.tick_params(axis='x', rotation=45)
    
    if sum(counts) > 0:
        ax2.pie(counts, labels=habits, autopct='%1.1f%%', startangle=90, colors=plt.cm.Paired.colors)
        ax2.set_title('Доля привычек')
    else:
        ax2.text(0.5, 0.5, 'Пока нет выполнений', ha='center', va='center')
        ax2.axis('off')
    
    plt.tight_layout()
    filename = f"chart_{user_id}.png"
    plt.savefig(filename)
    plt.close()
    
    photo = FSInputFile(filename)
    await message.answer_photo(photo, caption="Твои данные в виде графика! 📊")
    os.remove(filename)

@dp.message(StateFilter(None), F.text == "🏆 Рекорды")
async def records_handler(message: Message):
    user_id = message.from_user.id
    stats = get_habit_stats(user_id)
    if not stats:
        await message.answer("У тебя пока нет данных для рекордов. Отметь хотя бы одну привычку!")
        return
        
    most_completed = max(stats, key=lambda x: x[1])
    habits = get_habits(user_id)
    best_streak_habit = None
    max_streak = 0
    
    for h in habits:
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

@dp.message(StateFilter(None), F.text == "👤 Мой профиль")
async def user_profile_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    total_logs = len(logs)
    level = int(total_logs ** 0.5)
    next_level_logs = (level + 1) ** 2
    logs_needed = next_level_logs - total_logs
    
    if level == 0: rank = "Новичок 🚶‍♂️"
    elif level < 3: rank = "Искатель 🔍"
    elif level < 5: rank = "Адепт рутины 🧘‍♂️"
    elif level < 8: rank = "Мастер привычек 🥷"
    else: rank = "Легенда 👑"
        
    response = (
        f"👤 <b>Твой профиль:</b>\n\n"
        f"📊 Всего выполнений: <b>{total_logs}</b>\n"
        f"⭐ Уровень: <b>{level}</b> (<i>{rank}</i>)\n"
        f"📈 До следующего уровня: осталось {logs_needed} выполнений"
    )
    await message.answer(response)

@dp.message(StateFilter(None), F.text == "📁 Экспорт данных")
async def export_data_handler(message: Message):
    user_id = message.from_user.id
    logs = get_all_logs(user_id)
    if not logs:
        await message.answer("У тебя пока нет истории выполнений для экспорта. Отметь хотя бы одну привычку!")
        return
    df = pd.DataFrame(logs, columns=["Привычка", "Дата выполнения"])
    df = df.sort_values(by=["Привычка", "Дата выполнения"], ascending=[True, False])
    filename = f"habits_dataset_{user_id}.xlsx"
    df.to_excel(filename, index=False, engine='openpyxl')
    document = FSInputFile(filename)
    await message.answer_document(
        document, 
        caption="Твой датасет готов! 📊\nСобран и отсортирован с помощью pandas."
    )

    os.remove(filename)

# ==========================================
# 7. ОБРАБОТКА ОШИБОК И ЗАПУСК
# ==========================================
@dp.error()
async def global_error_handler(event: ErrorEvent):
    logger.error(f"Произошла непредвиденная ошибка: {event.exception}", exc_info=True)
    try:
        if event.update.message:
            await event.update.message.answer(
                "Упс! Внутри бота что-то сломалось 🛠.\n"
                "Разработчик уже получил запись в логах и скоро всё починит!"
            )
        elif event.update.callback_query:
            await event.update.callback_query.message.answer("Произошла ошибка 🛠. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение об ошибке: {e}")

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
        BotCommand(command="heatmap", description="Карта активности (как в GitHub)")
    ]
    await bot.set_my_commands(commands)

async def main():
    init_db()
    logger.info("Бот успешно запущен и готов к работе!")
    
    await set_default_commands(bot)
    
    scheduler = AsyncIOScheduler(timezone='Europe/Moscow')
    scheduler.add_job(send_daily_reminders, trigger='cron', hour=20, minute=0)
    scheduler.start()

    scheduler = AsyncIOScheduler(timezone='Europe/Moscow')
    # Утренний план на день (в 08:00)
    scheduler.add_job(send_morning_greeting, trigger='cron', hour=8, minute=0)
    # Вечернее напоминание (в 20:00)
    scheduler.add_job(send_daily_reminders, trigger='cron', hour=20, minute=0)
    scheduler.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())