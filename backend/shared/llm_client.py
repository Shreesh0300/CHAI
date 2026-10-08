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
    defaulting to the responsive model: 'gemini-flash-lite-latest'.
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


def get_gemini_chat_model(
    model_name: Optional[str] = None,
    temperature: float = 0.2,
    api_key: Optional[str] = None,
):
    """
    Initializes and returns a LangChain ChatGoogleGenerativeAI instance.
    Defaults to 'gemini-3.8-flash' or GEMINI_MODEL environment variable.
    Raises ValueError if no API key is provided or present in environment.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    resolved_model = model_name or get_default_gemini_model()
    key = api_key or get_gemini_api_key()
    if not key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")

    return ChatGoogleGenerativeAI(
        model=resolved_model,
        temperature=temperature,
        api_key=key,
        max_retries=0,
        request_timeout=10.0,
    )


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
        key = self.api_key or get_gemini_api_key()
        return get_gemini_chat_model(
            model_name=model_name or self.model_name,
            temperature=temperature,
            api_key=key,
        )

    async def generate_content(self, prompt: str, system_instruction: str = None) -> str:
        """Asynchronous content generation compatible with earlier agents."""
        if not self.api_key:
            self.api_key = get_gemini_api_key()
            if self.api_key:
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=self.api_key)
                except Exception as e:
                    logger.warning(f"Failed to configure google.generativeai: {e}")

        if not self.api_key:
            return "Mock response: API key not configured."

        import google.generativeai as genai

        # Priority candidates for generation to maximize quota resilience
        candidates = [self.model_name, "gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        seen = set()
        models_to_try = [c for c in candidates if c and not (c in seen or seen.add(c))]

        last_error = None
        for m_name in models_to_try:
            try:
                try:
                    model = genai.GenerativeModel(
                        model_name=m_name,
                        system_instruction=system_instruction,
                    )
                except (TypeError, ValueError):
                    model = genai.GenerativeModel(model_name=m_name)
                    if system_instruction:
                        prompt = f"{system_instruction}\n\n{prompt}"

                response = await model.generate_content_async(prompt)
                if response and response.text:
                    return response.text
            except Exception as e:
                last_error = e
                logger.warning(f"Gemini API model {m_name} failed: {e}")
                continue

        logger.error(f"All Gemini models failed: {last_error}")
        return "Mock response: API error or offline fallback."


llm_client = GeminiClient()
