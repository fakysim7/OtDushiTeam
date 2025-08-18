# from fastapi import FastAPI, HTTPException, Depends, Query
# from sqlalchemy.orm import Session
# from . import models, schemas, crud
# from .database import engine, get_db
# from fastapi.middleware.cors import CORSMiddleware
# from datetime import datetime, timedelta

# models.Base.metadata.create_all(bind=engine)

# app = FastAPI()

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# @app.post("/reserve")
# def reserve(reservation: schemas.ReservationCreate, db: Session = Depends(get_db)):
#     end_time = (datetime.strptime(reservation.time, "%H:%M") + timedelta(hours=reservation.duration)).time()
#     if end_time > datetime.strptime("22:00", "%H:%M").time():
#         raise HTTPException(status_code=400, detail="Кафе закрывается в 22:00")

#     if not crud.is_time_slot_available(db, reservation.date, reservation.time, reservation.duration, reservation.place):
#         raise HTTPException(status_code=400, detail="Нет свободных столиков на это время")

#     return crud.create_reservation(db, reservation)

# @app.get("/check")
# def check(
#     date: str = Query(...),
#     time: str = Query(...),
#     duration: int = Query(1),
#     place: str = Query(...),
#     db: Session = Depends(get_db)
# ):
#     end_time = (datetime.strptime(time, "%H:%M") + timedelta(hours=duration)).time()
#     if end_time > datetime.strptime("23:00", "%H:%M").time():
#         return {"free": 0}
#     free = crud.get_free_tables(db, date, time, duration, place)
#     return {"free": free}

# @app.get("/get_reservations")
# def get_reservations(db: Session = Depends(get_db)):
#     return crud.get_all_reservations(db)

# @app.get("/get_reservations/{date}")
# def get_reservations_by_date(date: str, db: Session = Depends(get_db)):
#     return crud.get_reservations_by_date(db, date)

# @app.post("/confirm")
# def confirm(user_id: int, date: str, time: str, db: Session = Depends(get_db)):
#     result = crud.confirm_reservation(db, user_id, date, time)
#     if not result:
#         raise HTTPException(status_code=404, detail="Reservation not found")
#     return {"status": "confirmed"}

#app/main.py
from fastapi import FastAPI, HTTPException, Query
from datetime import datetime, timedelta
from . import schemas, crud
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
    end_time = (datetime.strptime(reservation.time, "%H:%M") + timedelta(hours=reservation.duration)).time()
    if end_time > datetime.strptime("22:00", "%H:%M").time():
        raise HTTPException(status_code=400, detail="Кафе закрывается в 22:00")

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
    end_time = (datetime.strptime(time, "%H:%M") + timedelta(hours=duration)).time()
    if end_time > datetime.strptime("23:00", "%H:%M").time():
        return {"free": 0}
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
        update_data = {
            "cancelled": True,
            "status": "cancelled",
            "confirmed": False,  # Снимаем подтверждение если было
            "cancelled_at": cancelled_at or datetime.now().isoformat()
        }
        
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
        
        # Подтверждаем бронь
        update_data = {
            "confirmed": True,
            "status": "confirmed",
            "confirmed_at": datetime.now().isoformat()
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