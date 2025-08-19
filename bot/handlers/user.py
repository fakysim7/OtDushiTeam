#bot/hundlers/user.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
import pytz
import httpx
from config import API_URL
from datetime import datetime
from keyboards.main import main_menu
from russian_calendar import RussianCalendar, CalendarCallback
from keyboards.inline import duration_kb, dynamic_hours_kb, place_kb
from utils.admin_notify import notify_admin_new_booking
from typing import Optional, Dict
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException

router = Router()


PLACE_ADDRESSES = {
    "1": "Пр-т Победителей 85",
    "2": "Пр-т Дзержинского 9"
}

class ReserveState(StatesGroup):
    place = State()
    date = State()
    time = State()
    duration = State()
    name = State()
    phone = State()

async def make_api_request(
    method: str,
    endpoint: str,
    params: Optional[Dict] = None,
    json: Optional[Dict] = None
) -> Dict:
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method,
            f"{API_URL}{endpoint}",
            params=params,
            json=json
        )
        return response.json()

@router.message(CommandStart())
async def start(msg: types.Message):
    await msg.answer(
        "👋 Добро пожаловать в бот бронирования столиков!\n\n"
        "Вы можете выбрать действие в меню ниже:",
        reply_markup=main_menu()
    )

@router.message(F.text.lower().in_(["📅 забронировать", "забронировать"]))
async def start_reserve(msg: types.Message, state: FSMContext):
    await msg.answer("Выберите заведение:", reply_markup=place_kb())
    await state.set_state(ReserveState.place)

@router.callback_query(F.data.startswith("place_"), ReserveState.place)
async def select_place(callback: types.CallbackQuery, state: FSMContext):
    place = callback.data.replace("place_", "")
    await state.update_data(place=place)
    await callback.message.answer(
        "Теперь выберите дату бронирования:",
        reply_markup=await RussianCalendar().start_calendar()
    )
    await state.set_state(ReserveState.date)


# @router.callback_query(calendar_cb.filter(), ReserveState.date)
# async def process_date(callback_query: types.CallbackQuery, callback_data: dict, state: FSMContext):
#     selected, selected_date = await RussianCalendar().process_selection(callback_query, callback_data)
    
#     if not selected:
#         return

#     if selected_date.date() < datetime.now().date():
#         await callback_query.message.answer("Выбрана прошедшая дата. Пожалуйста, выберите другую дату.")
#         return

#     await state.update_data(date=selected_date.strftime("%Y-%m-%d"))
#     await callback_query.message.answer(
#         f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}\nВыберите время:",
#         reply_markup=dynamic_hours_kb()
#     )
#     await state.set_state(ReserveState.time)

@router.callback_query(CalendarCallback.filter(), ReserveState.date)
async def process_date(callback_query: types.CallbackQuery, callback_data: CalendarCallback, state: FSMContext):
    import pytz
    
    selected, selected_date = await RussianCalendar().process_selection(callback_query, callback_data)

    if not selected:
        return

    selected_date_str = selected_date.strftime("%Y-%m-%d")
    await state.update_data(date=selected_date_str)
    
    # Формируем красивое отображение даты
    formatted_date = selected_date.strftime('%d.%m.%Y')
    
    # Проверяем по московскому времени
    moscow_tz = pytz.timezone('Europe/Moscow')
    now_moscow = datetime.now(moscow_tz)
    is_today = selected_date.date() == now_moscow.date()
    
    if is_today:
        current_time_str = now_moscow.strftime('%H:%M')
        message_text = f"Выбрана дата: {formatted_date} (сегодня)\nСейчас: {current_time_str} МСК\nВыберите время:"
    else:
        message_text = f"Выбрана дата: {formatted_date}\nВыберите время:"
    
    print(f"DEBUG: Отправка выбранной даты в клавиатуру: {selected_date_str}")
    
    await callback_query.message.answer(
        message_text,
        reply_markup=dynamic_hours_kb(selected_date_str)
    )
    await state.set_state(ReserveState.time)


