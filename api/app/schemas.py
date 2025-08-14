# Файл: api/app/schemas.py
from pydantic import BaseModel

class ReservationCreate(BaseModel):
    place: str
    name: str
    phone: str
    date: str
    time: str
    duration: int
    user_id: int

class ReservationOut(ReservationCreate):
    confirmed: bool