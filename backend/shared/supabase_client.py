"""
Supabase client provider for CHAI platform backend.

Provides connection to Supabase PostgreSQL using SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY. The service-role key is strictly backend-only.
"""
import os
from typing import Optional
from supabase import create_client, Client
from backend.config import get_settings
from backend.shared.logger import get_logger

logger = get_logger(__name__)

_client: Optional[Client] = None


def get_supabase_client() -> Optional[Client]:
    """
    Retrieves or lazily initializes the Supabase client using
    SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from the environment or settings.

    Returns:
        Optional[Client]: Active Supabase client, or None if credentials are not configured.
    """
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    env_url = os.environ.get("SUPABASE_URL")
    url = (env_url if env_url is not None else (settings.supabase_url or "")).strip()

    env_service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    service_key = (env_service_key if env_service_key is not None else (settings.supabase_service_role_key or "")).strip()

    env_anon_key = os.environ.get("SUPABASE_ANON_KEY")
    anon_key = (env_anon_key if env_anon_key is not None else (settings.supabase_anon_key or "")).strip()

    env_pub_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    pub_key = (env_pub_key if env_pub_key is not None else (settings.supabase_publishable_key or "")).strip()

    key = service_key or anon_key or pub_key

    if not url or not key:
        logger.warning(
            "Supabase client not initialized: SUPABASE_URL or API key is not set."
        )
        return None

    try:
        _client = create_client(url, key)
        is_service_role = bool(service_key)
        key_type = "service-role (admin)" if is_service_role else "anon/publishable"
        logger.info(f"Supabase client initialized successfully with {key_type} key.")
        return _client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None


def reset_supabase_client() -> None:
    """Resets the cached Supabase client singleton (useful for testing)."""
    global _client
    _client = None
