from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters.callback_data import CallbackData

MONTH_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

class CalendarCallback(CallbackData, prefix="cal"):
    act: str
    year: int
    month: int
    day: int

class RussianCalendar:
    def __init__(self):
        self.today = datetime.now()

    async def start_calendar(self, year: int = None, month: int = None) -> InlineKeyboardMarkup:
        if year is None:
            year = self.today.year
        if month is None:
            month = self.today.month

        keyboard = []

        # Строка навигации: << Месяц Год >>
        keyboard.append([
            InlineKeyboardButton(
                text="<<",
                callback_data=CalendarCallback.model_validate({
                    "act": "prev",
                    "year": year,
                    "month": month,
                    "day": 0
                }).pack()
            ),
            InlineKeyboardButton(
                text=f"{MONTH_NAMES[month-1]} {year}",
                callback_data="ignore"
            ),
            InlineKeyboardButton(
                text=">>",
                callback_data=CalendarCallback.model_validate({
                    "act": "next",
                    "year": year,
                    "month": month,
                    "day": 0
                }).pack()
            ),
        ])

        # Дни недели
        keyboard.append([
            InlineKeyboardButton(text=day, callback_data="ignore") for day in WEEKDAYS
        ])

        # Первый день месяца и его день недели (Пн=0, Вс=6)
        first_day = datetime(year, month, 1)
        start_weekday = first_day.weekday()  # 0 (Пн) - 6 (Вс)

        # Пустые кнопки до первого дня месяца
        row = []
        for _ in range(start_weekday):
            row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))

        # Количество дней в месяце
        if month == 12:
            next_month = datetime(year + 1, 1, 1)
        else:
            next_month = datetime(year, month + 1, 1)
        days_in_month = (next_month - timedelta(days=1)).day

        # Календарные дни
        for day in range(1, days_in_month + 1):
            if len(row) == 7:
                keyboard.append(row)
                row = []

            date_obj = datetime(year, month, day)
            is_today = date_obj.date() == self.today.date()
            is_past = date_obj.date() < self.today.date()

            # Декорирование
            if is_today:
                day_text = f"[{day}]"  # Сегодняшний день в квадратных скобках
            elif is_past:
                day_text = f"{day}"   # Прошедшие дни с белым кружком
            else:
                day_text = str(day)

            if is_past:
                # Прошедшие дни неактивны
                row.append(InlineKeyboardButton(text=day_text, callback_data="ignore"))
            else:
                # Доступные дни
                row.append(
                    InlineKeyboardButton(
                        text=day_text,
                        callback_data=CalendarCallback.model_validate({
                            "act": "select",
                            "year": year,
                            "month": month,
                            "day": day
                        }).pack()
                    )
                )
        # Пустые кнопки после последнего дня месяца
        while len(row) < 7:
            row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
        keyboard.append(row)


        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    async def process_selection(self, callback_query, callback_data: CalendarCallback):
        act = callback_data.act
        year = callback_data.year
        month = callback_data.month
        day = callback_data.day

        if act == "ignore":
            await callback_query.answer()
            return False, None

        elif act == "select":
            selected_date = datetime(year, month, day)
            if selected_date.date() < self.today.date():
                await callback_query.answer(
                    "Нельзя выбирать прошедшую дату, выберите другой день.",
                    show_alert=False  # Это toast-уведомление!
                )
                return False, None
            await callback_query.message.edit_reply_markup(reply_markup=None)
            return True, selected_date

        elif act == "prev":
            month -= 1
            if month < 1:
                month = 12
                year -= 1
            markup = await self.start_calendar(year, month)
            await callback_query.message.edit_reply_markup(reply_markup=markup)
            return False, None

        elif act == "next":
            month += 1
            if month > 12:
                month = 1
                year += 1
            markup = await self.start_calendar(year, month)
            await callback_query.message.edit_reply_markup(reply_markup=markup)
            return False, None

        # ОБЯЗАТЕЛЬНО!
        return False, None