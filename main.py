import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: Message):
    await message.answer("Привет! Я твой трекер привычек")

@dp.message(Command("help"))
async def command_help_handler(message: Message):
    await message.answer("Мои команды:\n/start - Перезапуск\n/help - Справка")

async def main():
    print("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())