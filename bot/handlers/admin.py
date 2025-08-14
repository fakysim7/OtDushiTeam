#bot/handlers/admin.py

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from firebase_admin import db
from datetime import datetime, timedelta
import asyncio
import pandas as pd
import tempfile
import httpx
from config import API_URL, ADMINS

router = Router()

admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🧾 Заявки на подтверждение")],
    [KeyboardButton(text="📈 Статистика")],
    [KeyboardButton(text="📊 Excel отчёт")],
    [KeyboardButton(text="🗑 Очистить старые отмены")],
    [KeyboardButton(text="🔍 Отладка брони")]
], resize_keyboard=True)

PLACE_ADDRESSES = {
    "1": "Пр-т Победителей 85",
    "2": "Пр-т Дзержинского 9"
}

async def cleanup_old_cancelled_reservations():
    """Удаляет отмененные заявки старше 3 дней"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_URL}/cleanup_cancelled")
            return response.json()
    except Exception as e:
        print(f"Cleanup error: {e}")
        return False

async def get_reservations_list():
    """Универсальная функция для получения списка бронирований"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_URL}/get_reservations")
        reservations_response = response.json()
        
        if isinstance(reservations_response, dict):
            return list(reservations_response.values())
        elif isinstance(reservations_response, list):
            return reservations_response
        else:
            raise ValueError("Некорректный формат данных о бронированиях")

@router.message(Command("admin"))
async def admin_panel(msg: types.Message):
    if msg.from_user.id not in ADMINS:
        await msg.answer("⛔ Нет доступа к админ-панели.")
        return
    await msg.answer("🔐 Панель администратора:", reply_markup=admin_menu)

@router.message(F.text.lower() == "🧾 заявки на подтверждение")
async def pending_reservations(msg: types.Message):
    if msg.from_user.id not in ADMINS:
        await msg.answer("⛔ Доступ запрещен")
        return

    try:
        loading_msg = await msg.answer("⏳ Ищу неподтвержденные заявки...")

        reservations = await get_reservations_list()

        # Фильтруем неподтвержденные заявки
        pending_reservations = []
        for res in reservations:
            if isinstance(res, dict):
                confirmed = res.get("confirmed", False)
                cancelled = res.get("cancelled", False)
                status = res.get("status", "")
                
                # Заявка в ожидании если НЕ подтверждена И НЕ отменена
                if not confirmed and not cancelled and status != "cancelled":
                    pending_reservations.append(res)

        await loading_msg.delete()

        if not pending_reservations:
            await msg.answer("✅ Нет неподтвержденных заявок")
            return

        for res in pending_reservations:
            date = res.get('date', 'Не указана')
            time = res.get('time', 'Не указано')
            duration = res.get('duration', 1)
            name = res.get('name', 'Не указано')
            phone = res.get('phone', 'Не указан')
            place = res.get('place', 'Не указано')
            
            # Преобразуем place если это ID
            if str(place) in PLACE_ADDRESSES:
                place = PLACE_ADDRESSES[str(place)]
            
            text = (
                f"📅 {date} ⏰ {time} ({duration} ч)\n"
                f"👤 {name} | 📞 {phone}\n"
                f"📍 {place}"
            )
            
            kb = InlineKeyboardBuilder()
            kb.button(
                text="✅ Подтвердить",
                callback_data=f"approve_{res['user_id']}_{res['date']}_{res['time']}"
            )
            kb.button(
                text="❌ Отменить",
                callback_data=f"cancel_{res['user_id']}_{res['date']}_{res['time']}"
            )
            kb.adjust(2)
            await msg.answer(text, reply_markup=kb.as_markup())

        await msg.answer(f"🔍 Всего неподтвержденных заявок: {len(pending_reservations)}")

    except Exception as e:
        await msg.answer("⚠️ Ошибка при загрузке заявок")
        print(f"Pending reservations error: {e}")
        import traceback
        traceback.print_exc()

