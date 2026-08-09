from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.health import router as health_router

app = FastAPI(
    title="AI Career Toolkit API",
    description="Backend API for JD Extraction and Resume Optimization. Built with Modular Monolith architecture.",
    version="1.0.0",
    contact={
        "name": "Danish Sabbirasul Ansari",
        "url": "https://github.com/PheonixWay"
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


app.include_router(health_router)