"""
Debug Observability for CHAI (Coordinated Hybrid Agentic Intelligence).

Provides developer-only visibility into intermediate agent outputs across
the 12-stage pipeline when CHAI_DEBUG_AGENT_OUTPUTS is enabled.

CRITICAL SECURITY RULES:
- Never exposes secrets, API keys, bearer tokens, passwords, or credentials.
- Sanitizes all data structures recursively before printing.
- Disabled by default (CHAI_DEBUG_AGENT_OUTPUTS=false).
"""
import os
import re
import json
from typing import Any, Dict, List, Union
from pydantic import BaseModel

SENSITIVE_KEY_PATTERNS = [
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"auth(?:orization)?", re.IGNORECASE),
    re.compile(r"bearer", re.IGNORECASE),
    re.compile(r"private[_-]?key", re.IGNORECASE),
]

SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"AIzaSy[A-Za-z0-9_-]{33}"),  # Google API key pattern
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # Generic API key pattern
    re.compile(r"ghp_[A-Za-z0-9]{36}"),  # GitHub PAT
]

REDACTED = "***REDACTED***"


def is_debug_agent_outputs_enabled() -> bool:
    """Returns True if intermediate agent outputs should be printed to the debug stream."""
    return os.getenv("CHAI_DEBUG_AGENT_OUTPUTS", "false").lower() in ("true", "1", "yes")


def sanitize_debug_payload(payload: Any) -> Any:
    """
    Recursively strips or masks sensitive credentials from dictionaries,
    lists, and strings so they are safe to log in development.
    """
    if payload is None:
        return None

    if isinstance(payload, BaseModel):
        try:
            return sanitize_debug_payload(payload.model_dump())
        except Exception:
            return str(payload)

    if isinstance(payload, dict):
        sanitized_dict: Dict[str, Any] = {}
        for key, value in payload.items():
            str_key = str(key)
            if any(pat.search(str_key) for pat in SENSITIVE_KEY_PATTERNS):
                sanitized_dict[str_key] = REDACTED
            else:
                sanitized_dict[str_key] = sanitize_debug_payload(value)
        return sanitized_dict

    if isinstance(payload, (list, tuple)):
        return [sanitize_debug_payload(item) for item in payload]

    if isinstance(payload, str):
        sanitized_str = payload
        for pat in SENSITIVE_VALUE_PATTERNS:
            sanitized_str = pat.sub(REDACTED, sanitized_str)
        return sanitized_str

    return payload


def format_debug_payload(payload: Any) -> str:
    """Formats a sanitized payload into readable structured text."""
    sanitized = sanitize_debug_payload(payload)
    if isinstance(sanitized, (dict, list)):
        try:
            return json.dumps(sanitized, indent=2, default=str)
        except Exception:
            return str(sanitized)
    return str(sanitized)


def log_debug_agent_output(stage_name: str, payload: Any) -> None:
    """
    Prints a formatted debug banner for a pipeline stage if CHAI_DEBUG_AGENT_OUTPUTS is enabled.

    Example format:
    ================ RESEARCHER OUTPUT ================
    {
      "agent": "researcher",
      ...
    }
    """
    if not is_debug_agent_outputs_enabled():
        return

    try:
        header = f"================ {stage_name.strip().upper()} ================"
        body = format_debug_payload(payload)
        print(f"\n{header}\n{body}\n")
    except Exception as e:
        # Never fail execution because of debug logging
        print(f"\n================ {stage_name.strip().upper()} ================\n[Error formatting debug output: {e}]\n")
