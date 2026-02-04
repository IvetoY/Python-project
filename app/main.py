import math
import hashlib
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Request, Form, Response, Cookie
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi.responses import RedirectResponse

from . import models, schemas
from .database import engine, get_db

templates = Jinja2Templates(directory="templates")

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Посредник за услуги наблизо - Backend")

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371 
    dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))

def hash_password(password: str):#kaloqn taka kaza
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password, hashed_password):
    return hash_password(plain_password) == hashed_password

@app.get("/search", response_class=HTMLResponse)
def search_web(
    request: Request, 
    name: str = None, 
    category: str = None, 
    city: str = None, 
    db: Session = Depends(get_db),
    current_user_id: str = Cookie(None)
):
    query = db.query(models.Lesson).join(models.User, models.Lesson.teacher_id == models.User.id)
    
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
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = models.User(email=user.email, password=user.password, role=user.role)
    db.add(db_user)
    db.commit()
    return {"message": "Успешна регистрация!"}

@app.post("/bookings")
def book(data: schemas.BookingCreate, db: Session = Depends(get_db)):
    new_booking = models.Booking(
        client_id=data.client_id, 
        lesson_id=data.lesson_id, 
        appointment_time=data.appointment_time
    )
    db.add(new_booking)
    db.commit()
    return {"message": "Резервацията е създадена!"}


@app.get("/admin/users")
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()

