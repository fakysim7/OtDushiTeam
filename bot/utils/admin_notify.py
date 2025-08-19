# bot/utils/admin_notify.py
from aiogram import Bot
from config import ADMINS

async def notify_admin_new_booking(bot: Bot, user_data: dict):
    """Уведомляет админов о новой брони"""
    
    # Отправляем уведомления всем админам
    for admin_id in ADMINS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text="🔔 <b>НОВАЯ БРОНЬ!</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления админу {admin_id}: {e}")