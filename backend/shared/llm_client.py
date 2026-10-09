import os
import time
import asyncio
import copy
from typing import Optional, Tuple, Any
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

from backend.config import get_settings
from backend.shared.logger import get_logger

logger = get_logger(__name__)


_QUOTA_EXHAUSTED_UNTIL = 0.0


def is_quota_exhausted() -> bool:
    """Returns True if Gemini API quota was recently detected as exhausted."""
    return time.time() < _QUOTA_EXHAUSTED_UNTIL


def mark_quota_exhausted(seconds: float = 60.0):
    """Marks Gemini API quota as exhausted for a specified duration."""
    global _QUOTA_EXHAUSTED_UNTIL
    _QUOTA_EXHAUSTED_UNTIL = time.time() + seconds


def classify_gemini_error(err: Exception) -> Tuple[str, str]:
    """Classifies Gemini API exceptions into standard category tags and sanitized messages."""
    sanitized = str(err)
    err_lower = sanitized.lower()
    if "429" in sanitized or "resource_exhausted" in err_lower or "quota" in err_lower or "rate limit" in err_lower:
        mark_quota_exhausted(60.0)
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


def get_default_gemini_model() -> str:
    """
    Returns the configured Gemini model name from GEMINI_MODEL env var,
    defaulting to the current stable model: 'gemini-3.1-flash-lite'.
    """
    return os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip() or "gemini-3.1-flash-lite"


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


def get_gemini_chat_model(
    model_name: Optional[str] = None,
    temperature: float = 0.2,
    api_key: Optional[str] = None,
):
    """
    Initializes and returns a LangChain ChatGoogleGenerativeAI instance with fast fallback.
    Defaults to 'gemini-3.1-flash-lite' or GEMINI_MODEL environment variable.
    Raises ValueError if no API key is provided or present in environment.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    resolved_model = model_name or get_default_gemini_model()
    key = api_key or get_gemini_api_key()
    if not key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")

    primary = ChatGoogleGenerativeAI(
        model=resolved_model,
        temperature=temperature,
        api_key=key,
        max_retries=1,
        timeout=30.0,
    )

    # Candidate resilient fallbacks if primary model is throttled or quota-limited
    fallback_models = ["gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-3.5-flash"]
    fallbacks = [
        ChatGoogleGenerativeAI(
            model=m,
            temperature=temperature,
            api_key=key,
            max_retries=1,
            timeout=30.0,
        )
        for m in fallback_models
        if m != resolved_model
    ]

    if fallbacks:
        return primary.with_fallbacks(fallbacks)
    return primary


class GeminiClient:
    """
    Legacy Gemini client wrapper maintained for backwards compatibility
    with other team agents and services.
    """
    def __init__(self):
        self.api_key = get_gemini_api_key()
        self.model_name = get_default_gemini_model()
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to configure google.generativeai: {e}")
        else:
            logger.warning("GEMINI_API_KEY is not configured.")

    def get_chat_model(self, model_name: Optional[str] = None, temperature: float = 0.2):
        """Returns a LangChain ChatGoogleGenerativeAI instance using the configured key."""
        return get_gemini_chat_model(
            model_name=model_name or self.model_name,
            temperature=temperature,
            api_key=self.api_key,
        )

    async def generate_content(self, prompt: str, system_instruction: str = None) -> str:
        """Asynchronous content generation compatible with earlier agents with multi-model fallback."""
        if not self.api_key or os.getenv("CHAI_MOCK_MODE", "").lower() in ("true", "1", "yes"):
            return "Mock response: API key not configured."

        if is_quota_exhausted():
            return "Mock response: API quota exceeded."

        import google.generativeai as genai
        models_to_try = [self.model_name] + [
            m for m in ["gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-3.5-flash"]
            if m != self.model_name
        ]

        last_err = None
        for m in models_to_try:
            try:
                if system_instruction:
                    try:
                        model = genai.GenerativeModel(
                            model_name=m,
                            system_instruction=system_instruction,
                        )
                        content_prompt = prompt
                    except TypeError:
                        model = genai.GenerativeModel(model_name=m)
                        content_prompt = f"System Instruction:\n{system_instruction}\n\nUser Request:\n{prompt}"
                else:
                    model = genai.GenerativeModel(model_name=m)
                    content_prompt = prompt

                try:
                    response = await model.generate_content_async(content_prompt)
                    return response.text
                except Exception as inner_e:
                    if "event loop is closed" in str(inner_e).lower():
                        import asyncio
                        response = await asyncio.to_thread(model.generate_content, content_prompt)
                        return response.text
                    raise inner_e
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                    mark_quota_exhausted(60.0)
                    logger.warning(f"GeminiClient: Model '{m}' hit quota limit ({e}). Fast fallback to mock.")
                    return "Mock response: API quota exceeded."
                if "404" in err_str or "event loop is closed" in err_str:
                    logger.warning(f"GeminiClient: Model '{m}' failed ({e}). Falling back to next candidate...")
                    continue
                logger.error(f"Error calling Gemini API: {e}")
                raise

        logger.warning(f"GeminiClient: All candidate models failed ({last_err}). Falling back to mock response.")
        last_str = str(last_err).lower()
        if "429" in last_str or "quota" in last_str or "resource_exhausted" in last_str:
            mark_quota_exhausted(60.0)
            return "Mock response: API quota exceeded."
        raise last_err


llm_client = GeminiClient()
