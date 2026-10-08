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
    url = (os.getenv("SUPABASE_URL") or settings.supabase_url or "").strip()
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or settings.supabase_service_role_key or "").strip()

    if not url or not key:
        logger.warning(
            "Supabase client not initialized: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set."
        )
        return None

    try:
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
