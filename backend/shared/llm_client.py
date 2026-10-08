import asyncio
import copy
import os
import re
from typing import Optional, Any
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv(override=True)

from backend.config import get_settings
from backend.shared.logger import get_logger

logger = get_logger(__name__)


def get_default_gemini_model() -> str:
    """
    Returns the configured Gemini model name from GEMINI_MODEL env var,
    defaulting to the current stable model: 'gemini-3.1-flash-lite'.
    """
    load_dotenv(override=True)
    return os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip() or "gemini-3.1-flash-lite"


def get_gemini_api_key() -> str:
    """
    Safely retrieves the Gemini API key from environment variables or settings.
    Never logs or exposes the key value.
    """
    load_dotenv(override=True)
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
    fallback_models = ["gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-3.5-flash", "gemini-flash-lite-latest"]
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
    Gemini client wrapper with multi-model fallback and backwards compatibility.
    """
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = (api_key or get_gemini_api_key()).strip()
        self.model_name = (model_name or get_default_gemini_model()).strip()
        self._genai_configured = False
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._genai_configured = True
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

    async def generate_content(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        response_schema: Optional[Any] = None,
        response_mime_type: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Asynchronous content generation compatible with earlier agents with multi-model fallback."""
        # Dynamically refresh API key if updated
        fresh_key = get_gemini_api_key()
        if fresh_key and fresh_key != self.api_key:
            self.api_key = fresh_key
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._genai_configured = True
            except Exception:
                pass

        if not self.api_key or os.getenv("CHAI_MOCK_MODE", "").lower() in ("true", "1", "yes"):
            return "Mock response: API key not configured."

        effective_model = get_default_gemini_model()
        models_to_try = [effective_model] + [
            m for m in ["gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-3.5-flash", "gemini-flash-lite-latest"]
            if m != effective_model
        ]

        import google.generativeai as genai
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

                generation_config = {}
                if temperature is not None:
                    generation_config["temperature"] = temperature
                if response_mime_type:
                    generation_config["response_mime_type"] = response_mime_type

                effective_timeout = timeout or DEFAULT_TIMEOUT_SECONDS
                coro = model.generate_content_async(
                    content_prompt,
                    generation_config=generation_config if generation_config else None,
                )
                response = await asyncio.wait_for(coro, timeout=effective_timeout)
                return response.text or ""
            except Exception as e:
                last_err = e
                err_cat, err_msg = classify_gemini_error(e)
                if err_cat in ("[QUOTA_ERROR]", "[TIMEOUT_ERROR]") or "429" in str(e) or "quota" in str(e).lower() or "404" in str(e):
                    logger.warning(f"GeminiClient: Model '{m}' failed ({err_cat}). Falling back to next candidate...")
                    continue
                logger.error(f"Error calling Gemini API: {err_cat} {err_msg}")
                raise RuntimeError(f"{err_cat} {err_msg}") from None

        err_cat, err_msg = classify_gemini_error(last_err) if last_err else ("[API_ERROR]", "Unknown error")
        logger.error(f"Error calling Gemini API on all candidate models: {err_cat} {err_msg}")
        raise RuntimeError(f"{err_cat} {err_msg}") from None

    generate = generate_content


llm_client = GeminiClient()
