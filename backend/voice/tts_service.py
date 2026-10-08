"""
Text-to-Speech (TTS) service implementation using Google Gemini GenAI SDK.
"""

import os
import time
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
FALLBACK_TTS_MODELS = [
    "gemini-3.8-flash-lite-tts",
]

LANGUAGE_INSTRUCTIONS = {
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
        self._gemini_quota_exhausted: bool = False

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
        """
        Construct prompt for Gemini TTS model.
        For English, return verbatim text so the model does not voice instructions.
        For non-English languages, guide pronunciation using native language instruction.
        """
        canon_lang = canonicalize_language(language) or DEFAULT_LANGUAGE
        if canon_lang == "en":
            return text.strip()
        instruction = LANGUAGE_INSTRUCTIONS.get(
            canon_lang,
            f"Read the following text aloud in {canon_lang}:",
        )
        return f"{instruction}\n\n{text.strip()}"

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

        provider = (
            os.getenv("TTS_PROVIDER")
            or getattr(self.settings, "tts_provider", "")
            or "auto"
        ).strip().lower()

        # If user explicitly configured Google TTS, synthesize directly
        if provider == "google":
            fallback_wav = self._synthesize_fallback(text_str, canon_lang)
            if fallback_wav:
                return fallback_wav

        # Fast-path: if this service instance already observed quota exhaustion, route to fallback
        if self._gemini_quota_exhausted and provider != "gemini":
            fallback_wav = self._synthesize_fallback(text_str, canon_lang)
            if fallback_wav:
                return fallback_wav

        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError("TTS API key is not configured (set GEMINI_API_KEY or TTS_API_KEY).")

        from google import genai

        client = genai.Client(api_key=api_key)
        prompt = self._build_prompt(text_str, canon_lang)

        # Candidates to try in sequence
        candidate_models = [self.model_name] + [
            m for m in FALLBACK_TTS_MODELS if m != self.model_name
        ]

        response = None
        last_error = None

        for model_name in candidate_models:
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response:
                    break
            except Exception as err:
                last_error = err
                err_str = str(err)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    logger.info("Gemini TTS daily quota reached. Seamlessly routing to multilingual voice engine.")
                    self._gemini_quota_exhausted = True
                    fallback_wav = self._synthesize_fallback(text_str, canon_lang)
                    if fallback_wav:
                        return fallback_wav
                    break
                logger.debug(f"TTS model '{model_name}' encountered error ({err_str[:60]}). Trying next.")
                continue

        if response is None:
            fallback_wav = self._synthesize_fallback(text_str, canon_lang)
            if fallback_wav:
                return fallback_wav
            raise RuntimeError(f"All Gemini TTS models exhausted. Last error: {last_error}")

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
            fallback_wav = self._synthesize_fallback(text_str, canon_lang)
            if fallback_wav:
                return fallback_wav
            raise RuntimeError("Gemini TTS response did not contain audio data.")

        return audio_data

    def _synthesize_fallback(self, text: str, language: str = "en") -> Optional[bytes]:
        """Synthesize audio using Google TTS or Windows SAPI when cloud GenAI quota is exhausted."""
        canon_lang = canonicalize_language(language) or DEFAULT_LANGUAGE

        # 1. Try Google Multilingual TTS (authentic native speech for kn, hi, sa, en)
        try:
            import urllib.request
            import urllib.parse
            encoded = urllib.parse.quote(text)
            lang_code = "hi" if canon_lang == "sa" else canon_lang
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded}&tl={lang_code}&client=tw-ob"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
            if len(data) > 100:
                logger.info(f"Successfully synthesized audio using Google TTS fallback ({canon_lang} via {lang_code}).")
                return data
        except Exception as e:
            logger.debug(f"Google TTS fallback unavailable: {e}")

        # 2. Try Local Windows SAPI (offline fallback for English)
        if canon_lang == "en":
            try:
                import win32com.client
                import tempfile
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                stream = win32com.client.Dispatch("SAPI.SpFileStream")
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    temp_path = tf.name
                try:
                    stream.Open(temp_path, 3)  # 3 = SSFMCreateForWrite
                    speaker.AudioOutputStream = stream
                    speaker.Speak(text)
                    stream.Close()
                    with open(temp_path, "rb") as f:
                        data = f.read()
                    if len(data) > 1000:
                        logger.info("Successfully synthesized audio using Windows SAPI engine fallback.")
                        return data
                finally:
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Local Windows SAPI fallback unavailable: {e}")

        return None
