"""Main FastAPI application and routes."""
from typing import Optional, Any
import hashlib
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Request, Form, Response, Cookie
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from . import models, schemas
from .database import engine, get_db

templates = Jinja2Templates(directory="templates")

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Посредник за услуги наблизо - Backend")


def hash_password(password: str) -> str:  # kaloqn taka kaza
    """Hash the user password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify if the provided plain password matches the stored hash."""
    return hash_password(plain_password) == hashed_password


@app.get("/search", response_class=HTMLResponse)
def search_web(
    request: Request,
    db: Session = Depends(get_db),
    name: Optional[str] = None,
    category: Optional[str] = None,
    city: Optional[str] = None,
    current_user_id: Optional[str] = Cookie(None)
) -> Any:
    """Search for lessons by subject, category, and city with verified teacher filtering."""
    query = db.query(models.Lesson).join(
        models.User, models.Lesson.teacher_id == models.User.id
    ).filter(models.User.is_verified is True)

    if name:
        query = query.filter(models.Lesson.subject.ilike(f"%{name}%"))
    if category:
        query = query.filter(models.Lesson.category == category)
    if city:
        search_city = f"%{city.strip()}%"
        query = query.filter(models.User.address.ilike(search_city))

    lessons = query.all()

    user = None
    if current_user_id:
        user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "lessons": lessons,
        "eur_rate": 1.95583,
        "user_id": user.id if user else None,
        "user_role": user.role if user else "guest",
        "username": user.username if user else None
    })


@app.post("/register")
def register(user: schemas.UserCreate, db: Session = Depends(get_db)) -> Any:
    """Register a new user via API."""
    db_user = models.User(email=user.email, password=user.password, role=user.role)
    db.add(db_user)
    db.commit()
    return {"message": "Успешна регистрация!"}


@app.post("/bookings")
def book(data: schemas.BookingCreate, db: Session = Depends(get_db)) -> Any:
    """Create a new lesson booking via API."""
    new_booking = models.Booking(
        client_id=data.client_id,
        lesson_id=data.lesson_id,
        appointment_time=data.appointment_time
    )
    db.add(new_booking)
    db.commit()
    return {"message": "Резервацията е създадена!"}


@app.get("/admin/users", response_model=None)
def list_users(db: Session = Depends(get_db)) -> Any:
    """List all users for administrative purposes."""
    return db.query(models.User).all()


@app.put("/admin/verify-tutor/{user_id}")
def verify(user_id: int, db: Session = Depends(get_db)) -> Any:
    """Verify a tutor by their user ID."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        user.is_verified = True
        db.commit()
        return {"message": "Учителят е верифициран!"}
    raise HTTPException(status_code=404, detail="Не е намерен")


@app.get("/setup")  # za testove beshe
def setup(db: Session = Depends(get_db)) -> Any:
    """Reset the database and populate it with initial test data."""
    db.query(models.Review).delete()
    db.query(models.Favorite).delete()
    db.query(models.Booking).delete()
    db.query(models.Lesson).delete()
    db.query(models.User).delete()

    tutor1 = models.User(
        email="ivan.ivanov@example.com",
        username="ivan_tutor",
        password=hash_password("123"),  # (парола) крие я
        role="tutor",
        first_name="Иван Иванов",
        address="София",
        phone="0888111222"
    )
    db.add(tutor1)
    db.commit()

    db.add(models.Lesson(
        subject="Математика (Анализ)",
        category="Частни уроци",
        teacher_name=tutor1.first_name,
        teacher_id=tutor1.id,
        price=35.0,
        latitude=42.69, longitude=23.32
    ))

    db.commit()
    return {"message": "Системата е готова с учители с пълни имена!"}


@app.put("/users/{user_id}/address")
def update_address(user_id: int, new_address: str, db: Session = Depends(get_db)) -> Any:
    """Update the address for a specific user."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Не е намерен")
    user.address = new_address
    db.commit()
    return {"message": "Адресът е обновен!"}


@app.get("/users/{user_id}/bookings", response_model=None)
def get_user_bookings(user_id: int, db: Session = Depends(get_db)) -> Any:
    """Retrieve all bookings associated with a specific client ID."""
    return db.query(models.Booking).filter(models.Booking.client_id == user_id).all()


