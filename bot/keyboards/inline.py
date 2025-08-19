from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta


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


def dynamic_hours_kb(selected_date: str = None) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с временными слотами, учитывая московское время
    """
    from datetime import datetime, timedelta
    import pytz
    
    builder = InlineKeyboardBuilder()
    
    # Получаем московское время
    moscow_tz = pytz.timezone('Europe/Moscow')
    now_moscow = datetime.now(moscow_tz)
    current_date_moscow = now_moscow.date()
    
    print(f"DEBUG: Московское время: {now_moscow.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"DEBUG: selected_date = {selected_date}")
    print(f"DEBUG: current_date_moscow = {current_date_moscow}")
    
    # Проверяем, является ли выбранная дата сегодняшней по МСК
    is_today = False
    if selected_date:
        try:
            selected_date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
            is_today = selected_date_obj == current_date_moscow
            print(f"DEBUG: selected_date_obj = {selected_date_obj}")
            print(f"DEBUG: is_today = {is_today}")
        except ValueError:
            print(f"DEBUG: Ошибка парсинга даты: {selected_date}")
            is_today = False
    
    # Определяем минимальное доступное время
    min_hour = 10  # Время открытия заведения
    
    if is_today:
        # Добавляем буферное время (1 час)
        buffer_minutes = 60
        min_datetime_moscow = now_moscow + timedelta(minutes=buffer_minutes)
        min_hour = min_datetime_moscow.hour
        
        # Если есть минуты, переходим к следующему часу
        if min_datetime_moscow.minute > 0:
            min_hour += 1
            
        # Но не раньше времени открытия
        min_hour = max(min_hour, 10)
        
        print(f"DEBUG: Сегодня {current_date_moscow}, сейчас {now_moscow.time()} МСК")
        print(f"DEBUG: Минимальный час с буфером: {min_hour}")
    
    # Генерируем доступные часы (до 22:00, чтобы можно было забронировать минимум 1 час до закрытия в 23:00)
    available_hours = []
    for hour in range(min_hour, 23):  # До 22:00 включительно
        available_hours.append(f"{hour:02d}:00")
    
    print(f"DEBUG: Доступные часы: {available_hours}")
    
    # Если нет доступных часов на сегодня
    if is_today and not available_hours:
        builder.button(
            text="❌ На сегодня время закончилось", 
            callback_data="time_unavailable"
        )
        print(f"DEBUG: На сегодня время закончилось")
    else:
        for time_slot in available_hours:
            builder.button(text=time_slot, callback_data=f"time_{time_slot}")
        
        builder.adjust(4)  # 4 кнопки в ряд
    
    return builder.as_markup()



def duration_kb(selected_time: str = None) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с продолжительностью, учитывая время закрытия (23:00)
    
    Args:
        selected_time: Выбранное время в формате HH:MM
    """
    from datetime import datetime, timedelta
    
    builder = InlineKeyboardBuilder()
    
    # Время закрытия заведения
    CLOSING_TIME = 23  # 23:00
    
    max_duration = 3  # Максимальная продолжительность по умолчанию
    
    if selected_time:
        try:
            # Парсим выбранное время
            start_time = datetime.strptime(selected_time, "%H:%M")
            start_hour = start_time.hour
            
            # Вычисляем максимальную продолжительность до закрытия
            max_duration = min(3, CLOSING_TIME - start_hour)
            
            print(f"DEBUG: Выбранное время: {selected_time}")
            print(f"DEBUG: Начальный час: {start_hour}")
            print(f"DEBUG: Максимальная продолжительность: {max_duration}")
            
        except ValueError:
            print(f"DEBUG: Ошибка парсинга времени: {selected_time}")
            max_duration = 3
    
    # Создаем кнопки только для доступной продолжительности
    if max_duration <= 0:
        builder.button(
            text="❌ Нет доступного времени", 
            callback_data="duration_unavailable"
        )
        print(f"DEBUG: Нет доступного времени для выбранного времени")
    else:
        for dur in range(1, max_duration + 1):
            builder.button(text=f"{dur} ч", callback_data=f"duration_{dur}")
        
        builder.adjust(3)
    
    return builder.as_markup()


def place_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📍 Заведение 1 (Пр-т Победителей 85)", callback_data="place_1")
    builder.button(text="📍 Заведение 2 (Пр-т Дзержинского 9)", callback_data="place_2")
    builder.adjust(1)  # По одной кнопке в строке
    return builder.as_markup()
