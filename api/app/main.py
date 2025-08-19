#app/main.py
from fastapi import FastAPI, HTTPException, Query
from datetime import datetime, timedelta
from . import schemas, crud
import pytz
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/reserve")
def reserve(reservation: schemas.ReservationCreate):
    import pytz
    
    # Получаем московское время
    moscow_tz = pytz.timezone('Europe/Moscow')
    now_moscow = datetime.now(moscow_tz)
    
    # Проверяем время закрытия заведения (23:00)
    start_time = datetime.strptime(reservation.time, "%H:%M")
    end_time = start_time + timedelta(hours=reservation.duration)
    
    if end_time.time() > datetime.strptime("23:00", "%H:%M").time():
        raise HTTPException(
            status_code=400, 
            detail=f"Заведение закрывается в 23:00. Выбранное время ({reservation.time}) и продолжительность ({reservation.duration} ч) превышают время работы."
        )

    # Проверяем, не прошло ли время для сегодняшнего дня (по МСК)
    reservation_date = datetime.strptime(reservation.date, "%Y-%m-%d").date()
    reservation_time = datetime.strptime(reservation.time, "%H:%M").time()
    
    # Если бронирование на сегодня по МСК
    today_moscow = now_moscow.date()
    if reservation_date == today_moscow:
        current_time_moscow = now_moscow.time()
        buffer_datetime = now_moscow + timedelta(minutes=60)
        buffer_time = buffer_datetime.time()
        
        if reservation_time <= buffer_time:
            raise HTTPException(
                status_code=400, 
                detail=f"Нельзя бронировать время, которое уже прошло или слишком близко к текущему времени по МСК ({now_moscow.strftime('%H:%M')}). Минимум за час."
            )

    # Проверяем доступность времени
    if not crud.is_time_slot_available(reservation.date, reservation.time, reservation.duration, reservation.place):
        raise HTTPException(status_code=400, detail="Нет свободных столиков на это время")

    return crud.create_reservation(reservation)

@app.get("/check")
def check(
    date: str = Query(...),
    time: str = Query(...),
    duration: int = Query(1),
    place: str = Query(...),
):
    # Проверяем время закрытия (23:00)
    start_time = datetime.strptime(time, "%H:%M")
    end_time = start_time + timedelta(hours=duration)
    
    if end_time.time() > datetime.strptime("23:00", "%H:%M").time():
        return {"free": 0, "reason": "closing_time"}
    
    # Проверяем, не прошло ли время для сегодняшнего дня
    try:
        check_date = datetime.strptime(date, "%Y-%m-%d").date()
        check_time = datetime.strptime(time, "%H:%M").time()
        
        # Если проверка на сегодня
        today = datetime.now().date()
        if check_date == today:
            current_datetime = datetime.now()
            buffer_datetime = current_datetime + timedelta(minutes=60)  # Буфер 1 час
            
            # Создаем datetime для проверяемого времени
            check_datetime = datetime.combine(check_date, check_time)
            
            if check_datetime <= buffer_datetime:
                return {"free": 0, "reason": "time_passed"}
    
    except ValueError:
        return {"free": 0, "reason": "invalid_date_time"}
    
    free = crud.get_free_tables(date, time, duration, place)
    return {"free": free}

# ИСПРАВЛЕНО: Замена функции get_reservations на прямое обращение к Firebase
@app.get("/get_reservations")
def get_reservations():
    """Получает все бронирования из Firebase"""
    try:
        ref = db.reference("/reservations")
        data = ref.get() or {}
        return data
    except Exception as e:
        print(f"Error getting reservations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get_reservations/{date}")
def get_reservations_by_date(date: str):
    """Получает бронирования по дате"""
    try:
        ref = db.reference("/reservations")
        data = ref.get() or {}
        
        # Фильтруем по дате
        filtered_reservations = {
            key: reservation for key, reservation in data.items()
            if reservation.get("date") == date
        }
        
        return filtered_reservations
    except Exception as e:
        print(f"Error getting reservations by date: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cancel_reservation")
