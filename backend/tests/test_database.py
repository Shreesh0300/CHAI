"""
Tests for Supabase Database Schema and Backend Client.

Validates:
1. Migration file existence and structural integrity (all 6 required tables).
2. Proper foreign key and RLS definitions in PostgreSQL migration.
3. Supabase client graceful handling of missing credentials.
4. Supabase client initialization when configured.
"""
import os
import re
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from backend.shared.supabase_client import get_supabase_client, reset_supabase_client


def test_migration_file_exists_and_defines_six_tables():
    """Verify 001_initial_schema.sql exists and creates all 6 required tables."""
    migration_path = Path("supabase/migrations/001_initial_schema.sql")
    assert migration_path.exists(), "Migration file 001_initial_schema.sql does not exist"

    content = migration_path.read_text(encoding="utf-8")
    assert len(content) > 500

    required_tables = [
        "profiles",
        "solve_requests",
        "agent_outputs",
        "evaluations",
        "security_findings",
        "sources",
    ]

    found_tables = re.findall(r"CREATE TABLE IF NOT EXISTS public\.(\w+)", content)
    for table in required_tables:
        assert table in found_tables, f"Table '{table}' not found in migration"

    # Verify RLS enabled on all 6 tables
    rls_tables = re.findall(r"ALTER TABLE public\.(\w+)\s+ENABLE ROW LEVEL SECURITY;", content)
    for table in required_tables:
        assert table in rls_tables, f"Table '{table}' does not have RLS enabled"

    # Verify foreign keys
    assert "REFERENCES auth.users(id)" in content
    assert "REFERENCES public.solve_requests(id)" in content


def test_supabase_client_unconfigured_returns_none():
    """Verify get_supabase_client returns None gracefully without raising when unconfigured."""
    reset_supabase_client()
    with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}):
        client = get_supabase_client()
        assert client is None
    reset_supabase_client()


def test_supabase_client_configured_initializes():
    """Verify get_supabase_client initializes client when credentials provided."""
    reset_supabase_client()
    with patch.dict(
        os.environ,
        {
            "SUPABASE_URL": "https://testproject.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key-12345",
        },
    ):
        with patch("backend.shared.supabase_client.create_client") as mock_create:
            mock_instance = MagicMock()
            mock_create.return_value = mock_instance
            client = get_supabase_client()
            assert client is not None
            mock_create.assert_called_once_with(
                "https://testproject.supabase.co",
                "test-service-key-12345",
            )
    reset_supabase_client()
