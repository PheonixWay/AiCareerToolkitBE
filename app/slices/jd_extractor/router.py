from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from .models import JobDescriptionRequest, ExtractedJobDescription
from .service import extract_jd_service
from app.slices.auth.dependencies import get_current_user

# We group all routes for this slice under /api/v1/jd
router = APIRouter(prefix="/api/v1/jd", tags=["JD Extractor"],dependencies=[Depends(get_current_user)])

@router.post("/extract", response_model=ExtractedJobDescription)
def extract_job_description(request: JobDescriptionRequest):
    try:
        # Pass the text to our AI service
        result = extract_jd_service(request.raw_text)
        return result
    except Exception as e:
        # If the AI fails or the JSON is bad, return a clean error to the frontend
        raise HTTPException(status_code=500, detail=str(e))