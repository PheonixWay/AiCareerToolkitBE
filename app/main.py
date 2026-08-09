from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.core.config import settings

class HealthResponse(BaseModel):
    status:str
    service:str
    api_key_configured:bool
    server_region:str
    
app=FastAPI(
    title="AI Career Toolkit API",
    description="Backend API for JD Extraction and Resume Optimization.Built with Modular Monolith architecture.",
    version="1.0.0",
    contact={
        "name":"Danish Sabbirasul Ansari",
        "url":"https://github.com/PheonixWay"
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/",tags=["General"])
def read_root():
    return {"message":"Welcome to AI Career Toolkit API"}

@app.get("/health",tags=["General"])
def health_check():
    return HealthResponse(
        status="healthy",
        service="AI Career Toolkit Backend",
        api_key_configured=bool(settings.OPENAI_API_KEY),
        server_region="Wani, Maharashtra (Local-Dev)" # Local testing environment
    )