@router.callback_query(F.data == "time_unavailable")
async def time_unavailable_handler(callback: types.CallbackQuery):
    """Обработчик для случая когда время на сегодня закончилось"""
    await callback.answer(
        "⏰ На сегодня доступное время для бронирования закончилось.\n"
        "Попробуйте выбрать другую дату.",
        show_alert=True
    )

@router.callback_query(F.data == "ignore", ReserveState.date)
async def ignore_past_date(callback: types.CallbackQuery):
    await callback.answer(
        "Нельзя выбирать прошедшую дату, выберите другой день.",
        show_alert=False  # Это toast!
    )
    
@router.callback_query(F.data.startswith("time_"), ReserveState.time)
async def select_time(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "time_unavailable":
        await callback.answer(
            "⏰ На сегодня доступное время для бронирования закончилось.\n"
            "Попробуйте выбрать другую дату.",
            show_alert=True
        )
        return
    
    time = callback.data.split("_")[1]
    await state.update_data(time=time)
    
    # Вычисляем время закрытия для выбранного времени
    try:
        from datetime import datetime
        start_time = datetime.strptime(time, "%H:%M")
        closing_time = datetime.strptime("23:00", "%H:%M")
        
        max_hours = (closing_time - start_time).seconds // 3600
        
        if max_hours <= 0:
            await callback.message.answer(
                f"❌ К сожалению, в {time} заведение уже будет закрываться.\n"
                "Пожалуйста, выберите более раннее время.",
                reply_markup=dynamic_hours_kb()
            )
            return
        elif max_hours >= 3:
            duration_text = "⏱️ Укажите продолжительность (в часах):"
        else:
            duration_text = f"⏱️ Укажите продолжительность (в часах):\nЗаведение закрывается в 23:00, максимум {max_hours} ч"
            
    except:
        duration_text = "⏱️ Укажите продолжительность (в часах):"
    
    await callback.message.answer(
        duration_text, 
        reply_markup=duration_kb(time)  # Передаем выбранное время
    )
    await state.set_state(ReserveState.duration)



@router.callback_query(F.data == "duration_unavailable")
async def duration_unavailable_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик для случая когда нет доступной продолжительности"""
    await callback.answer(
        "❌ Для выбранного времени нет доступной продолжительности.\n"
        "Заведение закрывается в 23:00. Выберите более раннее время.",
        show_alert=True
    )

@router.callback_query(F.data.startswith("duration_"), ReserveState.duration)
async def select_duration(callback: types.CallbackQuery, state: FSMContext):
    duration = int(callback.data.split("_")[1])
    data = await state.get_data()

    check = await make_api_request("GET", "/check", params={
        "date": data["date"],
        "time": data["time"],
        "duration": duration,
        "place": data["place"]  # добавили place
    })


    if not check.get("free", 0):
        await callback.message.answer("Нет свободных столиков на это время и продолжительность.")
        return

    await state.update_data(duration=duration)
    await callback.message.answer("Как вас зовут?")
    await state.set_state(ReserveState.name)

@router.message(ReserveState.name)
async def get_name(msg: types.Message, state: FSMContext):
    await state.update_data(name=msg.text)
    await msg.answer("Введите ваш номер телефона:")
    await state.set_state(ReserveState.phone)


@router.message(ReserveState.phone)
async def get_phone(msg: types.Message, state: FSMContext):
    # ✅ ЗАЩИТА: Сразу очищаем состояние чтобы предотвратить повторную обработку
    user_data = await state.get_data()
    await state.clear()
    
    try:
        # Парсим номер телефона
        parsed_number = phonenumbers.parse(msg.text, None)
        
        # Проверяем валидность номера
        if not phonenumbers.is_valid_number(parsed_number):
            raise ValueError("Некорректный номер телефона")
            
        # Форматируем номер в международном формате
        formatted_phone = phonenumbers.format_number(
            parsed_number,
            phonenumbers.PhoneNumberFormat.INTERNATIONAL
        )
        
        # ✅ ПРОВЕРКА: Существует ли уже такая бронь
        existing_check = await make_api_request("GET", "/get_reservations")
        
        # Проверяем на дублирование по user_id + date + time
        for reservation in existing_check.values() if isinstance(existing_check, dict) else []:
            if (str(reservation.get("user_id")) == str(msg.from_user.id) and
                reservation.get("date") == user_data.get("date") and
                reservation.get("time") == user_data.get("time") and
                not reservation.get("cancelled")):
                
                await msg.answer("❌ У вас уже есть бронь на это время!")
                return
        
        # Отправляем запрос в API
        result = await make_api_request(
            "POST",
            "/reserve",
            json={
                "place": user_data["place"],
                "name": user_data["name"],
                "phone": formatted_phone,
                "date": user_data["date"],
                "time": user_data["time"],
                "duration": user_data["duration"],
                "user_id": msg.from_user.id
            }
        )
        
        # ✅ УВЕДОМЛЯЕМ АДМИНОВ:
        await notify_admin_new_booking(msg.bot, user_data)
        
        await msg.answer("✅ Бронь успешно отправлена! Ожидайте подтверждения.\n" \
                        "А пока можете ознакомиться с нашим меню https://amelie-cafe.by/menu")
        
    except NumberParseException:
        # Восстанавливаем состояние для повторного ввода номера
        await state.set_data(user_data)
        await state.set_state(ReserveState.phone)
        
        await msg.answer(
            "⚠️ Пожалуйста, введите корректный номер телефона в международном формате.\n"
            "Примеры:\n"
            "+375 33 777 77 77 (Беларусь)\n"
            "+44 20 1234 5678 (Великобритания)\n"
            "+49 30 1234567 (Германия)\n"
            "+7 912 345 67 89 (Россия)\n\n"
            "Попробуйте ввести номер еще раз:"
        )
        return
        
    except Exception as e:
        # Восстанавливаем состояние для повторного ввода номера
        await state.set_data(user_data)
        await state.set_state(ReserveState.phone)
        
        await msg.answer(
            f"⛔ Произошла ошибка: {str(e)}\n"
            "Пожалуйста, введите номер телефона еще раз:"
        )
        return




# В начале файла user.py добавить константы
PLACE_ADDRESSES = {
    "1": "Пр-т Победителей 85",
    "2": "Пр-т Дзержинского 9"
}

@router.message(F.text.lower().in_(["📋 мои брони", "мои брони"]))
async def my_reservations(msg: types.Message):
    """Показывает кнопки для выбора категории бронирований"""
    try:
        # Получаем все бронирования пользователя
        user_reservations = await get_user_reservations(msg.from_user.id)
        
        if not user_reservations:
            await msg.answer("У вас нет бронирований.")
            return

        # Подсчитываем количество в каждой категории
        categories = await categorize_reservations(user_reservations)
        
        active_count = len(categories['active'])
        pending_count = len(categories['pending'])
        past_count = len(categories['past'])
        total_count = len(user_reservations)

        # Создаем клавиатуру с кнопками
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        kb = InlineKeyboardBuilder()
        
        # Кнопки для каждой категории с количеством
        kb.button(
            text=f"✅ Активные ({active_count})",
            callback_data="reservations_active"
        )
        kb.button(
            text=f"⏳ В ожидании ({pending_count})",
            callback_data="reservations_pending"
        )
        kb.button(
            text=f"❌ Прошедшие ({past_count})",
            callback_data="reservations_past"
        )

        
        # Располагаем по 2 кнопки в ряд
        kb.adjust(1, 2)


        await msg.answer(
            "📋 <b>Ваши брони</b>",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )

    except Exception as e:
        await msg.answer(
            "⚠️ Произошла ошибка при получении бронирований.\n"
            "Попробуйте позже или обратитесь в поддержку."
        )
        print(f"Ошибка при получении бронирований: {str(e)}")


@router.callback_query(F.data.startswith("reservations_"))
async def handle_reservations_callback(callback: types.CallbackQuery):
    """Объединенный обработчик для всех callback'ов связанных с бронированиями"""
    try:
        # Если это кнопка "Назад в меню"
        if callback.data == "reservations_back":
            # Получаем все бронирования пользователя
            user_reservations = await get_user_reservations(callback.from_user.id)
            
            if not user_reservations:
                await callback.message.edit_text("У вас нет бронирований.")
                return

            # Подсчитываем количество в каждой категории
            categories = await categorize_reservations(user_reservations)
            
            active_count = len(categories['active'])
            pending_count = len(categories['pending'])
            past_count = len(categories['past'])
            total_count = len(user_reservations)

            # Создаем клавиатуру с кнопками
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            
            kb = InlineKeyboardBuilder()
            
            kb.button(
                text=f"✅ Активные ({active_count})",
                callback_data="reservations_active"
            )
            kb.button(
                text=f"⏳ В ожидании ({pending_count})",
                callback_data="reservations_pending"
            )
            kb.button(
                text=f"❌ Прошедшие ({past_count})",
                callback_data="reservations_past"
            )

            
            kb.adjust(1, 2)

            await callback.message.edit_text(
                "📋 <b>Ваши брони</b>",
                parse_mode="HTML",
                reply_markup=kb.as_markup()
            )
            return
        
        # Иначе обрабатываем как выбор категории
        category = callback.data.replace("reservations_", "")
        
        # Получаем все бронирования пользователя
        user_reservations = await get_user_reservations(callback.from_user.id)
        
        if not user_reservations:
            await callback.message.edit_text("У вас нет бронирований.")
            return

        # Категоризируем бронирования
        categories = await categorize_reservations(user_reservations)
        
        # Определяем какую категорию показать
        if category == "active":
            reservations_to_show = categories['active']
            title = "✅ <b>Активные</b>"
            empty_message = "У вас нет активных бронирований."
        elif category == "pending":
            reservations_to_show = categories['pending']
            title = "⏳ <b>В ожидании</b>"
            empty_message = "У вас нет бронирований в ожидании."
        elif category == "past":
            reservations_to_show = categories['past']
            title = "❌ <b>Прошедшие</b>"
            empty_message = "У вас нет прошедших бронирований."


        # Формируем ответ
        if not reservations_to_show:
            response = f"{title}\n\n{empty_message}"
        else:
            response = f"{title}\n\n"
            
            # Сортируем бронирования
            reservations_to_show.sort(key=lambda x: (x.get("date", ""), x.get("time", "")))
            
            for i, res in enumerate(reservations_to_show, 1):
                response += await format_reservation(res, i)
                # Добавляем разделитель между бронированиями, кроме последней
                if i < len(reservations_to_show):
                    response += "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        # Создаем кнопку "Назад"
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 Назад в меню", callback_data="reservations_back")
        
        
        kb.adjust(1)

        await callback.message.edit_text(
            response,
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        
    except Exception as e:
        await callback.answer("⚠️ Произошла ошибка при загрузке бронирований", show_alert=True)
        print(f"Ошибка при работе с бронированиями: {str(e)}")


async def get_user_reservations(user_id: int) -> list:
    """Получает все бронирования пользователя"""
    try:
        # Получаем все бронирования
        reservations_response = await make_api_request("GET", "/get_reservations")
        
        if isinstance(reservations_response, dict):
            reservations_list = list(reservations_response.values())
        elif isinstance(reservations_response, list):
            reservations_list = reservations_response
        else:
            raise ValueError("Некорректный формат данных о бронированиях")
        
        # Фильтруем брони текущего пользователя
        user_reservations = [
            res for res in reservations_list
            if isinstance(res, dict) and str(res.get("user_id")) == str(user_id)
        ]
        
        return user_reservations
        
    except Exception as e:
        print(f"Ошибка при получении бронирований пользователя: {str(e)}")
        return []


async def categorize_reservations(reservations: list) -> dict:
    """Разделяет бронирования по категориям"""
    # Получаем текущую дату
    current_date = datetime.now().date()
    
    active_reservations = []      # Подтвержденные и предстоящие
    pending_reservations = []     # В ожидании подтверждения
    past_reservations = []        # Прошедшие или отмененные

    for res in reservations:
        try:
            # Получаем дату бронирования
            reservation_date = datetime.strptime(res.get('date', ''), '%Y-%m-%d').date()
            is_past = reservation_date < current_date
            
            # Определяем статус
            is_cancelled = res.get("cancelled") or res.get("status") == "cancelled"
            is_confirmed = res.get("confirmed") or res.get("status") == "confirmed"
            
            if is_cancelled or is_past:
                past_reservations.append(res)
            elif is_confirmed:
                active_reservations.append(res)
            else:
                pending_reservations.append(res)
                
        except ValueError:
            # Если не удается распарсить дату, отправляем в прошедшие
            past_reservations.append(res)

    return {
        'active': active_reservations,
        'pending': pending_reservations,
        'past': past_reservations
    }


async def format_reservation(res: dict, number: int) -> str:
    """Форматирует бронирование для отображения в новом формате"""
    import pytz
    
    # Определяем статус и иконку
    if res.get("cancelled") or res.get("status") == "cancelled":
        status_icon = "❌"
        status_text = "❌ Отменена"
    elif res.get("confirmed") or res.get("status") == "confirmed":
        status_icon = "✅"
        status_text = "✅ Подтверждена"
    else:
        status_icon = "⏳"
        status_text = "⏳ В ожидании"
    
    # Преобразуем ID места в адрес
    raw_place = res.get('place', 'Не указано')
    if str(raw_place) in PLACE_ADDRESSES:
        place = PLACE_ADDRESSES[str(raw_place)]
    else:
        place = raw_place if raw_place != 'Не указано' else 'Не указано'
    
    formatted = (
        f"{status_icon} <b>Бронь #{number}</b>\n"
        f"👤 Имя: {res.get('name', 'Не указано')}\n"
        f"📞 Телефон: {res.get('phone', 'Не указан')}\n\n"
        
        f"🏠 Место: {place}\n"
        f"📅 Дата: {res.get('date', 'Не указана')}\n"
        f"⏰ Время: {res.get('time', 'Не указано')}\n"
        f"⏱️ Длительность: {res.get('duration', 1)} ч\n\n"
        
        f"📌 Статус: {status_text}"
    )
    
    # Московская временная зона
    moscow_tz = pytz.timezone('Europe/Moscow')
    
    # Добавляем информацию о предзаказе если есть
    if res.get("preorder"):
        formatted += f"\n🍽 Предзаказ: Отмечен"
        if res.get("preorder_at"):
            try:
                # Парсим время и конвертируем в МСК
                preorder_utc = datetime.fromisoformat(res["preorder_at"].replace('Z', '+00:00'))
                if preorder_utc.tzinfo is None:
                    # Если нет информации о зоне, считаем что UTC
                    preorder_utc = preorder_utc.replace(tzinfo=pytz.UTC)
                preorder_moscow = preorder_utc.astimezone(moscow_tz)
                formatted += f" ({preorder_moscow.strftime('%d.%m.%Y %H:%M')})"
            except:
                pass
    
    # Добавляем дополнительную информацию о датах операций
    if res.get("cancelled_at"):
        try:
            # Парсим время отмены и конвертируем в МСК
            cancelled_utc = datetime.fromisoformat(res["cancelled_at"].replace('Z', '+00:00'))
            if cancelled_utc.tzinfo is None:
                cancelled_utc = cancelled_utc.replace(tzinfo=pytz.UTC)
            cancelled_moscow = cancelled_utc.astimezone(moscow_tz)
            formatted += f"\n🕑 Отменена: {cancelled_moscow.strftime('%d.%m.%Y в %H:%M')} "
        except Exception as e:
            print(f"DEBUG: Ошибка парсинга cancelled_at: {e}")
            pass
    elif res.get("confirmed_at"):
        try:
            # Парсим время подтверждения и конвертируем в МСК
            confirmed_utc = datetime.fromisoformat(res["confirmed_at"].replace('Z', '+00:00'))
            if confirmed_utc.tzinfo is None:
                confirmed_utc = confirmed_utc.replace(tzinfo=pytz.UTC)
            confirmed_moscow = confirmed_utc.astimezone(moscow_tz)
            formatted += f"\n🕑 Подтверждена: {confirmed_moscow.strftime('%d.%m.%Y в %H:%M')} "
        except Exception as e:
            print(f"DEBUG: Ошибка парсинга confirmed_at: {e}")
            pass
    
    formatted += "\n\n"
    return formatted


# Функция для отмены собственной брони пользователем (если нужно)
# @router.message(F.text.lower().in_(["🚫 отменить бронь", "отменить бронь"]))
# async def cancel_my_reservation(msg: types.Message):
#     try:
#         # Получаем брони пользователя
#         reservations_response = await make_api_request("GET", "/get_reservations")
        
#         if isinstance(reservations_response, dict):
#             reservations_list = list(reservations_response.values())
#         elif isinstance(reservations_response, list):
#             reservations_list = reservations_response
#         else:
#             raise ValueError("Некорректный формат данных о бронированиях")
        
#         # Находим активные брони пользователя (не отмененные и не завершенные)
#         user_active_reservations = [
#             res for res in reservations_list
#             if (isinstance(res, dict) and 
#                 str(res.get("user_id")) == str(msg.from_user.id) and
#                 not res.get("cancelled") and
#                 res.get("status") != "cancelled")
#         ]

#         if not user_active_reservations:
#             await msg.answer("У вас нет активных бронирований для отмены.")
#             return

#         # Сортируем по дате
#         user_active_reservations.sort(key=lambda x: (x.get("date", ""), x.get("time", "")))

#         response = "🚫 <b>Выберите бронь для отмены:</b>\n\n"
        
#         kb = InlineKeyboardBuilder()
        
#         for i, res in enumerate(user_active_reservations, 1):
#             date = res.get('date', 'Не указана')
#             time = res.get('time', 'Не указано')
#             place = res.get('place', 'Не указано')
            
#             # Преобразуем место
#             if str(place) in PLACE_ADDRESSES:
#                 place = PLACE_ADDRESSES[str(place)]
            
#             status = "✅ Подтверждена" if res.get("confirmed") else "⏳ В ожидании"
            
#             response += (
#                 f"<b>{i}.</b> {date} в {time}\n"
#                 f"📍 {place}\n"
#                 f"📌 {status}\n\n"
#             )
            
#             # Добавляем кнопку для отмены
#             kb.button(
#                 text=f"❌ Отменить #{i}",
#                 callback_data=f"user_cancel_{res['user_id']}_{res['date']}_{res['time']}"
#             )
        
#         kb.adjust(1)  # По одной кнопке в ряд
        
#         await msg.answer(response, parse_mode="HTML", reply_markup=kb.as_markup())

#     except Exception as e:
#         await msg.answer("⚠️ Ошибка при загрузке ваших бронирований")
#         print(f"Ошибка отмены пользователем: {str(e)}")

# @router.callback_query(F.data.startswith("user_cancel_"))
# async def process_user_cancellation(callback: types.CallbackQuery):
#     try:
#         _, _, uid, date, time = callback.data.split("_")
        
#         # Проверяем, что пользователь отменяет свою бронь
#         if str(callback.from_user.id) != uid:
#             await callback.answer("❌ Вы можете отменить только свои брони", show_alert=True)
#             return
        
#         # Отменяем бронь через API
#         async with httpx.AsyncClient() as client:
#             response = await client.post(
#                 f"{API_URL}/cancel_reservation",
#                 params={
#                     "user_id": uid,
#                     "date": date,
#                     "time": time,
#                     "cancelled_at": datetime.now().isoformat()
#                 }
#             )
            
#             if response.status_code == 200:
#                 result = response.json()
#                 if "error" not in result:
#                     await callback.message.answer("✅ Ваша бронь успешно отменена")
#                     await callback.message.edit_reply_markup(reply_markup=None)
#                 else:
#                     await callback.answer(f"❌ {result['error']}", show_alert=True)
#             else:
#                 await callback.answer("❌ Ошибка при отмене брони", show_alert=True)
    
#     except Exception as e:
#         await callback.answer("❌ Произошла ошибка", show_alert=True)
#         print(f"Ошибка при отмене пользователем: {e}")




@router.message(F.text.lower().in_(["❓ помощь", "помощь"]))
async def help_command(msg: types.Message):
    await msg.answer(
        "Напишите \"📅 Забронировать\", чтобы оставить заявку на столик.\n"
        "Администратор подтвердит вашу бронь в течение нескольких минут."
    )