async def cancel_reservation(user_id: str, date: str, time: str, cancelled_at: str = None):
    """Помечает бронь как отмененную"""
    try:
        print(f"=== CANCEL RESERVATION DEBUG ===")
        print(f"Received parameters:")
        print(f"  user_id: {user_id} (type: {type(user_id)})")
        print(f"  date: {date} (type: {type(date)})")
        print(f"  time: {time} (type: {type(time)})")
        print(f"  cancelled_at: {cancelled_at}")
        
        ref = db.reference("/reservations")
        data = ref.get() or {}
        
        print(f"Total reservations in database: {len(data)}")
        
        reservation_key = None
        original_reservation = None
        
        # Находим нужную бронь с подробным логированием
        for key, reservation in data.items():
            print(f"\nChecking reservation {key}:")
            print(f"  DB user_id: {reservation.get('user_id')} (type: {type(reservation.get('user_id'))})")
            print(f"  DB date: {reservation.get('date')} (type: {type(reservation.get('date'))})")
            print(f"  DB time: {reservation.get('time')} (type: {type(reservation.get('time'))})")
            print(f"  DB confirmed: {reservation.get('confirmed')}")
            print(f"  DB cancelled: {reservation.get('cancelled')}")
            print(f"  DB status: {reservation.get('status')}")
            
            # Проверяем каждое условие отдельно
            user_id_match = str(reservation.get("user_id")) == str(user_id)
            date_match = reservation.get("date") == date
            time_match = reservation.get("time") == time
            
            print(f"  user_id match: {user_id_match}")
            print(f"  date match: {date_match}")
            print(f"  time match: {time_match}")
            
            if user_id_match and date_match and time_match:
                print(f"  ✅ FOUND MATCH!")
                reservation_key = key
                original_reservation = reservation
                break
            else:
                print(f"  ❌ No match")
        
        if not reservation_key:
            print(f"❌ NO RESERVATION FOUND")
            print(f"Search criteria:")
            print(f"  Looking for user_id: '{user_id}'")
            print(f"  Looking for date: '{date}'") 
            print(f"  Looking for time: '{time}'")
            return {"error": "Reservation not found"}
        
        print(f"✅ Found reservation to cancel: {reservation_key}")
        
        # Обновляем статус брони
        utc_now = datetime.now(pytz.UTC)
        update_data = {
            "cancelled": True,
            "status": "cancelled",
            "confirmed": False,
            "cancelled_at": utc_now.isoformat()  # Сохраняем в UTC
        }
        
        ref.child(reservation_key).update(update_data)
        
        print(f"Updating with data: {update_data}")
        
        # Применяем обновление
        ref.child(reservation_key).update(update_data)
        
        # Проверяем, что обновление прошло успешно
        updated_reservation = ref.child(reservation_key).get()
        
        print(f"Updated reservation: {updated_reservation}")
        
        if updated_reservation and updated_reservation.get("cancelled"):
            print(f"✅ Reservation {reservation_key} successfully cancelled")
            return {
                "message": "Reservation cancelled successfully",
                "id": reservation_key,
                "updated_reservation": updated_reservation
            }
        else:
            print(f"❌ Failed to update reservation status")
            return {"error": "Failed to update reservation status"}
            
    except Exception as e:
        print(f"❌ ERROR in cancel_reservation: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup_cancelled")
async def cleanup_cancelled_reservations():
    """Удаляет отмененные заявки старше 3 дней"""
    try:
        ref = db.reference("/reservations")
        data = ref.get() or {}
        
        deleted_count = 0
        three_days_ago = datetime.now() - timedelta(days=3)
        keys_to_delete = []
        
        # Находим заявки для удаления
        for key, reservation in data.items():
            if reservation.get("cancelled") and reservation.get("cancelled_at"):
                try:
                    cancelled_date = datetime.fromisoformat(reservation["cancelled_at"])
                    if cancelled_date < three_days_ago:
                        keys_to_delete.append(key)
                except Exception as e:
                    print(f"Error processing reservation {key}: {e}")
        
        # Удаляем найденные заявки
        for key in keys_to_delete:
            try:
                ref.child(key).delete()
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting reservation {key}: {e}")
        
        return {
            "deleted_count": deleted_count, 
            "message": f"Deleted {deleted_count} old cancelled reservations"
        }
        
    except Exception as e:
        print(f"Error in cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/check_reservation_status")
