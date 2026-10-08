"""
Central Gemini client module for CHAI.

Built exclusively on the modern `google-genai` SDK (`from google import genai`).
Provides:
- One consistent shared client instance (`llm_client`)
- Native Pydantic structured output support
- Centralized schema compatibility transformation (`clean_gemini_schema`)
- Categorized, sanitized error reporting ([QUOTA_ERROR], [AUTH_ERROR], etc.)
- Safe timeouts and credential leak prevention
"""
import os
import re
import copy
import asyncio
from typing import Optional, Any, Union
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

from backend.config import get_settings
from backend.shared.logger import get_logger

logger = get_logger(__name__)


def get_default_gemini_model() -> str:
    """
    Returns the configured Gemini model name from GEMINI_MODEL env var,
    defaulting to 'gemini-flash-lite-latest'.
    """
    return os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest").strip() or "gemini-flash-lite-latest"


def get_gemini_api_key() -> str:
    """
    Safely retrieves the Gemini API key from environment variables or settings.
    Never logs or exposes the key value.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        try:
            api_key = get_settings().gemini_api_key
        except Exception:
            api_key = ""
    return (api_key or "").strip()


def _sanitize_error_message(msg: str) -> str:
    """Strip any API key patterns or sensitive tokens from error strings."""
    sanitized = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[REDACTED_API_KEY]", str(msg))
    sanitized = re.sub(r"key=[0-9A-Za-z-_]+", "key=[REDACTED]", sanitized)
    sanitized = re.sub(r"api_key=[0-9A-Za-z-_]+", "api_key=[REDACTED]", sanitized)
    return sanitized


sanitize_api_keys = _sanitize_error_message

DEFAULT_TIMEOUT_SECONDS = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "60.0"))


def classify_gemini_error(err: Exception) -> tuple[str, str]:
    """
    Categorizes Gemini errors into distinct, sanitized tags:
    [SDK_IMPORT_ERROR], [CONFIG_ERROR], [AUTH_ERROR], [QUOTA_ERROR],
    [TIMEOUT_ERROR], [NETWORK_ERROR], [SCHEMA_ERROR], [VALIDATION_ERROR],
    and [API_ERROR].
    """
    raw_str = str(err)
    sanitized = _sanitize_error_message(raw_str)
    err_lower = sanitized.lower()

    if isinstance(err, ImportError) or "no module named" in err_lower or "not installed" in err_lower:
        return "[SDK_IMPORT_ERROR]", f"Required Gemini SDK or dependency missing: {sanitized.splitlines()[0]}"
    if "not configured" in err_lower or "missing api key" in err_lower or "api key not provided" in err_lower:
        return "[CONFIG_ERROR]", "GEMINI_API_KEY is not configured in environment or config."
    if "validationerror" in err_lower or "validation error" in err_lower:
        return "[VALIDATION_ERROR]", f"Structured output Pydantic validation failed: {sanitized.splitlines()[0]}"
    if "429" in sanitized or "resource_exhausted" in err_lower or "quota" in err_lower:
        return "[QUOTA_ERROR]", "Gemini API quota exhausted (HTTP 429). Model call unavailable."
    if "401" in sanitized or "403" in sanitized or "unauthenticated" in err_lower or "invalid api key" in err_lower:
        return "[AUTH_ERROR]", f"Gemini API authentication failed: {sanitized.splitlines()[0]}"
    if isinstance(err, asyncio.TimeoutError) or "timeout" in err_lower or "deadline_exceeded" in err_lower:
        return "[TIMEOUT_ERROR]", f"Gemini API request timed out: {sanitized.splitlines()[0]}"
    if "schema" in err_lower or "unknown field" in err_lower:
        return "[SCHEMA_ERROR]", f"Gemini structured schema error: {sanitized.splitlines()[0]}"
    if "network" in err_lower or "connection" in err_lower or "econnrefused" in err_lower:
        return "[NETWORK_ERROR]", f"Gemini API network connection failure: {sanitized.splitlines()[0]}"
    return "[API_ERROR]", f"Gemini API error: {sanitized.splitlines()[0]}"


def clean_gemini_schema(schema: Any) -> Any:
    """
    Deterministically cleans a Pydantic model or JSON Schema dict for strict Gemini API compatibility.
    Inlines $defs/$ref, strips unsupported metadata (e.g. 'default', '$schema', 'examples')
    while strictly preserving:
    - required fields
    - enum/literal constraints
    - object structure & property types
    - nested objects
    - list item types
    """
    if isinstance(schema, type) and hasattr(schema, "model_json_schema"):
        raw_schema = schema.model_json_schema()
    elif isinstance(schema, dict):
        raw_schema = copy.deepcopy(schema)
    else:
        return schema

    defs = raw_schema.pop("$defs", {}) or raw_schema.pop("definitions", {})

    def _resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_key = node["$ref"].split("/")[-1]
                if ref_key in defs:
                    resolved = copy.deepcopy(defs[ref_key])
                    for k, v in node.items():
                        if k != "$ref":
                            resolved[k] = v
                    return _resolve(resolved)

            cleaned = {}
            for k, v in node.items():
                if k in ("default", "$schema", "examples"):
                    continue
                cleaned[k] = _resolve(v)
            return cleaned
        elif isinstance(node, list):
            return [_resolve(item) for item in node]
        return node

    return _resolve(raw_schema)


class GeminiClient:
    """
    Central Gemini client wrapper built exclusively on the modern `google-genai` SDK.
    Provides async content generation, typed structured output, safe timeouts,
    sanitized error classification, and quota awareness.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = (api_key or get_gemini_api_key()).strip()
        self.model_name = (model_name or get_default_gemini_model()).strip()
        self._client: Optional[Any] = None
        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError as ie:
                logger.error(f"[SDK_IMPORT_ERROR] google-genai package is not installed: {ie}")
            except Exception as e:
                logger.warning(f"[CONFIG_ERROR] Failed to initialize google-genai Client: {_sanitize_error_message(str(e))}")
        else:
            logger.warning("[CONFIG_ERROR] GEMINI_API_KEY is not configured.")

    async def generate_content(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        response_schema: Optional[Any] = None,
        response_mime_type: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """
        Asynchronously generates content from Gemini using the modern google-genai SDK.
        Supports system instructions, typed structured response schemas, and timeout bounds.
        """
        if not self.api_key or os.getenv("CHAI_MOCK_MODE", "").lower() in ("true", "1", "yes"):
            return "Mock response: API key not configured."

        if not self._client:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                err_cat, err_msg = classify_gemini_error(exc)
                raise RuntimeError(f"{err_cat} {err_msg}") from None

        effective_timeout = timeout or DEFAULT_TIMEOUT_SECONDS

        try:
            from google.genai import types

            config_kwargs: dict[str, Any] = {}
            if system_instruction:
                config_kwargs["system_instruction"] = system_instruction
            if temperature is not None:
                config_kwargs["temperature"] = temperature

            if response_schema is not None:
                config_kwargs["response_mime_type"] = "application/json"
                config_kwargs["response_schema"] = clean_gemini_schema(response_schema)
            elif response_mime_type:
                config_kwargs["response_mime_type"] = response_mime_type

            config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

            coro = self._client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            response = await asyncio.wait_for(coro, timeout=effective_timeout)
            return response.text or ""

        except asyncio.TimeoutError:
            err_cat, err_msg = classify_gemini_error(asyncio.TimeoutError(f"Call timed out after {effective_timeout}s"))
            logger.error(f"{err_cat} {err_msg}")
            raise RuntimeError(f"{err_cat} {err_msg}") from None

        except Exception as exc:
            err_cat, err_msg = classify_gemini_error(exc)
            logger.error(f"{err_cat} {err_msg}")
            raise RuntimeError(f"{err_cat} {err_msg}") from None

    generate = generate_content


def get_gemini_chat_model(
    model_name: Optional[str] = None,
    temperature: float = 0.2,
    api_key: Optional[str] = None,
):
    """
    Backward-compatible factory for LangChain ChatGoogleGenerativeAI if available.
    Active production agents use `llm_client` directly via google-genai.
    """
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        resolved_model = model_name or get_default_gemini_model()
        key = api_key or get_gemini_api_key()
        if not key:
            raise ValueError("[CONFIG_ERROR] GEMINI_API_KEY is not set.")
        return ChatGoogleGenerativeAI(
            model=resolved_model,
            temperature=temperature,
            api_key=key,
        )
    except ImportError:
        raise RuntimeError("[SDK_IMPORT_ERROR] langchain_google_genai is not installed. Use llm_client instead.")


llm_client = GeminiClient()
