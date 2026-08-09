from fastapi import APIRouter
from pydantic import BaseModel
from app.core.config import settings


router = APIRouter(tags=["General"])


class HealthResponse(BaseModel):
    status: str
    service: str
    api_key_configured: bool
    server_region: str

@router.get("/")
def read_root():
    return {"message": "Welcome to AI Career Toolkit API"}

@router.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="healthy",
        service="AI Career Toolkit Backend",
        api_key_configured=bool(settings.OPENAI_API_KEY),
        server_region="Wani, Maharashtra (Local-Dev)"
    )