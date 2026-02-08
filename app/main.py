"""Main FastAPI application and routes."""
from typing import Optional
from pydantic import ValidationError
import hashlib
from typing import Optional, Dict, Union, Any
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

app = FastAPI(title="Частни уроци")


def hash_password(password: str) -> str:
    """Hash the user password."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify if the provided plain password matches the stored hash."""
    return hash_password(plain_password) == hashed_password


@app.get("/search", response_class=HTMLResponse, response_model=None)
def search_web(
    request: Request,
    db: Session = Depends(get_db),
    name: Optional[str] = None,
    category: Optional[str] = None,
    city: Optional[str] = None,
    current_user_id: Optional[str] = Cookie(None)
) -> HTMLResponse:
    """Search for lessons by subject, category, and city with verified teacher filtering."""
    query = db.query(models.Lesson).join(
        models.User, models.Lesson.teacher_id == models.User.id
    ).filter(models.User.is_verified == True)

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



@app.put("/users/{user_id}/address")
def update_address(user_id: int, new_address: str, db: Session = Depends(get_db)) -> Dict[str, str]:
    """Update the address for a specific user."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Не е намерен")
    user.address = new_address
    db.commit()
    return {"message": "Адресът е обновен!"}


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> HTMLResponse:
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
    """Handle registration using Pydantic schemas for validation."""
    
    try:
        user_data = schemas.UserCreate(
            first_name=first_name,
            username=username,
            email=email,
            password=password,
            phone=phone,
            role=role,
            address=address
        )
    except ValidationError as e:
        error_msg = e.errors()[0]['msg']
        return HTMLResponse(content=f"<script>alert('{error_msg}'); window.history.back();</script>")

    if db.query(models.User).filter(models.User.username == user_data.username).first():
        return HTMLResponse(content="<script>alert('Потребителското име е заето!');" \
        " window.history.back();</script>")

    new_user = models.User(
        first_name=user_data.first_name,
        username=user_data.username,
        email=user_data.email,
        password=hash_password(user_data.password),
        phone=user_data.phone,
        bio=bio,
        role=user_data.role,
        address=user_data.address
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    redirect_res = RedirectResponse(url="/profile", status_code=303)
    redirect_res.set_cookie(key="current_user_id", value=str(new_user.id), httponly=True)
    return redirect_res


@app.get("/", response_class=HTMLResponse, response_model=None)
def home_page(request: Request, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> HTMLResponse:
    """Render the home page with active lessons from verified tutors."""
    lessons = db.query(models.Lesson).join(
    models.User, models.Lesson.teacher_id == models.User.id
    ).filter(
    models.User.is_verified == True,
    models.Lesson.is_active == True
    ).all()
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
def login_page(request: Request) -> HTMLResponse:
    """Render the login HTML page."""
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login-web")
def login_web(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
) -> Any:
    """Authenticate user login using schemas."""
    try:
        login_data = schemas.UserLogin(email=email, password=password)
    except ValidationError:
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Невалиден формат на данните."
        })

    user = db.query(models.User).filter(models.User.email == login_data.email).first()
    
    if not user or not user.is_active:
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Профилът не съществува или е деактивиран."
        })

    if not verify_password(login_data.password, user.password):
        return HTMLResponse(content="<script>alert('Грешен имейл или парола!');" \
        " window.location.href='/login';</script>")
    
    url = "/admin" if user.role == "admin" else "/profile"
    redirect_res = RedirectResponse(url=url, status_code=303)
    redirect_res.set_cookie(key="current_user_id", value=str(user.id))
    return redirect_res


@app.get("/profile", response_class=HTMLResponse, response_model=None)
def profile_page(request: Request, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Union[HTMLResponse, RedirectResponse]:
    """Display the user's personal profile, bookings, and notifications."""
    if not current_user_id:
        return RedirectResponse(url='/login', status_code=303)

    user_id = int(current_user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()

    favorite_lessons = db.query(models.Lesson).join(models.Favorite).filter(
        models.Favorite.user_id == user_id, models.Lesson.is_active == True
    ).all()

    notifications = db.query(models.Notification).filter(
        models.Notification.user_id == user_id, models.Notification.is_read == False
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


@app.get("/edit-profile", response_class=HTMLResponse, response_model=None)
def edit_profile_page(request: Request, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Union[HTMLResponse, RedirectResponse]:
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
) -> RedirectResponse:
    if not current_user_id:
        return RedirectResponse(url='/login', status_code=303)

    try:
        updated_data = schemas.UserUpdate(
            first_name=first_name, phone=phone, address=address, bio=bio
        )
    except ValidationError as e:
        error_msg = e.errors()[0]['msg']
        return HTMLResponse(content=f"<script>alert('{error_msg}'); window.history.back();</script>")

    user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if user:
        user.first_name = updated_data.first_name
        user.phone = updated_data.phone
        user.address = updated_data.address
        if user.role == 'tutor':
            user.bio = updated_data.bio
        db.commit()

    return RedirectResponse(url="/profile", status_code=303)


@app.post("/book-lesson/{lesson_id}", response_model=None)
def book_lesson(
    lesson_id: int, 
    appointment_time: str = Form(...), 
    db: Session = Depends(get_db),
    current_user_id: str = Cookie(None)
) -> Union[HTMLResponse, RedirectResponse]:
    """Process a lesson booking request and notify the teacher."""
    if not current_user_id:
        return HTMLResponse(content="<script>alert('Моля, влезте в профила си!'); "
                                    "window.location.href='/login';</script>")

    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Урокът не е намерен")

    if not lesson.is_active:
        return HTMLResponse(content="<script>alert('Този урок вече не се предлага.');" \
        " window.history.back();</script>")

    teacher = db.query(models.User).filter(models.User.id == lesson.teacher_id).first()
    if not teacher or not teacher.is_verified:
        return HTMLResponse(content="<script>alert('Учителят все още не е одобрен от администратор.');" \
        " window.history.back();</script>")

    user_id = int(current_user_id)
    client_user = db.query(models.User).filter(models.User.id == user_id).first()

    new_booking = models.Booking(
        client_id=user_id, 
        lesson_id=lesson_id,
        appointment_time=appointment_time, 
        status="Заявен"
    )
    db.add(new_booking)
    msg = f"Имате нова резервация за {lesson.subject} от {client_user.username}!"
    new_notif = models.Notification(user_id=lesson.teacher_id, message=msg)
    db.add(new_notif)
    db.commit()

    return RedirectResponse(url="/profile?message=booked", status_code=303)


@app.post("/confirm-booking/{booking_id}")
def confirm_booking(booking_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    """Confirm a lesson booking and update its status."""
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if booking:
        booking.status = "Потвърден"
        db.commit()
    return RedirectResponse(url="/profile", status_code=303)


@app.get("/logout")
def logout() -> RedirectResponse:
    """Log out the user by deleting the session cookie."""
    redirect_res = RedirectResponse(url="/", status_code=303)
    redirect_res.delete_cookie("current_user_id")
    return redirect_res


@app.post("/update-booking/{booking_id}/{new_status}", response_model=None)
def update_booking(booking_id: int, new_status: str, db: Session = Depends(get_db)) -> Union[HTMLResponse, RedirectResponse]:
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
        if new_status == "Потвърден":
            msg = f"Вашият час по {booking.lesson.subject} за {pretty_date} ч. беше ПОТВЪРДЕН!"
            db.add(models.Notification(user_id=booking.client_id, message=msg))

    booking.status = new_status
    db.commit()
    return RedirectResponse(url="/profile", status_code=303)


@app.get("/public-profile/{user_id}", response_class=HTMLResponse, response_model=None)
def public_profile(request: Request, user_id: int, db: Session = Depends(get_db),
                   current_user_id: str = Cookie(None)) -> Union[HTMLResponse, Response]:
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
def delete_notification(notif_id: int, db: Session = Depends(get_db)) -> Dict[str, str]:
    """Delete a specific notification from the database."""
    db.query(models.Notification).filter(models.Notification.id == notif_id).delete()
    db.commit()
    return {"status": "success"}


@app.get("/add-lesson", response_class=HTMLResponse, response_model=None)
def add_lesson_page(request: Request, current_user_id: str = Cookie(None), db: Session = Depends(get_db)) -> Union[HTMLResponse, RedirectResponse]:
    """Render the page for adding a new lesson (tutors only)."""
    if not current_user_id:
        return RedirectResponse(url='/login')

    user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if user.role != "tutor":
        return HTMLResponse(content="<script>alert('Само учители могат да добавят уроци!'); "
                                    "window.location.href='/';</script>")

    return templates.TemplateResponse("add_lesson.html", {"request": request, "user": user})


@app.post("/create-lesson")
def create_lesson(
    subject: str = Form(...), category: str = Form(...), price: float = Form(...),
    db: Session = Depends(get_db), current_user_id: str = Cookie(None)
) -> RedirectResponse:
    try:
        lesson_data = schemas.LessonCreate(subject=subject, category=category, price=price)
    except ValidationError as e:
        return HTMLResponse(content=f"<script>alert('{e.errors()[0]['msg']}'); window.history.back();</script>")

    user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    new_lesson = models.Lesson(
        subject=lesson_data.subject, category=lesson_data.category, price=lesson_data.price,
        teacher_id=user.id, teacher_name=user.first_name or user.username,
        latitude=42.69, longitude=23.32
    )
    db.add(new_lesson)
    db.commit()
    return RedirectResponse(url="/profile", status_code=303)


@app.post("/favorites")
def add_to_favorites(lesson_id: int = Form(...), user_id: int = Form(...), db: Session = Depends(get_db)) -> RedirectResponse:
    """Add a lesson to the user's favorite list."""
    existing = db.query(models.Favorite).filter(
        models.Favorite.user_id == user_id, models.Favorite.lesson_id == lesson_id
    ).first()

    if not existing:
        db.add(models.Favorite(user_id=user_id, lesson_id=lesson_id))
        db.commit()

    return RedirectResponse(url="/?message=added", status_code=303)


@app.post("/remove-favorite/{lesson_id}")
def remove_favorite(lesson_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Dict[str, str]:
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


@app.post("/submit-review/{teacher_id}", response_model=None)
def submit_review(
    teacher_id: int, 
    rating: int = Form(...), 
    comment: str = Form(None),
    db: Session = Depends(get_db), 
    current_user_id: str = Cookie(None)
) -> Union[HTMLResponse, RedirectResponse]:
    """Submit a rating and comment using ReviewCreate schema for validation."""
    
    if not current_user_id:
        return RedirectResponse(url='/login', status_code=303)

    try:
        review_data = schemas.ReviewCreate(
            lesson_id=0, 
            rating=rating, 
            comment=comment
        )
    except ValidationError as e:
        error_msg = e.errors()[0]['msg']
        return HTMLResponse(content=f"<script>alert('{error_msg}'); window.history.back();</script>")

    user_id = int(current_user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if user.role != "client":
        return HTMLResponse(content="<script>alert('Само ученици могат да оставят ревюта!');" \
        " window.history.back();</script>")
    
    if user_id == teacher_id:
        return HTMLResponse(content="<script>alert('Не можете да оценявате себе си!'); " \
        "window.history.back();</script>")

    new_review = models.Review(
        teacher_id=teacher_id, 
        user_id=user_id, 
        rating=review_data.rating, 
        comment=review_data.comment
    )
    db.add(new_review)
    
    msg = f"Ученикът {user.username} ви остави оценка {review_data.rating} ⭐!"
    db.add(models.Notification(user_id=teacher_id, message=msg))
    
    db.commit()

    return RedirectResponse(url=f"/public-profile/{teacher_id}", status_code=303)


@app.post("/cancel-booking/{booking_id}")
def cancel_booking(
    booking_id: int, 
    db: Session = Depends(get_db), 
    current_user_id: str = Cookie(None)
) -> RedirectResponse:
    """Cancel a booking and notify the other party with full details."""
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)

    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        return RedirectResponse(url="/profile", status_code=303)

    user_id = int(current_user_id)
    
    subject = booking.lesson.subject
    pretty_date = booking.appointment_time.replace('T', ' ')
    teacher_id = booking.lesson.teacher_id
    client_id = booking.client_id
    
    if user_id == teacher_id:
        receiver_id = client_id
        msg = f"Преподавателят отмени часа по {subject} за {pretty_date} ч."
    else:
        receiver_id = teacher_id
        client_name = db.query(models.User).filter(models.User.id == user_id).first().username
        msg = f"Ученикът {client_name} отмени часа по {subject} за {pretty_date} ч."

    new_notif = models.Notification(user_id=receiver_id, message=msg)
    db.add(new_notif)
    db.delete(booking)
    db.commit()

    return RedirectResponse(url="/profile?message=cancelled", status_code=303)

@app.get("/admin", response_class=HTMLResponse, response_model=None)
def admin_panel(request: Request, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Union[HTMLResponse, RedirectResponse]:
    """Render the admin dashboard with system stats and user management."""
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)

    admin_user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if not admin_user or admin_user.role != "admin":
        return HTMLResponse(content="<script>alert('Нямате права!'); window.location.href='/';</script>")

    users, reviews, lessons = db.query(models.User).all(), db.query(models.Review).all(), db.query(models.Lesson).all()
    stats = {
        "total_users": len(users), "tutors_count": len([u for u in users if u.role == 'tutor']),
        "pending_verifications": len([u for u in users if u.role == 'tutor' and not u.is_verified]),
        "total_reviews": len(reviews)
    }

    return templates.TemplateResponse("admin_panel.html", {
        "request": request, "users": users, "reviews": reviews, "lessons": lessons,
        "admin_name": admin_user.username, "stats": stats, "transactions": db.query(models.Transaction).all()
    })


@app.post("/admin/verify-tutor/{user_id}", response_model=None)
def verify_tutor(user_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Union[Dict[str, str], RedirectResponse]:
    """Approve a tutor's verification request (admin only)."""
    
    admin_user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if not admin_user or admin_user.role != "admin":
        return {"error": "Unauthorized"}

    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if user and user.role == "tutor":
        user.is_verified = True
        db.query(models.Lesson).filter(
            models.Lesson.teacher_id == user_id
        ).update({models.Lesson.is_active: True})
        
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/delete-user/{user_id}", response_model=None)
def delete_user(user_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Union[Dict[str, str], RedirectResponse]:
    """Deactivate a user and their associated lessons (admin only)."""
    admin_user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if not admin_user or admin_user.role != "admin":
        return {"error": "Unauthorized"}

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        user.is_active = False
        if user.role == "tutor":
            db.query(models.Lesson).filter(models.Lesson.teacher_id == user.id).update({"is_active": False})
        db.commit()

    return RedirectResponse(url="/admin?message=user_deactivated", status_code=303)


@app.post("/admin/delete-review/{review_id}")
def delete_review(review_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> RedirectResponse:
    """Remove a review from the system (admin only)."""
    admin_user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if admin_user and admin_user.role == "admin":
        db.query(models.Review).filter(models.Review.id == review_id).delete()
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/delete-lesson/{lesson_id}")
def delete_lesson(lesson_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> RedirectResponse:
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


@app.get("/make-me-admin/{username}")#ами предполагам че не беше много адекватен начен  така да правя админа но работи
def make_admin(username: str, db: Session = Depends(get_db)) -> Dict[str, str]:
    """Grant admin privileges to a user (testing only)."""
    user = db.query(models.User).filter(models.User.username == username).first()
    if user:
        user.role = "admin"
        db.commit()
        return {"message": f"Потребител {username} вече е Админ!"}
    return {"error": "Потребителят не е намерен"}


@app.get("/checkout/{lesson_id}", response_class=HTMLResponse, response_model=None)
def checkout_page(lesson_id: int, request: Request, db: Session = Depends(get_db),
                  current_user_id: str = Cookie(None)) -> Union[HTMLResponse, RedirectResponse]:
    """Render the lesson checkout page."""
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)

    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    if not lesson:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse("checkout.html", {"request": request, "lesson": lesson, "user_id": current_user_id})


@app.post("/process-payment/{lesson_id}")
def process_payment(lesson_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> RedirectResponse:
    """Simulate payment processing and record a new transaction."""
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)

    user_id_int = int(current_user_id)
    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    booking = db.query(models.Booking).filter(
        models.Booking.lesson_id == lesson_id, models.Booking.client_id == user_id_int,
          models.Booking.status == "Потвърден"
    ).first()

    if not booking:
        return HTMLResponse("<script>alert('Няма потвърдена резервация за плащане!'); " \
        "window.location.href='/profile';</script>")

    booking.status = "Платен"

    db.add(models.Transaction(
        client_id=user_id_int, teacher_id=lesson.teacher_id, lesson_id=lesson.id,
        amount=lesson.price, status="completed", payment_method="Карта"
    ))
    db.commit()
    return RedirectResponse(url=f"/profile?message=success&paid_id={lesson_id}", status_code=303)


@app.post("/admin/restore-user/{user_id}", response_model=None)
def restore_user(user_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)) -> Union[Dict[str, str], RedirectResponse]:
    """Restore a deactivated user account (admin only)."""
    admin_user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if not admin_user or admin_user.role != "admin":
        return {"error": "Unauthorized"}

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        user.is_active = True
        db.query(models.Lesson).filter(
            models.Lesson.teacher_id == user_id
        ).update({models.Lesson.is_active: True})
        
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)

