#bot/handlers/admin.py

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from firebase_admin import db
from utils.admin_notify import notify_admin_new_booking
from keyboards.inline import confirm_button
import aiohttp
import pytz
from datetime import datetime, timedelta
import asyncio
import pandas as pd
import tempfile
import httpx
from config import API_URL, ADMINS

router = Router()

admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🧾 Заявки на подтверждение")],
    [KeyboardButton(text="📋 Все брони"), KeyboardButton(text="✅ Активные брони")],
    [KeyboardButton(text="📈 Статистика")],
    [KeyboardButton(text="📊 Excel отчёт")],
    [KeyboardButton(text="🗑 Очистить старые отмены")],
    [KeyboardButton(text="🗂 Прочее")],  # Новая кнопка
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

# ЗАМЕНИТЕ функцию excel_export в файле admin.py

@router.message(F.text.lower() == "📊 excel отчёт")
async def excel_export(msg: types.Message):
    if msg.from_user.id not in ADMINS:
        return

    try:
        import pytz
        
        reservations = await get_reservations_list()
        valid_reservations = [res for res in reservations if isinstance(res, dict)]

        if not valid_reservations:
            await msg.answer("Нет данных для отчёта.")
            return

        # Московская временная зона
        moscow_tz = pytz.timezone('Europe/Moscow')

        def convert_to_moscow_time(timestamp_str):
            """Конвертирует timestamp в московское время"""
            if not timestamp_str or timestamp_str == 'Не указана':
                return 'Не указана'
            
            try:
                # Парсим timestamp
                utc_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                if utc_time.tzinfo is None:
                    # Если нет информации о зоне, считаем что UTC
                    utc_time = utc_time.replace(tzinfo=pytz.UTC)
                
                # Конвертируем в МСК
                moscow_time = utc_time.astimezone(moscow_tz)
                return moscow_time.strftime('%d.%m.%Y %H:%M')
            except Exception as e:
                print(f"DEBUG: Ошибка конвертации времени {timestamp_str}: {e}")
                return timestamp_str

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
            
            # Форматируем дату создания (если есть created_at)
            created_at_moscow = 'Не указана'
            if res.get('created_at'):
                created_at_moscow = convert_to_moscow_time(res['created_at'])
            
            # Формируем запись для Excel
            excel_record = {
                # "ID брони": res.get('id', ''),
                # "ID пользователя": res.get('user_id', ''),
                "Имя": res.get('name', 'Не указано'),
                "Телефон": res.get('phone', 'Не указан'),
                "Место": place_address,
                "Дата": res.get('date', 'Не указана'),
                "Время": res.get('time', 'Не указано'),
                "Длительность (ч)": res.get('duration', 1),
                "Статус": status,
                # "Подтверждена": "Да" if res.get('confirmed') else "Нет",
                "Отменена": "Да" if res.get('cancelled') else "Нет",
                "Предзаказ": "Да" if res.get('preorder') else "Нет",
                # "Дата создания": created_at_moscow,
                "Дата подтверждения": convert_to_moscow_time(res.get('confirmed_at', 'Не указана')),
                "Дата отмены": convert_to_moscow_time(res.get('cancelled_at', 'Не указана')),
                "Дата предзаказа": convert_to_moscow_time(res.get('preorder_at', 'Не указана'))
            }
            excel_data.append(excel_record)

        df = pd.DataFrame(excel_data)

        # Группировка по заведениям для отдельных листов
        places = df["Место"].unique()
        
        # Добавляем текущее московское время в название файла
        current_moscow_time = datetime.now(moscow_tz)
        timestamp = current_moscow_time.strftime('%Y%m%d_%H%M')
        
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
                
                # Добавляем информацию о времени генерации
                info_data = {
                    "Параметр": [
                        "Дата генерации отчета", 
                        "Время генерации", 
                        "Всего записей",
                        "Временная зона данных"
                    ],
                    "Значение": [
                        current_moscow_time.strftime('%d.%m.%Y'),
                        current_moscow_time.strftime('%H:%M'),
                        len(df),
                        "Московское время (UTC+3)"
                    ]
                }
                info_df = pd.DataFrame(info_data)
                
                # Объединяем статистику и информацию
                combined_stats = pd.concat([info_df, pd.DataFrame([["", ""]], columns=["Параметр", "Значение"]), stats_df], ignore_index=True)
                combined_stats.to_excel(writer, index=False, sheet_name="Статистика")
                
                # Создаем отдельные листы для каждого заведения
                for place in places:
                    if pd.notna(place) and place != 'Не указано':
                        sheet_df = df[df["Место"] == place]
                        # Обрезаем название листа до 31 символа (ограничение Excel)
                        sheet_name = place[:31] if len(place) <= 31 else place[:28] + "..."
                        
                        if not sheet_df.empty:
                            sheet_df.to_excel(writer, index=False, sheet_name=sheet_name)

            # Формируем описание файла
            caption_text = (
                f"📊 Отчёт по бронированиям\n"
                f"🕐 Создан: {current_moscow_time.strftime('%d.%m.%Y в %H:%M')}\n\n"
                f"📈 Листы:\n"
                f"• Все бронирования (полный список)\n"
                f"• Статистика (сводная информация)\n"
            )
            
            # Добавляем информацию о листах заведений
            for place in places:
                if place != 'Не указано':
                    place_count = len(df[df["Место"] == place])
                    caption_text += f"• {place} ({place_count} брон.)\n"
            

            await msg.answer_document(
                types.FSInputFile(f.name, filename=f"отчет_бронирования_{timestamp}.xlsx"),
                caption=caption_text
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

async def format_reservation_admin(res: dict, number: int, status_icon: str) -> str:
    """Форматирует бронирование для админской панели с московским временем"""
    import pytz
    
    # Преобразуем ID места в адрес
    raw_place = res.get('place', 'Не указано')
    if str(raw_place) in PLACE_ADDRESSES:
        place = PLACE_ADDRESSES[str(raw_place)]
    else:
        place = raw_place if raw_place != 'Не указано' else 'Не указано'
    
    formatted = (
        f"{status_icon} <b>Бронь #{number}</b>\n"
        f"👤 {res.get('name', 'Не указано')} | 📞 {res.get('phone', 'Не указан')}\n"
        f"📍 {place}\n"
        f"📅 {res.get('date', 'Не указана')} ⏰ {res.get('time', 'Не указано')} ({res.get('duration', 1)} ч)\n"
    )
    
    # Московская временная зона
    moscow_tz = pytz.timezone('Europe/Moscow')
    
    # Добавляем информацию о предзаказе
    if res.get("preorder"):
        formatted += f"🍽 Предзаказ отмечен\n"
        if res.get("preorder_at"):
            try:
                preorder_utc = datetime.fromisoformat(res["preorder_at"].replace('Z', '+00:00'))
                if preorder_utc.tzinfo is None:
                    preorder_utc = preorder_utc.replace(tzinfo=pytz.UTC)
                preorder_moscow = preorder_utc.astimezone(moscow_tz)
                formatted += f"🕑 Предзаказ: {preorder_moscow.strftime('%d.%m.%Y %H:%M')} \n"
            except:
                pass
    
    # Добавляем информацию о времени операций
    if res.get("cancelled_at"):
        try:
            cancelled_utc = datetime.fromisoformat(res["cancelled_at"].replace('Z', '+00:00'))
            if cancelled_utc.tzinfo is None:
                cancelled_utc = cancelled_utc.replace(tzinfo=pytz.UTC)
            cancelled_moscow = cancelled_utc.astimezone(moscow_tz)
            formatted += f"🕑 Отменена: {cancelled_moscow.strftime('%d.%m.%Y %H:%M')} \n"
        except:
            pass
    elif res.get("confirmed_at"):
        try:
            confirmed_utc = datetime.fromisoformat(res["confirmed_at"].replace('Z', '+00:00'))
            if confirmed_utc.tzinfo is None:
                confirmed_utc = confirmed_utc.replace(tzinfo=pytz.UTC)
            confirmed_moscow = confirmed_utc.astimezone(moscow_tz)
            formatted += f"🕑 Подтверждена: {confirmed_moscow.strftime('%d.%m.%Y %H:%M')} \n"
        except:
            pass
            
    return formatted


@router.message(F.text.lower() == "📋 все брони")
async def view_all_reservations(msg: types.Message):
    if msg.from_user.id not in ADMINS:
        await msg.answer("⛔ Доступ запрещен")
        return

    try:
        loading_msg = await msg.answer("⏳ Загружаю все бронирования...")

        reservations = await get_reservations_list()
        valid_reservations = [res for res in reservations if isinstance(res, dict)]

        await loading_msg.delete()

        if not valid_reservations:
            await msg.answer("📭 Нет бронирований в системе")
            return

        # Сортируем по дате и времени (сначала новые)
        valid_reservations.sort(key=lambda x: (x.get("date", ""), x.get("time", "")), reverse=True)

        # Разбиваем на страницы (по 5 бронирований на сообщение)
        page_size = 5
        total_pages = (len(valid_reservations) + page_size - 1) // page_size

        for page in range(total_pages):
            start_idx = page * page_size
            end_idx = min((page + 1) * page_size, len(valid_reservations))
            page_reservations = valid_reservations[start_idx:end_idx]

            response = f"📋 <b>Все бронирования</b> (стр. {page + 1}/{total_pages})\n\n"

            for i, res in enumerate(page_reservations, start_idx + 1):
                # Определяем статус и иконку
                if res.get("cancelled") or res.get("status") == "cancelled":
                    status_icon = "❌"
                    status = "Отменена"
                elif res.get("confirmed") or res.get("status") == "confirmed":
                    status_icon = "✅"
                    status = "Подтверждена"
                else:
                    status_icon = "⏳"
                    status = "В ожидании"

                # Преобразуем место
                raw_place = res.get('place', 'Не указано')
                place = PLACE_ADDRESSES.get(str(raw_place), raw_place)

                response += (
                    f"{status_icon} <b>#{i}</b> {res.get('name', 'Не указано')}\n"
                    f"📞 {res.get('phone', 'Не указан')}\n"
                    f"📍 {place}\n"
                    f"📅 {res.get('date', '')} ⏰ {res.get('time', '')} ({res.get('duration', 1)} ч)\n"
                    f"📌 {status}"
                )

                # Добавляем предзаказ если есть
                if res.get("preorder"):
                    response += " 🍽"

                response += "\n\n"

            # Добавляем кнопки управления для неподтвержденных бронирований на последней странице
            if page == total_pages - 1:
                response += f"📊 <b>Всего бронирований:</b> {len(valid_reservations)}\n"
                response += f"✅ Подтверждено: {sum(1 for r in valid_reservations if r.get('confirmed'))}\n"
                response += f"⏳ В ожидании: {sum(1 for r in valid_reservations if not r.get('confirmed') and not r.get('cancelled'))}\n"
                response += f"❌ Отменено: {sum(1 for r in valid_reservations if r.get('cancelled'))}"

            await msg.answer(response, parse_mode="HTML")

    except Exception as e:
        await msg.answer("⚠️ Ошибка при загрузке бронирований")
        print(f"View all reservations error: {e}")
        import traceback
        traceback.print_exc()


@router.message(F.text.lower() == "✅ активные брони")
async def view_active_reservations(msg: types.Message):
    if msg.from_user.id not in ADMINS:
        await msg.answer("⛔ Доступ запрещен")
        return

    try:
        import pytz
        loading_msg = await msg.answer("⏳ Загружаю активные бронирования...")

        reservations = await get_reservations_list()
        
        # Фильтруем только активные бронирования (подтвержденные и предстоящие)
        moscow_tz = pytz.timezone('Europe/Moscow')
        current_date_moscow = datetime.now(moscow_tz).date()
        
        active_reservations = []
        for res in reservations:
            if isinstance(res, dict):
                # Проверяем что бронь подтверждена и не отменена
                is_confirmed = res.get("confirmed", False)
                is_cancelled = res.get("cancelled", False) or res.get("status") == "cancelled"
                
                if is_confirmed and not is_cancelled:
                    # Проверяем что дата не прошла
                    try:
                        reservation_date = datetime.strptime(res.get('date', ''), '%Y-%m-%d').date()
                        if reservation_date >= current_date_moscow:
                            active_reservations.append(res)
                    except ValueError:
                        continue  # Пропускаем брони с некорректной датой

        await loading_msg.delete()

        if not active_reservations:
            await msg.answer("📭 Нет активных бронирований")
            return

        # Сортируем по дате и времени (сначала ближайшие)
        active_reservations.sort(key=lambda x: (x.get("date", ""), x.get("time", "")))

        # Показываем каждую бронь отдельным сообщением для удобства
        for i, res in enumerate(active_reservations, 1):
            # Преобразуем место
            raw_place = res.get('place', 'Не указано')
            place = PLACE_ADDRESSES.get(str(raw_place), raw_place)

            # Форматируем дату для лучшего отображения
            try:
                reservation_date = datetime.strptime(res.get('date', ''), '%Y-%m-%d').date()
                if reservation_date == current_date_moscow:
                    date_display = f"{reservation_date.strftime('%d.%m.%Y')} (сегодня)"
                elif reservation_date == current_date_moscow + timedelta(days=1):
                    date_display = f"{reservation_date.strftime('%d.%m.%Y')} (завтра)"
                else:
                    date_display = reservation_date.strftime('%d.%m.%Y')
            except:
                date_display = res.get('date', 'Не указана')

            # Проверяем статус предзаказа
            has_preorder = res.get("preorder", False)
            
            response = (
                f"✅ <b>Активная бронь #{i}</b>\n"
                f"👤 {res.get('name', 'Не указано')}\n"
                f"📞 {res.get('phone', 'Не указан')}\n"
                f"📍 {place}\n"
                f"📅 {date_display} ⏰ {res.get('time', '')} ({res.get('duration', 1)} ч)\n"
            )

            # Показываем статус предзаказа
            if has_preorder:
                response += "🍽 <b>Предзаказ отмечен</b>\n"
                
                # Показываем время отметки предзаказа если есть
                if res.get("preorder_at"):
                    try:
                        import pytz
                        moscow_tz = pytz.timezone('Europe/Moscow')
                        preorder_utc = datetime.fromisoformat(res["preorder_at"].replace('Z', '+00:00'))
                        if preorder_utc.tzinfo is None:
                            preorder_utc = preorder_utc.replace(tzinfo=pytz.UTC)
                        preorder_moscow = preorder_utc.astimezone(moscow_tz)
                        response += f"🕑 Отмечен: {preorder_moscow.strftime('%d.%m %H:%M')} МСК\n"
                    except:
                        pass

            # Создаем клавиатуру в зависимости от статуса предзаказа
            kb = InlineKeyboardBuilder()
            
            if has_preorder:
                # Если предзаказ уже есть - показываем только кнопку отмены брони
                kb.button(
                    text="❌ Отменить бронь",
                    callback_data=f"cancel_{res['user_id']}_{res['date']}_{res['time']}"
                )
                kb.button(
                    text="🗑 Снять предзаказ", 
                    callback_data=f"remove_preorder_{res['user_id']}_{res['date']}_{res['time']}"
                )
                kb.adjust(1)
            else:
                # Если предзаказа нет - показываем обе кнопки
                kb.button(
                    text="🍽 Отметить предзаказ",
                    callback_data=f"preorder_{res['user_id']}_{res['date']}_{res['time']}"
                )
                kb.button(
                    text="❌ Отменить бронь",
                    callback_data=f"cancel_{res['user_id']}_{res['date']}_{res['time']}"
                )
                kb.adjust(2)  # Две кнопки в ряд

            await msg.answer(response, parse_mode="HTML", reply_markup=kb.as_markup())

        # Показываем общую статистику
        stats_response = (
            f"📊 <b>Статистика активных бронирований:</b>\n\n"
            f"✅ Всего активных: {len(active_reservations)}\n"
            f"🍽 С предзаказом: {sum(1 for r in active_reservations if r.get('preorder'))}\n"
            f"📋 Без предзаказа: {sum(1 for r in active_reservations if not r.get('preorder'))}\n"
        )
        
        # Группируем по заведениям
        place_stats = {}
        preorder_by_place = {}
        
        for res in active_reservations:
            raw_place = res.get('place', 'Не указано')
            place = PLACE_ADDRESSES.get(str(raw_place), raw_place)
            
            place_stats[place] = place_stats.get(place, 0) + 1
            
            if res.get('preorder'):
                preorder_by_place[place] = preorder_by_place.get(place, 0) + 1
        
        stats_response += "\n📍 <b>По заведениям:</b>\n"
        for place, count in place_stats.items():
            preorder_count = preorder_by_place.get(place, 0)
            stats_response += f"• {place}: {count} (🍽 {preorder_count})\n"

        await msg.answer(stats_response, parse_mode="HTML")

    except Exception as e:
        await msg.answer("⚠️ Ошибка при загрузке активных бронирований")
        print(f"View active reservations error: {e}")
        import traceback
        traceback.print_exc()


# ДОБАВЬТЕ новый обработчик для снятия предзаказа

@router.callback_query(F.data.startswith("remove_preorder_"))
async def remove_preorder(callback: types.CallbackQuery):
    try:
        _, _, uid, date, time = callback.data.split("_")

        # Снимаем предзаказ через API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/remove_preorder",
                params={
                    "user_id": uid,
                    "date": date,
                    "time": time
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                if "error" not in result:
                    await callback.message.answer("🗑 Предзаказ снят")
                    
                    # Убираем кнопки из исходного сообщения
                    try:
                        await callback.message.edit_reply_markup(reply_markup=None)
                    except:
                        pass
                        
                    # Обновляем отображение брони
                    await callback.answer("Предзаказ успешно снят ✅")
                else:
                    await callback.message.answer(f"⚠️ {result['error']}")
            else:
                await callback.message.answer("⚠️ Ошибка при снятии предзаказа")

    except Exception as e:
        await callback.message.answer("⚠️ Ошибка при снятии предзаказа")
        print(f"Remove preorder error: {e}")



@router.message(F.text == "🗂 Прочее")
async def show_misc_menu(message: Message):
    """Показать старые брони для удаления"""
    if message.from_user.id not in ADMINS:
        return
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}/get_old_reservations?months_back=2") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    old_reservations = data.get("old_reservations", {})
                else:
                    await message.answer("❌ Ошибка получения данных")
                    return
        
        if not old_reservations:
            await message.answer("📝 Старых броней (2+ месяца) не найдено")
            return
        
        total_count = len(old_reservations)
        text = f"🗂 <b>Старые брони</b> (старше 2 месяцев)\n"
        text += f"Всего найдено: {total_count}\n\n"
        
        # Показываем первые 10 броней
        count = 0
        builder = InlineKeyboardBuilder()
        
        for res_id, reservation in old_reservations.items():
            if count >= 10:  # Ограничиваем показ 10 бронями
                text += f"\n... и еще {total_count - 10} броней"
                break
                
            name = reservation.get("name", "Неизвестно")
            date = reservation.get("date", "Не указана")
            time = reservation.get("time", "Не указано")
            days_ago = reservation.get("days_ago", 0)
            place = reservation.get("place", "")
            
            # Определяем заведение
            place_names = {
                "place_1": "Пр-т Победителей 85",
                "place_2": "Пр-т Дзержинского 9"
            }
            place_display = place_names.get(place, place)
            
            # Статус
            status = "✅" if reservation.get("confirmed") else "⏳"
            if reservation.get("cancelled"):
                status = "❌"
            
            count += 1
            text += f"{count}. {status} <b>{name}</b>\n"
            text += f"   📅 {date} в {time} ({days_ago} дн. назад)\n"
            text += f"   📍 {place_display}\n"
            text += f"   🆔 {res_id[:8]}...\n\n"
            
            # Добавляем кнопку для удаления этой брони
            builder.button(
                text=f"🗑 Удалить {name} ({date})", 
                callback_data=f"delete_old_{res_id}"
            )
        
        builder.adjust(1)  # По одной кнопке в ряд
        
        # Добавляем кнопку "Удалить все старые"
        if total_count > 0:
            builder.button(text="🗑 Удалить ВСЕ старые брони", callback_data="delete_all_old")
        
        await message.answer(
            text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        print(f"Error in misc menu: {e}")
        await message.answer("❌ Произошла ошибка при получении старых броней")


@router.callback_query(F.data.startswith("delete_old_"))
async def delete_single_old_reservation(callback: CallbackQuery):
    """Удалить одну старую бронь"""
    reservation_id = callback.data.replace("delete_old_", "")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(f"{API_URL}/delete_reservation/{reservation_id}") as resp:
                if resp.status == 200:
                    result = await resp.json()
                    deleted_reservation = result.get("deleted_reservation", {})
                    name = deleted_reservation.get("name", "Неизвестно")
                    date = deleted_reservation.get("date", "Неизвестно")
                    
                    await callback.answer(f"✅ Бронь {name} ({date}) удалена", show_alert=True)
                    
                    # Обновляем сообщение - показываем актуальный список
                    await callback.message.edit_text(
                        f"✅ <b>Бронь удалена</b>\n\n"
                        f"👤 {name}\n"
                        f"📅 {date}\n"
                        f"🆔 {reservation_id[:8]}...\n\n"
                        f"Для обновления списка нажмите 'Прочее' снова.",
                        parse_mode="HTML"
                    )
                else:
                    await callback.answer("❌ Ошибка при удалении", show_alert=True)
                    
    except Exception as e:
        print(f"Error deleting reservation: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "delete_all_old")
async def confirm_delete_all_old(callback: CallbackQuery):
    """Подтверждение удаления всех старых броней"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить ВСЕ", callback_data="confirm_delete_all_old")
    builder.button(text="❌ Нет, отменить", callback_data="cancel_delete_all")
    
    await callback.message.edit_text(
        "⚠️ <b>Подтверждение удаления</b>\n\n"
        "Вы уверены, что хотите удалить ВСЕ старые брони (старше 2 месяцев)?\n\n"
        "⚠️ Это действие нельзя отменить!",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "confirm_delete_all_old")
async def delete_all_old_reservations(callback: CallbackQuery):
    """Удалить все старые брони"""
    try:
        # Сначала получаем список старых броней
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}/get_old_reservations?months_back=2") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    old_reservations = data.get("old_reservations", {})
                else:
                    await callback.answer("❌ Ошибка получения данных", show_alert=True)
                    return
        
        if not old_reservations:
            await callback.message.edit_text("📝 Старых броней не найдено")
            return
        
        # Удаляем каждую бронь
        deleted_count = 0
        failed_count = 0
        
        for res_id in old_reservations.keys():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.delete(f"{API_URL}/delete_reservation/{res_id}") as resp:
                        if resp.status == 200:
                            deleted_count += 1
                        else:
                            failed_count += 1
            except:
                failed_count += 1
        
        result_text = f"🗑 <b>Массовое удаление завершено</b>\n\n"
        result_text += f"✅ Удалено: {deleted_count}\n"
        if failed_count > 0:
            result_text += f"❌ Ошибок: {failed_count}\n"
        result_text += f"\nВсего обработано: {len(old_reservations)}"
        
        await callback.message.edit_text(result_text, parse_mode="HTML")
        await callback.answer(f"✅ Удалено {deleted_count} броней", show_alert=True)
        
    except Exception as e:
        print(f"Error in mass delete: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "cancel_delete_all")
async def cancel_delete_all(callback: CallbackQuery):
    """Отменить удаление всех броней"""
    await callback.message.edit_text(
        "❌ <b>Удаление отменено</b>\n\n"
        "Старые брони не были удалены.\n"
        "Нажмите 'Прочее' для повторного просмотра.",
        parse_mode="HTML"
    )


