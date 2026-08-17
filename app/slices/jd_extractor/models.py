from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Literal

class ExperienceInfo(BaseModel):
    min_years: float = Field(default=0.0, description="Minimum years of experience required. Strictly return 0.0 if for freshers or entry-level.")
    max_years: Optional[float] = Field(default=None, description="Maximum years of experience mentioned. Leave null if not mentioned.")
    is_fresher_allowed: bool = Field(default=False, description="True ONLY if the JD explicitly mentions freshers, graduates, or 0 years experience.")

class SkillSet(BaseModel):
    must_have_tech_skills: List[str] = Field(
        default_factory=list, 
        description="Strict mandatory technical tools, programming languages, or frameworks (e.g., 'React', 'Python', 'Docker'). Extract ONLY from the JD."
    )
    nice_to_have_tech_skills: List[str] = Field(
        default_factory=list, 
        description="Bonus, preferred, or 'nice to have' technical skills mentioned. Do not infer; extract only what is written."
    )
    soft_skills: List[str] = Field(
        default_factory=list, 
        description="Behavioral skills explicitly mentioned (e.g., 'Communication', 'Leadership', 'Agile')."
    )

class EducationInfo(BaseModel):
    minimum_degree: Optional[str] = Field(default="Not Specified", description="The lowest acceptable degree (e.g., 'B.Tech', 'Bachelor\\'s', 'Master\\'s'). Return 'Not Specified' if missing.")
    preferred_fields: List[str] = Field(default_factory=list, description="Preferred fields of study (e.g., 'Computer Science', 'Information Technology').")

class JDExtractionModel(BaseModel):
   
    job_title: str = Field(
        description="The exact title of the job role if explicitly mentioned. If NOT mentioned, analyze the entire JD and infer a highly relevant and standard professional job title (e.g., 'Senior Frontend Developer', 'Backend Engineer')."
    )
    company_name: Optional[str] = Field(default="Not Specified", description="Name of the hiring company. Return 'Not Specified' if missing.")
    location: Optional[str] = Field(default="Not Specified", description="Job location (City, State, Country, or 'Remote'). Return 'Not Specified' if missing.")
    
    employment_type: Literal["Full-time", "Part-time", "Contract", "Internship", "Freelance", "Not Specified"] = Field(
        default="Not Specified", 
        description="Classify the employment type strictly into one of the allowed categories."
    )
    department: Optional[str] = Field(default="Not Specified", description="Department or team name if mentioned (e.g., 'Engineering', 'Marketing').")
    
    experience: ExperienceInfo
    skills: SkillSet
    education: EducationInfo
    
    key_responsibilities: List[str] = Field(
        default_factory=list,
        description="Extract ALL distinct day-to-day responsibilities or tasks explicitly stated in the JD. DO NOT make up or hallucinate tasks. If only 1 or 2 are mentioned, return only those."
    )
    
    ats_keywords: List[str] = Field(
        default_factory=list,
        description="Extract a comprehensive list of crucial keywords for ATS optimization. Include highly repeated terms, core technologies, and key domain phrases present in the text."
    )


    @model_validator(mode='after')
    def clean_empty_strings(self):
        if not self.company_name or self.company_name.strip().lower() in ["none", "null", "na", "n/a"]:
            self.company_name = "Not Specified"
        if not self.location or self.location.strip().lower() in ["none", "null", "na", "n/a"]:
            self.location = "Not Specified"
        return self