async def check_reservation_status(user_id: str, date: str, time: str):
    """Проверяет статус конкретной брони - для отладки"""
    try:
        ref = db.reference("/reservations")
        data = ref.get() or {}
        
        for key, reservation in data.items():
            if (str(reservation.get("user_id")) == str(user_id) and
                reservation.get("date") == date and
                reservation.get("time") == time):
                
                return {
                    "found": True,
                    "id": key,
                    "reservation": reservation
                }
        
        return {"found": False, "message": "Reservation not found"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/debug_database_structure")
async def debug_database_structure():
    """Отладка структуры базы данных Firebase"""
    try:
        # Проверяем корень
        root_ref = db.reference("/")
        root_data = root_ref.get() or {}
        
        # Проверяем узел reservations
        reservations_ref = db.reference("/reservations") 
        reservations_data = reservations_ref.get() or {}
        
        return {
            "root_structure": {
                "keys": list(root_data.keys()) if isinstance(root_data, dict) else "not_dict",
                "total_items": len(root_data) if isinstance(root_data, dict) else 0,
                "sample_data": dict(list(root_data.items())[:2]) if isinstance(root_data, dict) and root_data else {}
            },
            "reservations_structure": {
                "keys": list(reservations_data.keys()) if isinstance(reservations_data, dict) else "not_dict", 
                "total_items": len(reservations_data) if isinstance(reservations_data, dict) else 0,
                "sample_data": dict(list(reservations_data.items())[:2]) if isinstance(reservations_data, dict) and reservations_data else {}
            }
        }
    except Exception as e:
        print(f"Error in debug: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/confirm")
async def confirm_reservation(user_id: str, date: str, time: str):
    """Подтверждает бронь"""
    import pytz
    try:
        ref = db.reference("/reservations")
        data = ref.get() or {}
        
        reservation_key = None
        
        # Находим нужную бронь
        for key, reservation in data.items():
            if (str(reservation.get("user_id")) == str(user_id) and
                reservation.get("date") == date and
                reservation.get("time") == time):
                reservation_key = key
                break
        
        if not reservation_key:
            return {"error": "Reservation not found"}
        
        # Подтверждаем бронь с временем в UTC
        utc_now = datetime.now(pytz.UTC)
        update_data = {
            "confirmed": True,
            "status": "confirmed",
            "confirmed_at": utc_now.isoformat()
        }
        
        ref.child(reservation_key).update(update_data)
        
        return {
            "message": "Reservation confirmed successfully",
            "id": reservation_key
        }
        
    except Exception as e:
        print(f"Error confirming reservation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mark_preorder")
async def mark_preorder(user_id: str, date: str, time: str, preorder_at: str = None):
    """Помечает бронь как имеющую предзаказ"""
    try:
        print(f"=== MARK PREORDER DEBUG ===")
        print(f"Received parameters:")
        print(f"  user_id: {user_id}")
        print(f"  date: {date}")
        print(f"  time: {time}")
        print(f"  preorder_at: {preorder_at}")
        
        # Используем тот же ref что и в других функциях
        from .firebase_config import ref
        data = ref.get() or {}
        
        reservation_key = None
        
        # Находим нужную бронь
        for key, reservation in data.items():
            if (str(reservation.get("user_id")) == str(user_id) and
                reservation.get("date") == date and
                reservation.get("time") == time):
                reservation_key = key
                break
        
        if not reservation_key:
            print(f"❌ NO RESERVATION FOUND for preorder")
            return {"error": "Reservation not found"}
        
        print(f"✅ Found reservation to mark preorder: {reservation_key}")
        
        # Обновляем статус предзаказа
        update_data = {
            "preorder": True,
            "preorder_at": preorder_at or datetime.now().isoformat()
        }
        
        print(f"Updating preorder with data: {update_data}")
        
        # Применяем обновление
        ref.child(reservation_key).update(update_data)
        
        # Проверяем, что обновление прошло успешно
        updated_reservation = ref.child(reservation_key).get()
        
        print(f"Updated reservation with preorder: {updated_reservation}")
        
        if updated_reservation and updated_reservation.get("preorder"):
            print(f"✅ Preorder marked successfully for reservation {reservation_key}")
            return {
                "message": "Preorder marked successfully",
                "id": reservation_key,
                "updated_reservation": updated_reservation
            }
        else:
            print(f"❌ Failed to mark preorder")
            return {"error": "Failed to mark preorder"}
            
    except Exception as e:
        print(f"❌ ERROR in mark_preorder: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/reserve")
def reserve(reservation: schemas.ReservationCreate):
    import pytz
    
    # Получаем московское время
    moscow_tz = pytz.timezone('Europe/Moscow')
    now_moscow = datetime.now(moscow_tz)
    
    # Проверяем время закрытия заведения
    end_time = (datetime.strptime(reservation.time, "%H:%M") + timedelta(hours=reservation.duration)).time()
    if end_time > datetime.strptime("22:00", "%H:%M").time():
        raise HTTPException(status_code=400, detail="Кафе закрывается в 22:00")

    # Проверяем, не прошло ли время для сегодняшнего дня (по МСК)
    reservation_date = datetime.strptime(reservation.date, "%Y-%m-%d").date()
    reservation_time = datetime.strptime(reservation.time, "%H:%M").time()
    
    # Если бронирование на сегодня по МСК
    today_moscow = now_moscow.date()
    if reservation_date == today_moscow:
        current_time_moscow = now_moscow.time()
        buffer_datetime = now_moscow + timedelta(minutes=60)
        buffer_time = buffer_datetime.time()
        
        if reservation_time <= buffer_time:
            raise HTTPException(
                status_code=400, 
                detail=f"Нельзя бронировать время, которое уже прошло или слишком близко к текущему времени по МСК ({now_moscow.strftime('%H:%M')}). Минимум за час."
            )

    # Проверяем доступность времени
    if not crud.is_time_slot_available(reservation.date, reservation.time, reservation.duration, reservation.place):
        raise HTTPException(status_code=400, detail="Нет свободных столиков на это время")

    return crud.create_reservation(reservation)

@app.get("/check")
def check(
    date: str = Query(...),
    time: str = Query(...),
    duration: int = Query(1),
    place: str = Query(...),
):
    # Проверяем время закрытия
    end_time = (datetime.strptime(time, "%H:%M") + timedelta(hours=duration)).time()
    if end_time > datetime.strptime("23:00", "%H:%M").time():
        return {"free": 0}
    
    # Проверяем, не прошло ли время для сегодняшнего дня
    try:
        check_date = datetime.strptime(date, "%Y-%m-%d").date()
        check_time = datetime.strptime(time, "%H:%M").time()
        
        # Если проверка на сегодня
        today = datetime.now().date()
        if check_date == today:
            current_datetime = datetime.now()
            buffer_datetime = current_datetime + timedelta(minutes=60)  # Буфер 1 час
            
            # Создаем datetime для проверяемого времени
            check_datetime = datetime.combine(check_date, check_time)
            
            if check_datetime <= buffer_datetime:
                return {"free": 0, "reason": "time_passed"}
    
    except ValueError:
        return {"free": 0, "reason": "invalid_date_time"}
    
    free = crud.get_free_tables(date, time, duration, place)
    return {"free": free}

@app.post("/remove_preorder")
async def remove_preorder(user_id: str, date: str, time: str):
    """Снимает отметку предзаказа с брони"""
    try:
        ref = db.reference("/reservations")
        data = ref.get() or {}
        
        reservation_key = None
        
        # Находим нужную бронь
        for key, reservation in data.items():
            if (str(reservation.get("user_id")) == str(user_id) and
                reservation.get("date") == date and
                reservation.get("time") == time):
                reservation_key = key
                break
        
        if not reservation_key:
            return {"error": "Reservation not found"}
        
        # Снимаем предзаказ
        update_data = {
            "preorder": False,
            "preorder_at": None
        }
        
        ref.child(reservation_key).update(update_data)
        
        return {
            "message": "Preorder removed successfully",
            "id": reservation_key
        }
        
    except Exception as e:
        print(f"Error removing preorder: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

@app.delete("/delete_reservation/{reservation_id}")
async def delete_reservation(reservation_id: str):
    """Удаляет бронь по ID"""
    try:
        ref = db.reference("/reservations")
        
        # Проверяем, существует ли бронь
        reservation = ref.child(reservation_id).get()
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        
        # Удаляем бронь
        ref.child(reservation_id).delete()
        
        return {
            "message": "Reservation deleted successfully",
            "deleted_id": reservation_id,
            "deleted_reservation": reservation
        }
        
    except Exception as e:
        print(f"Error deleting reservation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_old_reservations")
async def get_old_reservations(months_back: int = 2):
    """Получает старые брони за указанное количество месяцев"""
    try:
        from datetime import datetime, timedelta
        import pytz
        
        # Получаем московское время
        moscow_tz = pytz.timezone('Europe/Moscow')
        now_moscow = datetime.now(moscow_tz)
        current_date_moscow = now_moscow.date()
        
        # Вычисляем дату N месяцев назад
        past_date = current_date_moscow - timedelta(days=months_back * 30)
        
        ref = db.reference("/reservations")
        data = ref.get() or {}
        
        old_reservations = {}
        
        for key, reservation in data.items():
            try:
                reservation_date_str = reservation.get("date")
                if not reservation_date_str:
                    continue
                    
                reservation_date = datetime.strptime(reservation_date_str, "%Y-%m-%d").date()
                
                # Проверяем, что бронь старше 2 месяцев
                if reservation_date < past_date:
                    old_reservations[key] = {
                        **reservation,
                        "reservation_id": key,
                        "days_ago": (current_date_moscow - reservation_date).days
                    }
                    
            except (ValueError, TypeError) as e:
                print(f"Error processing reservation {key}: {e}")
                continue
        
        # Сортируем по дате (старые сначала)
        sorted_reservations = dict(
            sorted(
                old_reservations.items(), 
                key=lambda x: x[1].get("date", "")
            )
        )
        
        return {
            "old_reservations": sorted_reservations,
            "total_count": len(sorted_reservations)
        }
        
    except Exception as e:
        print(f"Error getting old reservations: {e}")
        raise HTTPException(status_code=500, detail=str(e))
