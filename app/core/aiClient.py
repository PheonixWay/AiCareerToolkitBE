from openai import OpenAI
from app.core.config import settings

# We configure the OpenAI client to point to Groq's fast, free endpoint
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=settings.GROQ_API_KEY
)