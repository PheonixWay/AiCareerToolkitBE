from pydantic import BaseModel,Field
from typing import List

class JobDescriptionRequest(BaseModel):
    raw_text: str=Field(..., description="The raw text of the job description to be processed.")
    
class ExtractedJobDescription(BaseModel):
    job_title:str=Field(...,description="The title of the position")
    years_of_experience: str = Field(
        default="Not specified", 
        description="Required years of experience."
    )
    must_have_skills: List[str] = Field(..., description="List of mandatory technical skills.")
    good_to_have_skills: List[str] = Field(..., description="List of optional or bonus skills.")
    potential_interview_questions: List[str] = Field(
        ..., description="5 technical interview questions based on the required tech stack."
    )