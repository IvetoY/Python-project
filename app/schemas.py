from pydantic import BaseModel
from typing import Optional

class UserCreate(BaseModel):
    email: str
    password: str
    role: str

class BookingCreate(BaseModel):
    client_id: int
    lesson_id: int
    appointment_time: str

class ReviewCreate(BaseModel):
    lesson_id: int
    rating: int
    comment: str