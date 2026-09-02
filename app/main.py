import os

from fastapi import FastAPI, Depends, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import User, Upload
from app.auth import hash_password, verify_password
from app.csv_ingest import parse_and_validate, apply_upload, CSVValidationError
from app.dashboard import compute_dashboard

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Retail-Pulse")

# SECRET_KEY must be set in production (Render/host env vars) - the
# fallback here is only for local dev and is NOT safe to deploy with.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-change-me")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

templates = Jinja2Templates(directory="app/templates")


def _user_or_none(request: Request, db: Session):
    user_id = request.session.get("user_id")
    return db.query(User).filter(User.id == user_id).first() if user_id else None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = _user_or_none(request, db)
    return RedirectResponse("/dashboard" if user else "/login")


@app.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "user": None})


@app.post("/signup", response_class=HTMLResponse)
async def signup(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    shop_name, email, password = form.get("shop_name", "").strip(), form.get("email", "").strip().lower(), form.get("password", "")

    if not shop_name or not email or len(password) < 8:
        return templates.TemplateResponse("signup.html", {
            "request": request, "user": None,
            "error": "All fields are required; password must be at least 8 characters.",
        })
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse("signup.html", {
            "request": request, "user": None, "error": "An account with that email already exists.",
        })

    user = User(email=email, password_hash=hash_password(password), shop_name=shop_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "user": None})


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    email, password = form.get("email", "").strip().lower(), form.get("password", "")

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request, "user": None, "error": "Incorrect email or password.",
        })
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = _user_or_none(request, db)
    if not user:
        return RedirectResponse("/login")
    data = compute_dashboard(db, user.id)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "data": data})


@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request, db: Session = Depends(get_db)):
    user = _user_or_none(request, db)
    if not user:
        return RedirectResponse("/login")
    uploads = (
        db.query(Upload).filter(Upload.user_id == user.id)
        .order_by(Upload.uploaded_at.desc()).limit(10).all()
    )
    return templates.TemplateResponse("upload.html", {"request": request, "user": user, "uploads": uploads})


@app.post("/upload", response_class=HTMLResponse)
async def upload_csv(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = _user_or_none(request, db)
    if not user:
        return RedirectResponse("/login")

    raw = await file.read()
    uploads_ctx = lambda **kw: templates.TemplateResponse("upload.html", {
        "request": request, "user": user,
        "uploads": db.query(Upload).filter(Upload.user_id == user.id).order_by(Upload.uploaded_at.desc()).limit(10).all(),
        **kw,
    })

    try:
        rows = parse_and_validate(raw)
    except CSVValidationError as e:
        db.add(Upload(user_id=user.id, filename=file.filename, row_count=0, status="REJECTED", message=str(e)))
        db.commit()
        return uploads_ctx(error=f"Upload rejected: {e}")

    upload_record = Upload(user_id=user.id, filename=file.filename, row_count=len(rows), status="OK")
    db.add(upload_record)
    db.commit()
    db.refresh(upload_record)

    apply_upload(db, user.id, upload_record.id, rows)

    return uploads_ctx(ok=f"{len(rows)} rows processed from {file.filename}")


@app.get("/sample.csv")
def sample_csv():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_data", "sample_upload.csv")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return PlainTextResponse(content, media_type="text/csv")