@router.message(F.text.lower() == "📈 статистика")
async def statistics(msg: types.Message):
    if msg.from_user.id not in ADMINS:
        return

    try:
        message = "📊 Статистика бронирований за всё время:\n\n"

        reservations = await get_reservations_list()
        valid_reservations = [res for res in reservations if isinstance(res, dict)]

        total = len(valid_reservations)
        confirmed = sum(1 for res in valid_reservations if res.get("confirmed", False))
        cancelled = sum(1 for res in valid_reservations if res.get("cancelled", False))
        preorders = sum(1 for res in valid_reservations if res.get("preorder", False))
        pending = total - confirmed - cancelled

        message += (
            f"🔢 Всего: {total}\n"
            f"✅ Подтверждено: {confirmed}\n"
            f"⏳ В ожидании: {pending}\n"
            f"❌ Отменено: {cancelled}\n"
            f"🍽 С предзаказом: {preorders}\n"
        )

        await msg.answer(message)

    except Exception as e:
        await msg.answer("⚠️ Ошибка при получении статистики")
        print(f"Statistics error: {e}")

@router.message(F.text.lower() == "📊 excel отчёт")
async def excel_export(msg: types.Message):
    if msg.from_user.id not in ADMINS:
        return

    try:
        reservations = await get_reservations_list()
        valid_reservations = [res for res in reservations if isinstance(res, dict)]

        if not valid_reservations:
            await msg.answer("Нет данных для отчёта.")
            return

        # Подготавливаем данные для Excel с русификацией
        excel_data = []
        for res in valid_reservations:
            # Преобразуем place в адрес
            raw_place = res.get('place', 'Не указано')
            place_address = PLACE_ADDRESSES.get(str(raw_place), raw_place) if raw_place != 'Не указано' else 'Не указано'
            
            # Определяем статус на русском
            if res.get("cancelled") or res.get("status") == "cancelled":
                status = "Отменена"
            elif res.get("confirmed") or res.get("status") == "confirmed":
                status = "Подтверждена"
            else:
                status = "В ожидании"
            
            # Формируем запись для Excel
            excel_record = {
                "ID брони": res.get('id', ''),
                "ID пользователя": res.get('user_id', ''),
                "Имя": res.get('name', 'Не указано'),
                "Телефон": res.get('phone', 'Не указан'),
                "Место": place_address,
                "Дата": res.get('date', 'Не указана'),
                "Время": res.get('time', 'Не указано'),
                "Длительность (ч)": res.get('duration', 1),
                "Статус": status,
                "Подтверждена": "Да" if res.get('confirmed') else "Нет",
                "Отменена": "Да" if res.get('cancelled') else "Нет",
                "Предзаказ": "Да" if res.get('preorder') else "Нет",
                "Дата создания": res.get('created_at', 'Не указана'),
                "Дата подтверждения": res.get('confirmed_at', 'Не указана'),
                "Дата отмены": res.get('cancelled_at', 'Не указана'),
                "Дата предзаказа": res.get('preorder_at', 'Не указана')
            }
            excel_data.append(excel_record)

        df = pd.DataFrame(excel_data)

        # Группировка по заведениям для отдельных листов
        places = df["Место"].unique()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as f:
            with pd.ExcelWriter(f.name, engine="openpyxl") as writer:
                
                # Создаем общий лист со всеми данными
                df.to_excel(writer, index=False, sheet_name="Все бронирования")
                
                # Статистика по статусам
                stats_data = {
                    "Статус": ["Всего", "Подтверждено", "В ожидании", "Отменено", "С предзаказом"],
                    "Количество": [
                        len(df),
                        len(df[df["Статус"] == "Подтверждена"]),
                        len(df[df["Статус"] == "В ожидании"]),
                        len(df[df["Статус"] == "Отменена"]),
                        len(df[df["Предзаказ"] == "Да"])
                    ]
                }
                stats_df = pd.DataFrame(stats_data)
                stats_df.to_excel(writer, index=False, sheet_name="Статистика")
                
                # Создаем отдельные листы для каждого заведения
                for place in places:
                    if pd.notna(place) and place != 'Не указано':
                        sheet_df = df[df["Место"] == place]
                        # Обрезаем название листа до 31 символа (ограничение Excel)
                        sheet_name = place[:31] if len(place) <= 31 else place[:28] + "..."
                        
                        if not sheet_df.empty:
                            sheet_df.to_excel(writer, index=False, sheet_name=sheet_name)

            await msg.answer_document(
                types.FSInputFile(f.name, filename="отчет_бронирования.xlsx"),
                caption="📊 Отчёт по бронированиям\n\n"
                       f"📈 Листы:\n"
                       f"• Все бронирования\n"
                       f"• Статистика\n" +
                       "\n".join([f"• {place}" for place in places if place != 'Не указано'])
            )

    except Exception as e:
        await msg.answer("⚠️ Ошибка при создании отчёта")
        print(f"Excel export error: {e}")
        import traceback
        traceback.print_exc()

