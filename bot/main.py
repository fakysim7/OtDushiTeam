# Файл: bot/main.py
import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from handlers import user, admin
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=RedisStorage(Redis(host="redis")))

    dp.include_routers(user.router, admin.router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())