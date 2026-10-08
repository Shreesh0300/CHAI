from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", protected_namespaces=(), extra="ignore")

    port: int = 8000
    environment: str = "development"
    frontend_url: str = "http://localhost:5173"
    
    gemini_api_key: str = ""
    
    database_url: str = ""

    supabase_url: str = ""
    supabase_service_role_key: str = ""

    web_search_api_key: str = ""
    web_search_max_results: int = 5
    web_fetch_timeout_seconds: float = 10.0
    web_fetch_max_bytes: int = 2000000

    api_source_enabled: bool = True
    api_source_url: str = "https://api.frankfurter.app/latest?from=USD"
    model_knowledge_enabled: bool = True

@lru_cache()
def get_settings():
    return Settings()
