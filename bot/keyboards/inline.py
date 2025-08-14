from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def time_slots_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    
    # Добавьте кнопки с временными слотами
    times = ["10:00", "12:00", "14:00", "16:00", "18:00", "20:00"]
    buttons = [
        InlineKeyboardButton(text=time, callback_data=f"time_{time}")
        for time in times
    ]
    
    kb.inline_keyboard = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    return kb

def confirm_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("✅ Подтверждено", callback_data="confirmed")]
    ])


def dynamic_hours_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for hour in range(10, 22):  # Последняя бронь на 21:00
        builder.button(text=f"{hour}:00", callback_data=f"time_{hour}:00")
    builder.adjust(4)  # 4 кнопки в ряд
    return builder.as_markup()

def duration_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for dur in range(1, 4):
        builder.button(text=f"{dur} ч", callback_data=f"duration_{dur}")
    builder.adjust(3)
    return builder.as_markup()


def place_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📍 Заведение 1 (Пр-т Победителей 85)", callback_data="place_1")
    builder.button(text="📍 Заведение 2 (Пр-т Дзержинского 9)", callback_data="place_2")
    builder.adjust(1)  # По одной кнопке в строке
    return builder.as_markup()
