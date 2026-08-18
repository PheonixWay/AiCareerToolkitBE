from pydantic_settings import BaseSettings,SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    GROQ_API_KEY: str = Field(..., description="OpenAI API Key for accessing OpenAI services.")
    DATABASE_URL: str = Field(..., description="Database connection URL for the application.")
    JWT_SECRET_KEY: str = Field(..., description="Secret key for generating JWT tokens.")
    JWT_ALGORITHM: str = Field(..., description="Algorithm for generating JWT tokens.")
    TOKEN_EXPIRY: str = Field(...,description="Token Expiry time for JWT tokens.")
    ADMIN_NAME: str = Field(...,description="Admin Username For seed")
    ADMIN_PASSWORD: str = Field(...,description="Admin Password for Seed")
    GOOGLE_API_KEY:str = Field(...,description="Google Gemini Api Key")
    model_config=SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    

settings=Settings() # type: ignore