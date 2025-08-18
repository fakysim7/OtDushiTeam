# # Файл: api/app/models.py
# from sqlalchemy import Column, Integer, String, Boolean
# from sqlalchemy.ext.declarative import declarative_base

# Base = declarative_base()

# class Reservation(Base):
#     __tablename__ = "reservations"

#     id = Column(Integer, primary_key=True, index=True)
#     place = Column(String)  
#     name = Column(String, nullable=False)
#     phone = Column(String, nullable=False)
#     date = Column(String, nullable=False)
#     time = Column(String, nullable=False)
#     duration = Column(Integer, default=1)
#     user_id = Column(Integer, nullable=False)
#     confirmed = Column(Boolean, default=False)
    