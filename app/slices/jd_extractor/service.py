from openai import OpenAI
from app.core.config import settings
from .models import ExtractedJobDescription

# We configure the OpenAI client to point to Groq's fast, free endpoint
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=settings.OPENAI_API_KEY
)

def extract_jd_service(raw_text: str) -> ExtractedJobDescription:
    # We give the AI clear instructions and a strict JSON template to follow
    prompt = f"""
    You are an expert HR assistant. Extract the following information from the job description below.
    Respond ONLY with a valid JSON object matching this exact structure:
    {{
        "job_title": "string",
        "years_of_experience": "string",
        "must_have_skills": ["string"],
        "good_to_have_skills": ["string"],
        "potential_interview_questions": ["string", "string", "string", "string", "string"]
    }}

    Job Description:
    {raw_text}
    """

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant", # A very fast, free open-source model on Groq
        messages=[
            {"role": "system", "content": "You are a helpful assistant that outputs strict JSON."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.1 # Low temperature ensures it extracts facts without hallucinating
    )

    # Get the JSON string from the AI's response
    result_text = response.choices[0].message.content
    
    if result_text is None:
        raise ValueError("The model returned an empty response body.")

    # Pydantic automatically validates the string and converts it into our Python model
    return ExtractedJobDescription.model_validate_json(result_text)