@router.message(F.text.lower() == "🗑 очистить старые отмены")
async def manual_cleanup(msg: types.Message):
    if msg.from_user.id not in ADMINS:
        return
    
    loading_msg = await msg.answer("🗑 Очищаю старые отмененные заявки...")
    result = await cleanup_old_cancelled_reservations()
    await loading_msg.delete()
    
    if result:
        deleted_count = result.get('deleted_count', 0)
        await msg.answer(f"✅ Очистка завершена\n🗑 Удалено записей: {deleted_count}")
    else:
        await msg.answer("⚠️ Ошибка при очистке")

@router.message(F.text.lower() == "🔍 отладка брони")
async def debug_reservation(msg: types.Message):
    if msg.from_user.id not in ADMINS:
        return
    
    await msg.answer("Введите данные брони в формате:\nuser_id date time\n\nНапример: 123456789 2025-08-21 16:00")

@router.message(F.text.regexp(r'^\d+\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$'))
async def process_debug_request(msg: types.Message):
    if msg.from_user.id not in ADMINS:
        return
    
    try:
        parts = msg.text.strip().split()
        user_id, date, time = parts[0], parts[1], parts[2]
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/check_reservation_status",
                params={"user_id": user_id, "date": date, "time": time}
            )
            result = response.json()
            
            if result.get("found"):
                reservation = result["reservation"]
                status_text = (
                    f"🔍 <b>Отладка брони</b>\n\n"
                    f"📝 ID: {result['id']}\n"
                    f"👤 User ID: {reservation.get('user_id')}\n"
                    f"📅 Дата: {reservation.get('date')}\n"
                    f"⏰ Время: {reservation.get('time')}\n"
                    f"✅ Подтверждена: {reservation.get('confirmed', False)}\n"
                    f"❌ Отменена: {reservation.get('cancelled', False)}\n"
                    f"🍽 Предзаказ: {reservation.get('preorder', False)}\n"
                    f"🏷 Статус: {reservation.get('status', 'не указан')}\n"
                    f"📞 Телефон: {reservation.get('phone', 'не указан')}\n"
                    f"👤 Имя: {reservation.get('name', 'не указано')}\n"
                )
                
                if reservation.get('cancelled_at'):
                    status_text += f"⏰ Отменена: {reservation['cancelled_at']}\n"
                
                if reservation.get('preorder_at'):
                    status_text += f"🍽 Предзаказ отмечен: {reservation['preorder_at']}\n"
                    
                await msg.answer(status_text, parse_mode="HTML")
            else:
                await msg.answer("❌ Бронь не найдена")
                
    except Exception as e:
        await msg.answer(f"⚠️ Ошибка: {e}")

@router.callback_query(F.data.startswith("approve_"))
async def confirm_res(callback: types.CallbackQuery):
    try:
        _, uid, date, time = callback.data.split("_")

        async with httpx.AsyncClient() as client:
            await client.post(
                f"{API_URL}/confirm",
                params={"user_id": uid, "date": date, "time": time}
            )

        reservations = await get_reservations_list()
        res = next(
            (r for r in reservations if
             isinstance(r, dict) and 
             str(r.get("user_id")) == uid and
             r.get("date") == date and
             r.get("time") == time),
            None
        )

        if not res:
            await callback.message.answer("⚠️ Бронь подтверждена, но не удалось найти детали.")
            return

        raw_place = res.get("place", "заведение не указано")
        place = PLACE_ADDRESSES.get(str(raw_place), raw_place)
        duration = res.get("duration", 1)
        name = res.get("name", "Пользователь")

        # Создаем кнопку для пометки предзаказа
        kb = InlineKeyboardBuilder()
        kb.button(
            text="🍽 Отметить предзаказ",
            callback_data=f"preorder_{uid}_{date}_{time}"
        )

        await callback.message.answer(
            f"✅ Бронь подтверждена\n👤 {name}\n\n"
            f"📅 {date} ⏰ {time}\n📍 {place}",
            reply_markup=kb.as_markup()
        )

        await callback.bot.send_message(
            int(uid),
            f"✅ Ваша бронь подтверждена!\n"
            f"📅 Дата: {date}\n"
            f"⏰ Время: {time} ({duration} ч)\n"
            f"📍 Заведение: {place}\n"
            "Ждём вас! 🤗"
        )

        # Убираем кнопки подтверждения/отмены из исходного сообщения
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except:
            pass

    except Exception as e:
        await callback.message.answer("⚠️ Ошибка при подтверждении брони")
        print(f"Confirm reservation error: {e}")

