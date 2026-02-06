"""Database models for the Tutoring Platform application."""
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Float, Boolean, ForeignKey, Text
from .database import Base
from sqlalchemy.orm import relationship


class User(Base):
    """User model representing students, teachers, and admins."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    role = Column(String)

    first_name = Column(String, nullable=True)
    username = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)

    bio = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    reviews_sent = relationship("Review", foreign_keys="Review.user_id", back_populates="user")
    reviews_received = relationship("Review", foreign_keys="Review.teacher_id", back_populates="teacher")
    lessons = relationship("Lesson", back_populates="teacher")

    payments_made = relationship("Transaction", foreign_keys="Transaction.client_id", back_populates="client")
    payments_received = relationship("Transaction", foreign_keys="Transaction.teacher_id", back_populates="teacher")


class Lesson(Base):
    """Lesson model representing the services offered by teachers."""
    __tablename__ = "lessons"
    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String)
    category = Column(String)
    price = Column(Float)
    teacher_id = Column(Integer, ForeignKey("users.id"))
    teacher_name = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)

    is_active = Column(Boolean, default=True)

    teacher = relationship("User", back_populates="lessons")


class Booking(Base):
    """Booking model for scheduling appointments between clients and teachers."""
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"))
    lesson_id = Column(Integer, ForeignKey("lessons.id"))
    appointment_time = Column(String)
    status = Column(String, default="Заявен")

    lesson = relationship("Lesson", backref="bookings")
    client = relationship("User", foreign_keys=[client_id])


class Review(Base):
    """Review model for feedback and ratings."""
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id], back_populates="reviews_sent")
    teacher = relationship("User", foreign_keys=[teacher_id], back_populates="reviews_received")


class Favorite(Base):
    """Favorite model is used by users to save their preferred lessons."""
    __tablename__ = "favorites"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    lesson_id = Column(Integer, ForeignKey("lessons.id"))


class Notification(Base):
    """Notification model for user alerts."""
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(String)
    is_read = Column(Boolean, default=False)


class Transaction(Base):
    """Transaction model for financial records."""
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id"))
    teacher_id = Column(Integer, ForeignKey("users.id"))
    lesson_id = Column(Integer, ForeignKey("lessons.id"))
    amount = Column(Float)
    currency = Column(String, default="BGN")
    status = Column(String, default="pending")
    payment_method = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("User", foreign_keys=[client_id], back_populates="payments_made")
    teacher = relationship("User", foreign_keys=[teacher_id], back_populates="payments_received")

    lesson = relationship("Lesson")
