from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    port: int = 8000
    environment: str = "development"
    frontend_url: str = "http://localhost:5173"
    
    gemini_api_key: str = ""
    
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
