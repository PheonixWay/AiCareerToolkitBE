from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import Base, engine, SessionLocal
from sqlalchemy.exc import IntegrityError
from app.api.health import router as health_router
from app.slices.jd_extractor.router import router as jd_router
from app.slices.auth import models as auth_models
from app.core.security import get_password_hash
from app.core.config import settings
from app.slices.auth.router import router as auth_router
app = FastAPI(
    title="AI Career Toolkit API",
    description="Backend API for JD Extraction and Resume Optimization. Built with Modular Monolith architecture.",
    version="1.0.0",
    contact={
        "name": "Danish Sabbirasul Ansari",
        "url": "https://github.com/PheonixWay"
    }
)

# Create tables in Postgres
Base.metadata.create_all(bind=engine)

# Seed Data Function
def seed_admin_user():
    db = SessionLocal()
    try:
        # Check if the configured admin username already exists.
        user = db.query(auth_models.User).filter(auth_models.User.username == settings.ADMIN_NAME).first()
        if not user:
            print("Seeding admin user into PostgreSQL...")
            hashed_pw = get_password_hash(settings.ADMIN_PASSWORD)
            admin_user = auth_models.User(username=settings.ADMIN_NAME, hashed_password=hashed_pw)
            db.add(admin_user)
            db.commit()
    except IntegrityError:
        # In reload/concurrent startup scenarios, another process may seed first.
        db.rollback()
    finally:
        db.close()

# Run seed function exactly once when app starts
seed_admin_user()



app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173","https://ai-career-toolkit-fe.vercel.app/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(jd_router)