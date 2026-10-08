import os
from typing import Optional
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

from backend.config import get_settings
from backend.shared.logger import get_logger

logger = get_logger(__name__)


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

                response = await model.generate_content_async(content_prompt)
                return response.text
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str or "404" in err_str:
                    logger.warning(f"GeminiClient: Model '{m}' failed ({e}). Falling back to next candidate...")
                    continue
                logger.error(f"Error calling Gemini API: {e}")
                raise

        logger.error(f"Error calling Gemini API on all candidate models: {last_err}")
        raise last_err


llm_client = GeminiClient()