@app.post("/messages/send")
def send_message(to_user_id: int, text: str, db: Session = Depends(get_db)) -> Any:
    """Send a system notification to a specific user."""
    db.add(models.Notification(user_id=to_user_id, message=text))
    db.commit()
    return {"status": "Изпратено!"}


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> Any:
    """Render the registration HTML page."""
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register-web")
def register_web(
    response: Response,
    first_name: str = Form(None),
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    phone: str = Form(None),
    bio: str = Form(None),
    role: str = Form(...),
    address: str = Form(None),
    db: Session = Depends(get_db)
) -> Any:
    """Handle web-based registration form submission and set session cookie."""
    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        return HTMLResponse(content="<script>alert('Потребителското име е заето!'); "
                                    "window.history.back();</script>")
    hashed_pwd = hash_password(password)
    new_user = models.User(
        first_name=first_name,
        username=username,
        email=email,
        password=hashed_pwd,
        phone=phone,
        bio=bio,
        role=role,
        address=address
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    response = RedirectResponse(url="/profile", status_code=303)
    response.set_cookie(key="current_user_id", value=str(new_user.id), httponly=True)
    return response


@app.get("/", response_class=HTMLResponse)
def home_page(request: Request, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Any:
    """Render the home page with active lessons from verified tutors."""
    lessons = db.query(models.Lesson).join(
        models.User, models.Lesson.teacher_id == models.User.id
    ).filter(models.User.is_verified is True).filter(models.Lesson.is_active is True).all()

    user = None
    if current_user_id:
        user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "lessons": lessons,
        "eur_rate": 1.95583,
        "user_role": user.role if user else "guest",
        "user_id": user.id if user else None,
        "username": user.username if user else None
    })


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Any:
    """Render the login HTML page."""
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login-web")
def login_web(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
) -> Any:
    """Authenticate user login from the web form and manage session cookies."""
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not user.is_active:
        return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Профилът е деактивиран или не съществува."
    })

    if not verify_password(password, user.password):
        return HTMLResponse(content="<script>alert('Грешен имейл или парола!');"
                                    "window.location.href='/login';</script>")
    response = None
    if user.role == "admin":
        response = RedirectResponse(url="/admin", status_code=303)
    else:
        response = RedirectResponse(url="/profile", status_code=303)

    response.set_cookie(key="current_user_id", value=str(user.id))
    return response


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Any:
    """Display the user's personal profile, bookings, and notifications."""
    if not current_user_id:
        return RedirectResponse(url='/login', status_code=303)

    user_id = int(current_user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()

    favorite_lessons = db.query(models.Lesson).join(models.Favorite).filter(
        models.Favorite.user_id == user_id, models.Lesson.is_active is True
    ).all()

    notifications = db.query(models.Notification).filter(
        models.Notification.user_id == user_id, models.Notification.is_read is False
    ).all()

    if user.role == "admin":
        return RedirectResponse(url="/admin", status_code=303)

    if user.role == "client":
        bookings = db.query(models.Booking).filter(models.Booking.client_id == user.id).all()
    else:
        my_lessons = db.query(models.Lesson).filter(models.Lesson.teacher_id == user.id).all()
        my_lesson_ids = [l.id for l in my_lessons]
        bookings = db.query(models.Booking).filter(models.Booking.lesson_id.in_(my_lesson_ids)).all()

    now = datetime.now()
    upcoming_bookings = []
    history_bookings = []

    for b in bookings:
        if isinstance(b.appointment_time, str):
            try:
                b.appointment_time = datetime.fromisoformat(b.appointment_time.replace(' ', 'T'))
            except Exception:
                b.appointment_time = now

        if b.status == "Отменен от админ":
            history_bookings.append(b)
        elif b.appointment_time < now:
            b.status = "Проведен" if b.status in ["Платен", "Проведен"] else "Непроведен (неплатен)"
            history_bookings.append(b)
        else:
            upcoming_bookings.append(b)

    return templates.TemplateResponse("profile.html", {
        "request": request, "user": user, "upcoming_bookings": upcoming_bookings,
        "history_bookings": history_bookings, "notifications": notifications,
        "favorite_lessons": favorite_lessons, "now": now
    })


@app.get("/edit-profile", response_class=HTMLResponse)
def edit_profile_page(request: Request, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Any:
    """Render the profile editing page."""
    if not current_user_id:
        return RedirectResponse(url='/login', status_code=303)

    user_id = int(current_user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return templates.TemplateResponse("edit_profile.html", {"request": request, "user": user})


@app.post("/update-profile")
def update_profile(
    first_name: str = Form(None), phone: str = Form(None), address: str = Form(None),
    bio: str = Form(None), db: Session = Depends(get_db), current_user_id: str = Cookie(None)
) -> Any:
    """Update user profile information from form data."""
    if not current_user_id:
        return RedirectResponse(url='/login', status_code=303)

    user_id = int(current_user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if user:
        user.first_name, user.phone, user.address = first_name, phone, address
        if user.role == 'tutor':
            user.bio = bio
        db.commit()

    return RedirectResponse(url="/profile", status_code=303)


@app.post("/book-lesson/{lesson_id}")
def book_lesson(
    lesson_id: int, appointment_time: str = Form(...), db: Session = Depends(get_db),
    current_user_id: str = Cookie(None)
) -> Any:
    """Process a lesson booking request and notify the teacher."""
    if not current_user_id:
        return HTMLResponse(content="<script>alert('Моля, влезте в профила си!'); "
                                    "window.location.href='/login';</script>")

    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Урокът не е намерен")

    if not lesson.is_active:
        return {"error": "Този урок вече не се предлага."}
    teacher = db.query(models.User).filter(models.User.id == lesson.teacher_id).first()
    if not teacher.is_verified:
        return {"error": "Учителят все още не е одобрен от администратор."}

    user_id = int(current_user_id)
    client = db.query(models.User).filter(models.User.id == user_id).first()

    new_booking = models.Booking(
        client_id=user_id, lesson_id=lesson_id,
        appointment_time=appointment_time, status="Заявен"
    )
    db.add(new_booking)

    msg = f"Имате нова резервация за {lesson.subject} от {client.username}!"
    db.add(models.Notification(user_id=lesson.teacher_id, message=msg))
    db.commit()

    return RedirectResponse(url="/profile", status_code=303)


@app.post("/confirm-booking/{booking_id}")
def confirm_booking(booking_id: int, db: Session = Depends(get_db)) -> Any:
    """Confirm a lesson booking and update its status."""
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if booking:
        booking.status = "Потвърден"
        db.commit()
    return RedirectResponse(url="/profile", status_code=303)


@app.get("/logout")
def logout(response: Response) -> Any:
    """Log out the user by deleting the session cookie."""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("current_user_id")
    return response


@app.post("/update-booking/{booking_id}/{new_status}")
def update_booking(booking_id: int, new_status: str, db: Session = Depends(get_db)) -> Any:
    """Update booking status and send notifications if the booking is canceled."""
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()

    if booking:
        if new_status == "Отказан":
            pretty_date = booking.appointment_time.replace('T', ' ')
            msg = f"Вашият час по {booking.lesson.subject} за {pretty_date} ч. беше отказан от преподавателя."
            db.add(models.Notification(user_id=booking.client_id, message=msg))
            db.delete(booking)
            db.commit()
            return HTMLResponse(content="<script>alert('Резервацията е отказана успешно.');"
                                        " window.location.href='/profile';</script>")

        booking.status = new_status
        db.commit()
    return RedirectResponse(url="/profile", status_code=303)


@app.get("/public-profile/{user_id}", response_class=HTMLResponse)
def public_profile(request: Request, user_id: int, db: Session = Depends(get_db),
                   current_user_id: str = Cookie(None)) -> Any:
    """Display the public profile of a teacher including reviews and lessons."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return HTMLResponse(content="<script>alert('Потребителят не е намерен!'); window.history.back();</script>")

    teacher_lessons = db.query(models.Lesson).filter(models.Lesson.teacher_id == user_id).all()
    reviews = db.query(models.Review).filter(models.Review.teacher_id == user_id).order_by(
        models.Review.created_at.desc()
    ).all()

    return templates.TemplateResponse("public_profile.html", {
        "request": request, "user": user, "lessons": teacher_lessons, "reviews": reviews,
        "eur_rate": 1.95583, "is_logged_in": True if current_user_id else False,
        "current_user_id": int(current_user_id) if current_user_id else None
    })


@app.post("/delete-notification/{notif_id}")
def delete_notification(notif_id: int, db: Session = Depends(get_db)) -> Any:
    """Delete a specific notification from the database."""
    db.query(models.Notification).filter(models.Notification.id == notif_id).delete()
    db.commit()
    return {"status": "success"}


@app.get("/add-lesson", response_class=HTMLResponse)
def add_lesson_page(request: Request, current_user_id: str = Cookie(None), db: Session = Depends(get_db)) -> Any:
    """Render the page for adding a new lesson (tutors only)."""
    if not current_user_id:
        return HTMLResponse(content="<script>window.location.href='/login';</script>")

    user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if user.role != "tutor":
        return HTMLResponse(content="<script>alert('Само учители могат да добавят уроци!'); "
                                    "window.location.href='/';</script>")

    return templates.TemplateResponse("add_lesson.html", {"request": request, "user": user})


@app.post("/create-lesson")
def create_lesson(
    subject: str = Form(...), category: str = Form(...), price: float = Form(...),
    db: Session = Depends(get_db), current_user_id: str = Cookie(None)
) -> Any:
    """Create a new lesson entry in the database for the logged-in teacher."""
    user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()

    new_lesson = models.Lesson(
        subject=subject, category=category, price=price,
        teacher_id=user.id, teacher_name=user.first_name or user.username,
        latitude=42.69, longitude=23.32
    )
    db.add(new_lesson)
    db.commit()
    return RedirectResponse(url="/profile", status_code=303)


@app.post("/favorites")
def add_to_favorites(lesson_id: int = Form(...), user_id: int = Form(...), db: Session = Depends(get_db)) -> Any:
    """Add a lesson to the user's favorite list."""
    existing = db.query(models.Favorite).filter(
        models.Favorite.user_id == user_id, models.Favorite.lesson_id == lesson_id
    ).first()

    if not existing:
        db.add(models.Favorite(user_id=user_id, lesson_id=lesson_id))
        db.commit()

    return RedirectResponse(url="/?message=added", status_code=303)


@app.post("/remove-favorite/{lesson_id}")
def remove_favorite(lesson_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Any:
    """Remove a lesson from the user's favorite list."""
    if not current_user_id:
        return {"error": "Not logged in"}

    fav = db.query(models.Favorite).filter(
        models.Favorite.user_id == int(current_user_id), models.Favorite.lesson_id == lesson_id
    ).first()

    if fav:
        db.delete(fav)
        db.commit()
    return {"status": "success"}


@app.post("/submit-review/{teacher_id}")
def submit_review(
    teacher_id: int, rating: int = Form(...), comment: str = Form(None),
    db: Session = Depends(get_db), current_user_id: str = Cookie(None)
) -> Any:
    """Submit a rating and comment for a teacher and notify them."""
    if not current_user_id:
        return HTMLResponse(content="<script>alert('Трябва да влезете в профила си!'); window.location.href='/login';</script>")

    user_id = int(current_user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if user.role != "client":
        return HTMLResponse(content="<script>alert('Само ученици могат да оставят ревюта!'); window.history.back();</script>")
    if user_id == teacher_id:
        return HTMLResponse(content="<script>alert('Не можете да оценявате себе си!'); window.history.back();</script>")

    db.add(models.Review(teacher_id=teacher_id, user_id=user_id, rating=rating, comment=comment))
    msg = f"Ученикът {user.username} ви остави оценка {rating} ⭐!"
    db.add(models.Notification(user_id=teacher_id, message=msg))
    db.commit()

    return RedirectResponse(url=f"/public-profile/{teacher_id}", status_code=303)


@app.post("/cancel-booking/{booking_id}")
def cancel_booking(booking_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Any:
    """Cancel a booking and notify the relevant party (either teacher or student)."""
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)

    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        return RedirectResponse(url="/profile", status_code=303)

    user_id = int(current_user_id)
    receiver_id = booking.client_id if user_id == booking.lesson.teacher_id else booking.lesson.teacher_id
    msg = "Преподавателят отмени часа." if user_id == booking.lesson.teacher_id else "Ученикът отмени часа."

    db.add(models.Notification(user_id=receiver_id, message=msg))
    db.delete(booking)
    db.commit()

    return RedirectResponse(url="/profile", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Any:
    """Render the admin dashboard with system stats and user management."""
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)

    admin = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if not admin or admin.role != "admin":
        return HTMLResponse(content="<script>alert('Нямате права!'); window.location.href='/';</script>")

    users, reviews, lessons = db.query(models.User).all(), db.query(models.Review).all(), db.query(models.Lesson).all()
    stats = {
        "total_users": len(users), "tutors_count": len([u for u in users if u.role == 'tutor']),
        "pending_verifications": len([u for u in users if u.role == 'tutor' and not u.is_verified]),
        "total_reviews": len(reviews)
    }

    return templates.TemplateResponse("admin_panel.html", {
        "request": request, "users": users, "reviews": reviews, "lessons": lessons,
        "admin_name": admin.username, "stats": stats, "transactions": db.query(models.Transaction).all()
    })


@app.post("/admin/verify-tutor/{user_id}", response_model=None)
def verify_tutor(user_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Any:
    """Approve a tutor's verification request (admin only)."""
    admin = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if not admin or admin.role != "admin":
        return {"error": "Unauthorized"}

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user and user.role == "tutor":
        user.is_verified = True
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/delete-user/{user_id}", response_model=None)
def delete_user(user_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Any:
    """Deactivate a user and their associated lessons (admin only)."""
    admin = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if not admin or admin.role != "admin":
        return {"error": "Unauthorized"}

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        user.is_active = False
        if user.role == "tutor":
            db.query(models.Lesson).filter(models.Lesson.teacher_id == user.id).update({"is_active": False})
        db.commit()

    return RedirectResponse(url="/admin?message=user_deactivated", status_code=303)


@app.post("/admin/delete-review/{review_id}")
def delete_review(review_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Any:
    """Remove a review from the system (admin only)."""
    admin = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if admin and admin.role == "admin":
        db.query(models.Review).filter(models.Review.id == review_id).delete()
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/delete-lesson/{lesson_id}")
def delete_lesson(lesson_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Any:
    """Deactivate a lesson and cancel future bookings (admin only)."""
    now = datetime.now()
    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    lesson.is_active = False

    bookings = db.query(models.Booking).filter(models.Booking.lesson_id == lesson_id).all()
    for b in bookings:
        app_time = b.appointment_time
        if isinstance(app_time, str):
            app_time = datetime.fromisoformat(app_time.replace(' ', 'T'))
        if app_time >= now:
            b.status = "Отменен от админ"
            db.add(models.Notification(user_id=b.client_id, message=f"Урокът '{lesson.subject}' беше премахнат."))

    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@app.get("/make-me-admin/{username}")
def make_admin(username: str, db: Session = Depends(get_db)) -> Any:
    """Grant admin privileges to a user (testing only)."""
    user = db.query(models.User).filter(models.User.username == username).first()
    if user:
        user.role = "admin"
        db.commit()
        return {"message": f"Потребител {username} вече е Админ!"}
    return {"error": "Потребителят не е намерен"}


@app.get("/checkout/{lesson_id}", response_class=HTMLResponse)
def checkout_page(lesson_id: int, request: Request, db: Session = Depends(get_db),
                  current_user_id: str = Cookie(None)) -> Any:
    """Render the lesson checkout page."""
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)

    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    if not lesson:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse("checkout.html", {"request": request, "lesson": lesson, "user_id": current_user_id})


@app.post("/process-payment/{lesson_id}")
def process_payment(lesson_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Any:
    """Simulate payment processing and record a new transaction."""
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)

    user_id, lesson = int(current_user_id), db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    booking = db.query(models.Booking).filter(
        models.Booking.lesson_id == lesson_id, models.Booking.client_id == user_id, models.Booking.status == "Потвърден"
    ).order_by(models.Booking.id.desc()).first()

    if booking:
        booking.status = "Платен"

    db.add(models.Transaction(
        client_id=user_id, teacher_id=lesson.teacher_id, lesson_id=lesson.id,
        amount=lesson.price, status="completed", payment_method="Карта (симулация)"
    ))
    db.commit()
    return RedirectResponse(url=f"/profile?message=success&paid_id={lesson_id}", status_code=303)


@app.post("/admin/restore-user/{user_id}", response_model=None)
def restore_user(user_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Any:
    """Restore a deactivated user account (admin only)."""
    admin = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if not admin or admin.role != "admin":
        return {"error": "Unauthorized"}

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        user.is_active = True
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)

