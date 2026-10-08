"""
Supabase client provider for CHAI platform backend.

Provides connection to Supabase PostgreSQL using SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY. The service-role key is strictly backend-only.
"""
import os
from typing import Optional
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from supabase import create_client, Client
from backend.config import get_settings
from backend.shared.logger import get_logger

logger = get_logger(__name__)

_client: Optional[Client] = None


def get_supabase_client(access_token: Optional[str] = None) -> Optional[Client]:
    """
    Retrieves or lazily initializes the Supabase client using
    SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or anon key fallback)
    from the environment or settings.
    """
    global _client

    settings = get_settings()
    if os.getenv("SUPABASE_URL") == "":
        url = ""
    else:
        url = (
            os.getenv("SUPABASE_URL")
            or getattr(settings, "supabase_url", None)
            or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
            or ""
        ).strip()
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or getattr(settings, "supabase_service_role_key", "")
        or os.getenv("SUPABASE_ANON_KEY")
        or getattr(settings, "supabase_anon_key", "")
        or os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or getattr(settings, "supabase_publishable_key", "")
        or os.getenv("VITE_SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
        or ""
    ).strip()

    if not url or not key:
        logger.warning(
            "Supabase client not initialized: SUPABASE_URL or API keys are not set."
        )
        return None

    try:
        if access_token:
            user_client = create_client(url, key)
            user_client.postgrest.auth(access_token)
            try:
                user_client.postgrest.session.headers["authorization"] = f"Bearer {access_token}"
            except Exception:
                pass
            return user_client

        if _client is not None:
            return _client

        _client = create_client(url, key)
        logger.info("Supabase client initialized successfully.")
        return _client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None


def reset_supabase_client() -> None:
    """Resets the cached Supabase client singleton (useful for testing)."""
    global _client
    _client = None
