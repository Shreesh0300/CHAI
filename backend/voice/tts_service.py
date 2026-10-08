"""
Text-to-Speech (TTS) service implementation using Google Gemini GenAI SDK.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Union, Any

from backend.voice.voice_config import get_voice_settings
from backend.core.language import canonicalize_language, DEFAULT_LANGUAGE
from backend.shared.logger import get_logger

logger = get_logger(__name__)

# Suppress AFC noisy warnings from google_genai.models
logging.getLogger("google_genai.models").setLevel(logging.ERROR)
logging.getLogger("google_genai").setLevel(logging.ERROR)

DEFAULT_TTS_MODEL = "gemini-3.8-flash-tts"
FALLBACK_TTS_MODEL = "gemini-3.8-flash-lite-tts"

LANGUAGE_INSTRUCTIONS = {
    "en": "Read the following text aloud in clear English with natural pronunciation:",
    "hi": "Read the following text aloud in Hindi (हिंदी) with natural pronunciation:",
    "kn": "Read the following text aloud in Kannada (ಕನ್ನಡ) with natural pronunciation:",
    "sa": "Read the following text aloud in Sanskrit (संस्कृतम्) with clear Vedic/classical pronunciation:",
}


class TTSService:
    """Abstraction over cloud Text-to-Speech using Google Gemini API."""

    def __init__(self):
        self.settings = get_voice_settings()
        self.model_name = (
            os.getenv("GEMINI_TTS_MODEL")
            or getattr(self.settings, "gemini_tts_model", "")
            or DEFAULT_TTS_MODEL
        ).strip() or DEFAULT_TTS_MODEL

    def _resolve_api_key(self) -> str:
        """Safely resolve API key from voice settings, environment, or backend config."""
        api_key = (
            self.settings.tts_api_key
            or getattr(self.settings, "gemini_api_key", "")
            or os.getenv("TTS_API_KEY", "")
            or os.getenv("GEMINI_API_KEY", "")
        ).strip()
        if not api_key:
            try:
                from backend.config import get_settings
                api_key = (get_settings().gemini_api_key or "").strip()
            except Exception:
                pass
        if not api_key:
            try:
                from dotenv import load_dotenv
                repo_env = Path(__file__).resolve().parents[2] / ".env"
                if repo_env.exists():
                    load_dotenv(repo_env)
                else:
                    load_dotenv()
                api_key = (os.getenv("TTS_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
            except Exception:
                pass
        return api_key

    def _build_prompt(self, text: str, language: str) -> str:
        """Construct language-aware prompt for Gemini TTS model."""
        canon_lang = canonicalize_language(language) or DEFAULT_LANGUAGE
        instruction = LANGUAGE_INSTRUCTIONS.get(
            canon_lang,
            f"Read the following text aloud in {canon_lang} with natural pronunciation:",
        )
        return f"{instruction}\n\n{text}"

    async def synthesize(
        self,
        text: Union[str, Any],
        language: str = "en",
    ) -> bytes:
        """
        Synthesize text into speech audio bytes.

        Parameters
        ----------
        text : Union[str, TTSRequest]
            The input text to synthesize into spoken audio.
        language : str
            Target language code ("en", "hi", "kn", "sa"). Defaults to "en".

        Returns
        -------
        bytes
            Raw audio bytes (typically audio/wav).
        """
        # Support passing a TTSRequest object
        if hasattr(text, "text"):
            language = getattr(text, "language", language) or language
            text = getattr(text, "text", "")

        if not text or not str(text).strip():
            raise ValueError("Text to synthesize cannot be empty.")

        text_str = str(text).strip()
        canon_lang = canonicalize_language(language) or DEFAULT_LANGUAGE

        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError("TTS API key is not configured (set GEMINI_API_KEY or TTS_API_KEY).")

        from google import genai

        client = genai.Client(api_key=api_key)
        prompt = self._build_prompt(text_str, canon_lang)

        # Attempt synthesis with configured model; fallback if rate limited
        model_name = self.model_name
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
            )
        except Exception as err:
            err_str = str(err)
            if (
                "429" in err_str
                or "RESOURCE_EXHAUSTED" in err_str
                or "404" in err_str
                or "NOT_FOUND" in err_str
            ) and model_name != FALLBACK_TTS_MODEL:
                logger.warning(
                    f"TTS model '{model_name}' encountered quota/error ({err_str[:80]}). "
                    f"Falling back to '{FALLBACK_TTS_MODEL}'."
                )
                model_name = FALLBACK_TTS_MODEL
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
            else:
                logger.error(f"Gemini TTS generation error with model '{model_name}': {err}")
                raise RuntimeError(f"Gemini TTS generation failed: {err}")

        # Extract audio bytes from response parts
        audio_data: Optional[bytes] = None
        if response and response.candidates:
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        # Extract inline_data (standard Gemini media part)
                        inline_data = getattr(part, "inline_data", None)
                        if inline_data is not None and getattr(inline_data, "data", None):
                            audio_data = inline_data.data
                            break
                        # Check binary attributes
                        for attr in ("audio", "data", "bytes"):
                            val = getattr(part, attr, None)
                            if isinstance(val, (bytes, bytearray)) and len(val) > 0:
                                audio_data = bytes(val)
                                break
                    if audio_data:
                        break

        if not audio_data:
            raise RuntimeError("Gemini TTS response did not contain audio data.")

        return audio_data
