# Файл: bot/keyboards/main.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📅 Забронировать")],
        [KeyboardButton(text="📋 Мои брони")],
        [KeyboardButton(text="❓ Помощь")]
    ], resize_keyboard=True)