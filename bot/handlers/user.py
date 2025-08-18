#bot/hundlers/user.py
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
import httpx
from config import API_URL
from datetime import datetime
from keyboards.main import main_menu
from russian_calendar import RussianCalendar, CalendarCallback
from keyboards.inline import duration_kb, dynamic_hours_kb, place_kb
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
    selected, selected_date = await RussianCalendar().process_selection(callback_query, callback_data)

    if not selected:
        # Нажата навигация или недоступный день — ничего не делаем (alert уже показан в календаре)
        return

    # Здесь можно не проверять снова прошедшую дату — календарь сам блокирует их и показывает alert

    await state.update_data(date=selected_date.strftime("%Y-%m-%d"))
    await callback_query.message.answer(
        f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}\nВыберите время:",
        reply_markup=dynamic_hours_kb()
    )
    await state.set_state(ReserveState.time)

@router.callback_query(F.data == "ignore", ReserveState.date)
async def ignore_past_date(callback: types.CallbackQuery):
    await callback.answer(
        "Нельзя выбирать прошедшую дату, выберите другой день.",
        show_alert=False  # Это toast!
    )
    
@router.callback_query(F.data.startswith("time_"), ReserveState.time)
async def select_time(callback: types.CallbackQuery, state: FSMContext):
    time = callback.data.split("_")[1]
    await state.update_data(time=time)
    await callback.message.answer("⏱ Укажите продолжительность (в часах):", reply_markup=duration_kb())
    await state.set_state(ReserveState.duration)

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
        
        # Получаем данные из состояния
        user_data = await state.get_data()
        
        # Отправляем запрос в API
        await make_api_request(
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
        
        await msg.answer("✅ Бронь успешно отправлена! Ожидайте подтверждения.\n" \
                        "А пока можете ознакомиться с наши меню https://amelie-cafe.by/menu")
        await state.clear()  # Очищаем состояние только при успехе
        
    except NumberParseException:
        await msg.answer(
            "⚠️ Пожалуйста, введите корректный номер телефона в международном формате.\n"
            "Примеры:\n"
            "+375 33 777 77 77 (Беларусь)\n"
            "+44 20 1234 5678 (Великобритания)\n"
            "+49 30 1234567 (Германия)\n"
            "+7 912 345 67 89 (Россия)\n\n"
            "Попробуйте ввести номер еще раз:"
        )
        # Не очищаем состояние, чтобы пользователь мог повторить ввод
        return
        
    except Exception as e:
        await msg.answer(
            f"⛔ Произошла ошибка: {str(e)}\n"
            "Пожалуйста, введите номер телефона еще раз:"
        )
        # Не очищаем состояние при других ошибках
        return




# В начале файла user.py добавить константы
PLACE_ADDRESSES = {
    "1": "Пр-т Победителей 85",
    "2": "Пр-т Дзержинского 9"
}

@router.message(F.text.lower().in_(["📋 мои брони", "мои брони"]))
async def my_reservations(msg: types.Message):
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
            if isinstance(res, dict) and str(res.get("user_id")) == str(msg.from_user.id)
        ]

        if not user_reservations:
            await msg.answer("У вас нет бронирований.")
            return

        # Сортируем по дате и времени
        user_reservations.sort(key=lambda x: (x.get("date", ""), x.get("time", "")))

        response = "📋 <b>Ваши брони:</b>\n\n"
        
        for i, res in enumerate(user_reservations, 1):
            # Определяем статус брони
            if res.get("cancelled") or res.get("status") == "cancelled":
                status = "❌ Отменена"
                status_icon = "❌"
            elif res.get("confirmed") or res.get("status") == "confirmed":
                status = "✅ Подтверждена"
                status_icon = "✅"
            else:
                status = "⏳ В ожидании"
                status_icon = "⏳"
            
            # Преобразуем ID места в адрес
            raw_place = res.get('place', 'Не указано')
            if str(raw_place) in PLACE_ADDRESSES:
                place = PLACE_ADDRESSES[str(raw_place)]
            else:
                place = raw_place if raw_place != 'Не указано' else 'Не указано'
            
            response += (
                f"{status_icon} <b>Бронь #{i}</b>\n"
                f"👤 Имя: {res.get('name', 'Не указано')}\n"
                f"🏠 Место: {place}\n"
                f"📅 Дата: {res.get('date', 'Не указана')}\n"
                f"⏰ Время: {res.get('time', 'Не указано')}\n"
                f"⏱ Длительность: {res.get('duration', 'Не указана')} ч\n"
                f"📞 Телефон: {res.get('phone', 'Не указан')}\n"
                f"📌 Статус: {status}\n"
            )
            
            # Добавляем информацию о дате отмены если есть
            if res.get("cancelled_at"):
                try:
                    cancelled_date = datetime.fromisoformat(res["cancelled_at"])
                    response += f"🕒 Отменена: {cancelled_date.strftime('%d.%m.%Y %H:%M')}\n"
                except:
                    pass
            
            # Добавляем информацию о дате подтверждения если есть
            elif res.get("confirmed_at"):
                try:
                    confirmed_date = datetime.fromisoformat(res["confirmed_at"])
                    response += f"🕒 Подтверждена: {confirmed_date.strftime('%d.%m.%Y %H:%M')}\n"
                except:
                    pass
            
            response += "\n"
        
        await msg.answer(response, parse_mode="HTML")

    except Exception as e:
        await msg.answer(
            "⚠️ Произошла ошибка при получении бронирований.\n"
            "Попробуйте позже или обратитесь в поддержку."
        )
        print(f"Ошибка при получении бронирований: {str(e)}")


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