@app.put("/admin/verify-tutor/{user_id}")
def verify(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        user.is_verified = True
        db.commit()
        return {"message": "Учителят е верифициран!"}
    raise HTTPException(status_code=404, detail="Не е намерен")

@app.get("/setup")#za testove beshe
def setup(db: Session = Depends(get_db)):
    db.query(models.Review).delete()
    db.query(models.Favorite).delete()
    db.query(models.Booking).delete()
    db.query(models.Lesson).delete()
    db.query(models.User).delete()
    
    tutor1 = models.User(
        email="ivan.ivanov@example.com",
        username="ivan_tutor",
        password=hash_password("123"), # (парола) крие я 
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
def update_address(user_id: int, new_address: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Не е намерен")
    user.address = new_address
    db.commit()
    return {"message": "Адресът е обновен!"}

@app.get("/users/{user_id}/bookings")
def get_user_bookings(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.Booking).filter(models.Booking.client_id == user_id).all()

@app.post("/messages/send")
def send_message(to_user_id: int, text: str, db: Session = Depends(get_db)):
    db.add(models.Notification(user_id=to_user_id, message=text))
    db.commit()
    return {"status": "Изпратено!"}

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
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
):
    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        return HTMLResponse(content="<script>alert('Потребителското име е заето!'); window.history.back();</script>")
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
def home_page(request: Request, db: Session = Depends(get_db), current_user_id: str = Cookie(None)):
    lessons = db.query(models.Lesson).all()
    
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
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login-web")
def login_web(
    response: Response, 
    email: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(password, user.password):
        return HTMLResponse(content="<script>alert('Грешен имейл или парола!'); window.location.href='/login';</script>")
    
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="current_user_id", value=str(user.id), httponly=True)
    return response

@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db), current_user_id: str = Cookie(None)):
    if not current_user_id:
        return RedirectResponse(url='/login', status_code=303)
    
    user_id = int(current_user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    notifications = db.query(models.Notification).filter(models.Notification.user_id == user_id).all()
    favorite_lessons = db.query(models.Lesson).join(models.Favorite).filter(models.Favorite.user_id == user_id).all()

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
            except:
                b.appointment_time = now

        if b.appointment_time < now:
            if b.status != "Отказан":
                b.status = "Проведен"
            history_bookings.append(b)
        else:
            upcoming_bookings.append(b)
                
    return templates.TemplateResponse("profile.html", {
        "request": request, 
        "user": user,
        "bookings": upcoming_bookings,
        "history_bookings": history_bookings,
        "notifications": notifications,
        "favorite_lessons": favorite_lessons,
        "now": now
    })

@app.get("/edit-profile", response_class=HTMLResponse)
def edit_profile_page(request: Request, db: Session = Depends(get_db), current_user_id: str = Cookie(None)):
    if not current_user_id:
        return RedirectResponse(url='/login', status_code=303)
    
    user_id = int(current_user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return templates.TemplateResponse("edit_profile.html", {"request": request, "user": user})

@app.post("/update-profile")
def update_profile(
    first_name: str = Form(None),
    phone: str = Form(None),
    address: str = Form(None),
    bio: str = Form(None),
    db: Session = Depends(get_db),
    current_user_id: str = Cookie(None)
):
    if not current_user_id:
        return RedirectResponse(url='/login', status_code=303)

    user_id = int(current_user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if user:
        user.first_name = first_name
        user.phone = phone
        user.address = address
        if user.role == 'tutor':
            user.bio = bio
        db.commit()
    
    return RedirectResponse(url="/profile", status_code=303)

@app.post("/book-lesson/{lesson_id}")
def book_lesson(
    lesson_id: int, 
    appointment_time: str = Form(...),
    db: Session = Depends(get_db), 
    current_user_id: str = Cookie(None)
):
    if not current_user_id:
        return HTMLResponse(content="<script>alert('Моля, влезте в профила си!'); window.location.href='/login';</script>")

    user_id = int(current_user_id)
    client = db.query(models.User).filter(models.User.id == user_id).first()
    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    
    if not lesson:
        raise HTTPException(status_code=404, detail="Урокът не е намерен")
    
    new_booking = models.Booking(
        client_id=user_id,
        lesson_id=lesson_id,
        appointment_time=appointment_time,
        status="Заявен"
    )
    db.add(new_booking)
    
    msg = f"Имате нова резервация за {lesson.subject} от {client.username}!"
    db.add(models.Notification(user_id=lesson.teacher_id, message=msg))
    
    db.commit()
    
    return RedirectResponse(url="/profile", status_code=303)

@app.post("/confirm-booking/{booking_id}")
def confirm_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if booking:
        booking.status = "Потвърден"
        db.commit()
    return RedirectResponse(url="/profile", status_code=303)

@app.get("/logout")
def logout(response: Response):
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("current_user_id")
    return response

@app.post("/update-booking/{booking_id}/{new_status}")
def update_booking(booking_id: int, new_status: str, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    
    if booking:
        if new_status == "Отказан":
            pretty_date = booking.appointment_time.replace('T', ' ')
            msg = f"Вашият час по {booking.lesson.subject} за {pretty_date} ч. беше отказан от преподавателя."
            
            new_notif = models.Notification(user_id=booking.client_id, message=msg)
            db.add(new_notif)
            db.delete(booking)
            db.commit()
            return HTMLResponse(content="<script>alert('Резервацията е отказана успешно.'); window.location.href='/profile';</script>")
        
        booking.status = new_status
        db.commit()
    return RedirectResponse(url="/profile", status_code=303)

@app.get("/public-profile/{user_id}", response_class=HTMLResponse)
def public_profile(request: Request, user_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)):
    print(f"DEBUG: Отварям профил на потребител с ID: {user_id}")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return HTMLResponse(content="<script>alert('Потребителят не е намерен!'); window.history.back();</script>")
    
    teacher_lessons = db.query(models.Lesson).filter(models.Lesson.teacher_id == user_id).all()
    
    reviews = db.query(models.Review).filter(models.Review.teacher_id == user_id).order_by(models.Review.created_at.desc()).all()
    
    return templates.TemplateResponse("public_profile.html", {
        "request": request,
        "user": user,
        "lessons": teacher_lessons,
        "reviews": reviews,
        "eur_rate": 1.95583,
        "is_logged_in": True if current_user_id else False,
        "current_user_id": int(current_user_id) if current_user_id else None
    })

@app.post("/delete-notification/{notif_id}")
def delete_notification(notif_id: int, db: Session = Depends(get_db)):
    notif = db.query(models.Notification).filter(models.Notification.id == notif_id).first()
    if not notif:
        return {"status": "error", "message": "Известието не е намерено"}
    db.delete(notif)
    db.commit()
    return {"status": "success"}

@app.get("/add-lesson", response_class=HTMLResponse)
def add_lesson_page(request: Request, current_user_id: str = Cookie(None), db: Session = Depends(get_db)):
    if not current_user_id:
        return HTMLResponse(content="<script>window.location.href='/login';</script>")
    
    user = db.query(models.User).filter(models.User.id == int(current_user_id)).first()
    if user.role != "tutor":
        return HTMLResponse(content="<script>alert('Само учители могат да добавят уроци!'); window.location.href='/';</script>")
    
    return templates.TemplateResponse("add_lesson.html", {"request": request, "user": user})

@app.post("/create-lesson")
def create_lesson(
    subject: str = Form(...),
    category: str = Form(...),
    price: float = Form(...),
    db: Session = Depends(get_db),
    current_user_id: str = Cookie(None)
):
    user_id = int(current_user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()

    new_lesson = models.Lesson(
        subject=subject,
        category=category,
        price=price,
        teacher_id=user.id,
        teacher_name=user.first_name or user.username,
        latitude=42.69,
        longitude=23.32
    )
    db.add(new_lesson)
    db.commit()
    return RedirectResponse(url="/profile", status_code=303)

@app.post("/favorites")
def add_to_favorites(
    lesson_id: int = Form(...), 
    user_id: int = Form(...), 
    db: Session = Depends(get_db)
):
    existing = db.query(models.Favorite).filter(
        models.Favorite.user_id == user_id, 
        models.Favorite.lesson_id == lesson_id
    ).first()
    
    if not existing:
        new_fav = models.Favorite(user_id=user_id, lesson_id=lesson_id)
        db.add(new_fav)
        db.commit()
    
    return RedirectResponse(url="/?message=added", status_code=303)

@app.post("/remove-favorite/{lesson_id}")
def remove_favorite(lesson_id: int, db: Session = Depends(get_db), current_user_id: str = Cookie(None)):
    if not current_user_id:
        return {"error": "Not logged in"}
    
    fav = db.query(models.Favorite).filter(
        models.Favorite.user_id == int(current_user_id),
        models.Favorite.lesson_id == lesson_id
    ).first()
    
    if fav:
        db.delete(fav)
        db.commit()
    return {"status": "success"}


@app.post("/submit-review/{teacher_id}")
def submit_review(
    teacher_id: int,
    rating: int = Form(...),
    comment: str = Form(None),
    db: Session = Depends(get_db),
    current_user_id: str = Cookie(None)
):
    if not current_user_id:
        return HTMLResponse(content="<script>alert('Трябва да сте влезли в профила си, за да оставите ревю!'); window.location.href='/login';</script>")

    user_id = int(current_user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if user.role != "client":
        return HTMLResponse(content="<script>alert('Само ученици могат да оставят ревюта!'); window.history.back();</script>")

    if user_id == teacher_id:
        return HTMLResponse(content="<script>alert('Не можете да оценявате сами себе си!'); window.history.back();</script>")

    new_review = models.Review(
        teacher_id=teacher_id,
        user_id=user_id,
        rating=rating,
        comment=comment
    )
    db.add(new_review)

    notification_msg = f"Ученикът {user.username} ви остави оценка {rating} ⭐!"
    db.add(models.Notification(user_id=teacher_id, message=notification_msg))

    db.commit()
    return RedirectResponse(url=f"/public-profile/{teacher_id}", status_code=303)

@app.post("/cancel-booking/{booking_id}")
def cancel_booking(
    booking_id: int, 
    db: Session = Depends(get_db), 
    current_user_id: str = Cookie(None)
):
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)
    
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        return RedirectResponse(url="/profile", status_code=303)

    user_id = int(current_user_id)
    teacher_id = booking.lesson.teacher_id
    client_id = booking.client_id

    if user_id == teacher_id:
        receiver_id = client_id
        msg = f"Преподавателят отмени вашия час за {booking.lesson.subject}."
    else:
        receiver_id = teacher_id
        msg = f"Ученикът отмени часа си за {booking.lesson.subject}."

    new_notif = models.Notification(user_id=receiver_id, message=msg)
    db.add(new_notif)
    
    db.delete(booking)
    db.commit()
    
    return RedirectResponse(url="/profile", status_code=303)