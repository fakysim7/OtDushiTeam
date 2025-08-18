# bot/main.py - ИСПРАВЛЕННАЯ версия для Railway
import asyncio
import os
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from handlers import user, admin
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

async def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN не установлен!")
        return
        
    bot = Bot(token=BOT_TOKEN)
    
    # ИСПРАВЛЕНО: Используем REDIS_URL от Railway
    redis_url = os.getenv('REDIS_URL')
    
    if redis_url:
        print(f"Connecting to Redis via URL: {redis_url}")
        redis = Redis.from_url(redis_url)
    else:
        # Fallback для локальной разработки
        print("REDIS_URL not found, using localhost")
        redis = Redis(host='localhost', port=6379)
    
    try:
        # Проверяем подключение к Redis
        await redis.ping()
        print("✅ Redis connection successful!")
        
        dp = Dispatcher(storage=RedisStorage(redis))
        dp.include_routers(user.router, admin.router)
        
        print("🚀 Bot starting...")
        await dp.start_polling(bot)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        # Если Redis недоступен, используем MemoryStorage
        print("⚠️ Falling back to MemoryStorage")
        from aiogram.fsm.storage.memory import MemoryStorage
        
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_routers(user.router, admin.router)
        await dp.start_polling(
            bot, 
            polling_timeout=30,  
            request_timeout=30
        )

if __name__ == "__main__":
    asyncio.run(main())


