# from sqlalchemy.orm import Session
# from . import models, schemas
# from datetime import datetime, timedelta

# LIMIT_PER_PLACE = 5  # Максимум бронирований на одно время в одном заведении

# def create_reservation(db: Session, reservation: schemas.ReservationCreate):
#     db_res = models.Reservation(
#         name=reservation.name,
#         phone=reservation.phone,
#         date=reservation.date,
#         time=reservation.time,
#         duration=reservation.duration,
#         user_id=reservation.user_id,
#         place=reservation.place  # ← добавили заведение
#     )
#     db.add(db_res)
#     db.commit()
#     db.refresh(db_res)
#     return db_res

# def get_all_reservations(db: Session):
#     return db.query(models.Reservation).all()

# def get_reservations_by_date(db: Session, date: str):
#     return db.query(models.Reservation).filter(models.Reservation.date == date).all()

# def get_free_tables(db: Session, date: str, time: str, duration: int, place: str) -> int:
#     """
#     Вернуть количество свободных столов (максимум 5).
#     """
#     if not is_time_slot_available(db, date, time, duration, place):
#         return 0
#     return LIMIT_PER_PLACE  # или сколько осталось — можно сделать расчёт в будущем

# def is_time_slot_available(db: Session, date: str, time: str, duration: int, place: str) -> bool:
#     """
#     Проверяет, доступно ли время в конкретном заведении.
#     """
#     new_start = datetime.strptime(time, "%H:%M")
#     new_end = new_start + timedelta(hours=duration)

#     existing = db.query(models.Reservation).filter(
#         models.Reservation.date == date,
#         models.Reservation.place == place
#     ).all()

#     conflict_count = 0

#     for res in existing:
#         res_start = datetime.strptime(res.time, "%H:%M")
#         res_end = res_start + timedelta(hours=res.duration)

#         # Есть пересечение времени
#         if not (new_end <= res_start or new_start >= res_end):
#             conflict_count += 1

#     return conflict_count < LIMIT_PER_PLACE

# def confirm_reservation(db: Session, user_id: int, date: str, time: str):
#     res = db.query(models.Reservation).filter_by(user_id=user_id, date=date, time=time).first()
#     if res:
#         res.confirmed = True
#         db.commit()
#         return True
#     return False

#app/crud.py
from datetime import datetime, timedelta
from . import schemas
from .firebase_config import ref
import uuid

LIMIT_PER_PLACE = 5

def create_reservation(reservation: schemas.ReservationCreate):
    reservation_id = str(uuid.uuid4())
    reservation_data = {
        'id': reservation_id,
        'place': reservation.place,
        'name': reservation.name,
        'phone': reservation.phone,
        'date': reservation.date,
        'time': reservation.time,
        'duration': reservation.duration,
        'user_id': reservation.user_id,
        'confirmed': False
    }
    ref.child(reservation_id).set(reservation_data)
    return reservation_data

def get_all_reservations():
    return ref.get() or {}

def get_reservations_by_date(date: str):
    all_reservations = get_all_reservations()
    return {k: v for k, v in all_reservations.items() if v.get('date') == date}

def get_free_tables(date: str, time: str, duration: int, place: str) -> int:
    if not is_time_slot_available(date, time, duration, place):
        return 0
    return LIMIT_PER_PLACE

def is_time_slot_available(date: str, time: str, duration: int, place: str) -> bool:
    new_start = datetime.strptime(time, "%H:%M")
    new_end = new_start + timedelta(hours=duration)

    reservations = get_reservations_by_date(date)
    place_reservations = [r for r in reservations.values() if r.get('place') == place]

    conflict_count = 0

    for res in place_reservations:
        res_start = datetime.strptime(res['time'], "%H:%M")
        res_end = res_start + timedelta(hours=res['duration'])

        if not (new_end <= res_start or new_start >= res_end):
            conflict_count += 1

    return conflict_count < LIMIT_PER_PLACE

def confirm_reservation(user_id: int, date: str, time: str):
    reservations = get_all_reservations()
    for res_id, res in reservations.items():
        if (res['user_id'] == user_id and 
            res['date'] == date and 
            res['time'] == time):
            ref.child(res_id).update({'confirmed': True})
            return True
    return False