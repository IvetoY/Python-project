"""Schemas for data validation using Pydantic."""
import re
from typing import Optional
from pydantic import BaseModel, field_validator, EmailStr

class UserCreate(BaseModel):
    """Schema for user registration."""
    email: str
    username: str
    first_name: str
    address: str
    phone: str
    password: str
    role: str

    @field_validator('first_name', 'address')
    @classmethod
    def validate_bulgarian_no_digits(cls, value: str) -> str:
        """Validation of first_name and address."""
        if any(char.isdigit() for char in value):
            raise ValueError("Полето не може да съдържа цифри.")
        if not re.match(r"^[А-Яа-яЁё\s-]+$", value):
            raise ValueError("Моля, пишете на кирилица.")
        return value

    @field_validator('username')
    @classmethod
    def validate_username_latin(cls, value: str) -> str:
        """Validation of username."""
        if not re.match(r"^[A-Za-z0-9_.]+$", value):
            raise ValueError("Username-ът трябва да е на латиница.")
        return value

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, value: str) -> str:
        """Validation of phone number."""
        pattern = r"^(?:\+359|0)\d{9}$"
        if not re.match(pattern, value):
            raise ValueError("Невалиден български телефонен номер.")
        return value

class UserUpdate(BaseModel):
    """Schema for updating user profile."""
    first_name: str
    phone: str
    address: str
    bio: Optional[str] = None

    @field_validator('first_name', 'address')
    @classmethod
    def validate_bg(cls, v):
        if not re.match(r"^[А-Яа-яЁё\s-]+$", v):
            raise ValueError("Трябва да е на кирилица без цифри.")
        return v

    @field_validator('phone')
    @classmethod
    def validate_ph(cls, v):
        if not re.match(r"^(?:\+359|0)\d{9}$", v):
            raise ValueError("Невалиден български телефон.")
        return v
    
class LessonCreate(BaseModel):
    """Schema for creating a lesson."""
    subject: str
    category: str
    price: float

    @field_validator('price')
    @classmethod
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError("Цената трябва да е положително число.")
        return v
    
class UserLogin(BaseModel):
    """Schema for user login validation."""
    email: str
    password: str

class BookingCreate(BaseModel):
    client_id: int
    lesson_id: int
    appointment_time: str

class ReviewCreate(BaseModel):
    """Schema for creating a review."""
    lesson_id: int
    rating: int
    comment: Optional[str] = None

    @field_validator('rating')
    @classmethod
    def validate_rating(cls, v: int) -> int:
        """Оценката трябва да е между 2 и 6."""
        if not 1 <= v <= 5:
            raise ValueError("Оценката трябва да е между 2 и 6 звезди.")
        return v