@router.callback_query(F.data.startswith("preorder_"))
async def mark_preorder(callback: types.CallbackQuery):
    try:
        _, uid, date, time = callback.data.split("_")

        # Помечаем предзаказ через API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/mark_preorder",
                params={
                    "user_id": uid,
                    "date": date,
                    "time": time,
                    "preorder_at": datetime.now().isoformat()
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                if "error" not in result:
                    await callback.message.answer("🍽 Предзаказ отмечен ✅")
                    
                    # Убираем кнопку предзаказа
                    try:
                        await callback.message.edit_reply_markup(reply_markup=None)
                    except:
                        pass
                else:
                    await callback.message.answer(f"⚠️ {result['error']}")
            else:
                await callback.message.answer("⚠️ Ошибка при отметке предзаказа")

    except Exception as e:
        await callback.message.answer("⚠️ Ошибка при отметке предзаказа")
        print(f"Mark preorder error: {e}")

@router.callback_query(F.data.startswith("cancel_"))
async def cancel_reservation(callback: types.CallbackQuery):
    try:
        _, uid, date, time = callback.data.split("_")
        print(f"BOT: Attempting to cancel reservation:")
        print(f"  user_id: {uid}")
        print(f"  date: {date}")
        print(f"  time: {time}")

        # Получаем информацию о брони
        reservations = await get_reservations_list()
        res = next(
            (r for r in reservations if
             isinstance(r, dict) and 
             str(r.get("user_id")) == uid and
             r.get("date") == date and
             r.get("time") == time),
            None
        )

        if not res:
            await callback.message.answer("⚠️ Бронь не найдена в списке")
            return

        print(f"BOT: Found reservation to cancel: {res}")

        # Отменяем бронь через API
        async with httpx.AsyncClient() as client:
            print(f"BOT: Sending API request to cancel reservation")
            response = await client.post(
                f"{API_URL}/cancel_reservation",
                params={
                    "user_id": uid, 
                    "date": date, 
                    "time": time,
                    "cancelled_at": datetime.now().isoformat()
                }
            )
            
            print(f"BOT: API response status: {response.status_code}")
            result = response.json()
            print(f"BOT: API response body: {result}")
            
            if response.status_code != 200:
                await callback.message.answer(f"⚠️ Ошибка API: {response.status_code}")
                return
                
            if "error" in result:
                await callback.message.answer(f"⚠️ {result['error']}")
                
                # Дополнительная отладка - проверим статус брони через отдельный API
                debug_response = await client.get(
                    f"{API_URL}/check_reservation_status",
                    params={"user_id": uid, "date": date, "time": time}
                )
                debug_result = debug_response.json()
                print(f"BOT: Debug check result: {debug_result}")
                
                if debug_result.get("found"):
                    await callback.message.answer(
                        f"🔍 <b>Отладка:</b>\n"
                        f"Бронь найдена в базе:\n"
                        f"ID: {debug_result['id']}\n"
                        f"Cancelled: {debug_result['reservation'].get('cancelled', 'не указано')}\n"
                        f"Status: {debug_result['reservation'].get('status', 'не указано')}",
                        parse_mode="HTML"
                    )
                return

        # Формируем сообщение об успешной отмене
        raw_place = res.get("place", "заведение не указано")
        place = PLACE_ADDRESSES.get(str(raw_place), raw_place)
        duration = res.get("duration", 1)
        name = res.get("name", "Пользователь")

        await callback.message.answer(f"✅ Бронь отменена\n👤 {name}")

        # Уведомляем пользователя
        try:
            await callback.bot.send_message(
                int(uid),
                f"❌ Ваша бронь была отменена администратором\n\n"
                f"📅 Дата: {date}\n"
                f"⏰ Время: {time} ({duration} ч)\n"
                f"📍 Заведение: {place}\n\n"
                f"Если у вас есть вопросы, свяжитесь с нами.\n\n"
                f"ℹ️ Информация об отмененной брони будет удалена через 3 дня."
            )
        except Exception as e:
            print(f"Failed to notify user {uid}: {e}")

        # Обновляем сообщение с кнопками (убираем кнопки)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except:
            pass

    except Exception as e:
        await callback.message.answer("⚠️ Ошибка при отмене брони")
        print(f"Cancel reservation error: {e}")
        import traceback
        traceback.print_exc()