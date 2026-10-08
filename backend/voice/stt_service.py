"""
Cloud Speech-to-Text service abstraction.

Flow (future implementation):
  1. Receive audio bytes from the voice API route.
  2. Send audio to the selected cloud STT provider.
  3. Receive transcription from the provider.
  4. Return a structured STTResponse.

Phase 1: Class/function skeleton with TODO placeholders only.
"""

import io
import os
import re
import wave
from typing import Tuple, Optional

import logging
from backend.voice.voice_models import STTResponse
from backend.voice.voice_config import get_voice_settings
from backend.core.language import canonicalize_language, detect_language, DEFAULT_LANGUAGE
from backend.shared.logger import get_logger

logger = get_logger(__name__)
# Suppress noisy AFC warning from google_genai.models
logging.getLogger("google_genai.models").setLevel(logging.ERROR)
logging.getLogger("google_genai").setLevel(logging.ERROR)


STT_PROMPT = (
    "You are a dedicated multilingual Speech-to-Text (STT) transcription and language identification engine.\n"
    "Carefully listen to the audio and transcribe the exact words spoken in their native, original language and script:\n"
    "- If English speech: transcribe in English (Latin script).\n"
    "- If Hindi speech: transcribe in Hindi (Devanagari script, e.g., 'नमस्ते').\n"
    "- If Kannada speech (ಕನ್ನಡ): transcribe in authentic Kannada script (ಕನ್ನಡ ಲಿಪಿ, e.g., 'ನಮಸ್ಕಾರ, ಹೇಗಿದ್ದೀರಾ?').\n"
    "- If Sanskrit speech: transcribe in Sanskrit (Devanagari script, e.g., 'नमस्कारम्').\n\n"
    "STRICT RULES:\n"
    "1. DO NOT TRANSLATE. If the speaker speaks Kannada, output Kannada text. Do NOT translate Kannada to English or Hindi.\n"
    "2. DO NOT TRANSLITERATE. Kannada speech MUST be in Kannada Unicode script (ಕನ್ನಡ), NOT Devanagari (देवनागरी) and NOT Latin/English alphabet.\n"
    "3. DO NOT SUMMARIZE or add commentary.\n"
    "4. Output format MUST be:\n"
    "LANGUAGE: <en|hi|kn|sa>\n"
    "TEXT: <transcription in native script>\n\n"
    "If the audio contains only silence, noise, or no intelligible speech, output:\n"
    "LANGUAGE: en\n"
    "TEXT: "
)


def parse_stt_result(raw_text: str, metadata_lang: Optional[str] = None) -> Tuple[str, str]:
    """
    Parses raw Gemini transcription output into (clean_text, canonical_language).

    Expected format:
      LANGUAGE: <en|hi|kn|sa>
      TEXT: <transcription>

    Also gracefully handles:
      - Raw text without LANGUAGE/TEXT tags
      - Language names like 'Kannada', 'Hindi', 'Sanskrit', 'English'
      - Script-level detection if metadata or tags are missing or inconsistent
      - Kannada script is NEVER confused with Devanagari/Hindi
    """
    if not raw_text or not raw_text.strip():
        return "", DEFAULT_LANGUAGE

    cleaned = raw_text.strip()
    # Strip markdown code blocks if wrapped by model
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    extracted_lang: Optional[str] = None
    extracted_text: Optional[str] = None

    # 1. Check for structured LANGUAGE: and TEXT: tags
    lang_match = re.search(r"LANGUAGE:\s*([a-zA-Z\-]+)", cleaned, re.IGNORECASE)
    if lang_match:
        extracted_lang = lang_match.group(1).strip()

    text_match = re.search(r"TEXT:\s*(.*)", cleaned, re.IGNORECASE | re.DOTALL)
    if text_match:
        extracted_text = text_match.group(1).strip()
    elif lang_match:
        # If LANGUAGE: was present but TEXT: was not explicitly tagged
        extracted_text = re.sub(r"LANGUAGE:\s*[a-zA-Z\-]+\s*", "", cleaned, flags=re.IGNORECASE).strip()
    else:
        extracted_text = cleaned

    if extracted_text:
        # Remove surrounding quotes if model added them
        if (extracted_text.startswith('"') and extracted_text.endswith('"')) or (
            extracted_text.startswith("'") and extracted_text.endswith("'")
        ):
            extracted_text = extracted_text[1:-1].strip()

    # 2. Canonicalize extracted language tag
    canonical_lang = canonicalize_language(extracted_lang) if extracted_lang else None

    # 3. Analyze script of extracted text
    final_text = extracted_text or ""
    if final_text.strip() in ("00:00", "00:01", "00:00:00", "[silence]", "(silence)", "[music]", "(music)", "[applause]"):
        final_text = ""
    kn_chars = sum(1 for c in final_text if "\u0c80" <= c <= "\u0cff")
    devanagari_chars = sum(1 for c in final_text if "\u0900" <= c <= "\u097f")
    latin_chars = sum(1 for c in final_text if "a" <= c.lower() <= "z")

    # Script-level prioritization:
    # If text contains Kannada characters, it MUST be Kannada ('kn')
    if kn_chars > 0:
        resolved_lang = "kn"
    elif canonical_lang in ("kn", "hi", "sa", "en"):
        resolved_lang = canonical_lang
    elif devanagari_chars > 0:
        # Check if model or metadata identified Sanskrit or if Sanskrit vocabulary is detected
        if metadata_lang and canonicalize_language(metadata_lang) == "sa":
            resolved_lang = "sa"
        else:
            det = detect_language(final_text)
            resolved_lang = det.language if det.language in ("hi", "sa") else "hi"
    elif latin_chars > 0:
        resolved_lang = "en"
    elif metadata_lang:
        meta_canon = canonicalize_language(metadata_lang)
        resolved_lang = meta_canon if meta_canon else DEFAULT_LANGUAGE
    else:
        resolved_lang = DEFAULT_LANGUAGE

    return final_text, resolved_lang




def _format_audio_payload(audio_data: bytes, sample_rate: int = 16000, channels: int = 1) -> Tuple[bytes, str]:
    """
    Inspect audio bytes and return (formatted_bytes, mime_type).
    If raw PCM without container header, wrap into standard WAV container.
    """
    if not audio_data:
        return b"", "audio/wav"

    # RIFF/WAV
    if audio_data.startswith(b"RIFF"):
        return audio_data, "audio/wav"
    # WebM container
    if audio_data.startswith(b"\x1aE\xdf\xa3"):
        return audio_data, "audio/webm"
    # MP3 ID3 header or frame sync
    if audio_data.startswith(b"ID3") or (len(audio_data) >= 2 and audio_data[:2] == b"\xff\xfb"):
        return audio_data, "audio/mp3"
    # Ogg container
    if audio_data.startswith(b"OggS"):
        return audio_data, "audio/ogg"

    # Fallback: Treat as raw 16-bit PCM mono and wrap in standard WAV container
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data)
    return buf.getvalue(), "audio/wav"


class STTService:
    """Abstraction over a cloud Speech-to-Text provider."""

    def __init__(self):
        self.settings = get_voice_settings()

    async def transcribe(self, audio_data: bytes) -> STTResponse:
        """
        Transcribe audio bytes to text.

        Parameters
        ----------
        audio_data : bytes
            Raw audio bytes received from the client or microphone.

        Returns
        -------
        STTResponse
            Structured transcription result.
        """
        if not audio_data or len(audio_data) == 0:
            return STTResponse(
                text="",
                language="en",
                success=False,
                error="No audio data provided",
            )

        provider = (self.settings.stt_provider or "gemini").strip().lower()

        # Resolve API credentials safely without hardcoding or logging secrets
        api_key = (
            self.settings.stt_api_key
            or getattr(self.settings, "gemini_api_key", "")
            or os.getenv("STT_API_KEY", "")
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
                load_dotenv()
                api_key = (os.getenv("STT_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
            except Exception:
                pass

        if not api_key:
            return STTResponse(
                text="",
                language="en",
                success=False,
                error="STT API key is not configured (set GEMINI_API_KEY or STT_API_KEY)",
            )

        if provider in ("gemini", "google"):
            return await self._transcribe_gemini(audio_data, api_key)

        return STTResponse(
            text="",
            language="en",
            success=False,
            error=f"Unsupported STT provider: '{provider}'",
        )

    async def _transcribe_gemini(self, audio_data: bytes, api_key: str) -> STTResponse:
        """Transcribe audio using modern google.genai SDK and gemini-3.5-transcribe."""
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)

            formatted_bytes, mime_type = _format_audio_payload(audio_data)
            configured_model = (
                os.getenv("GEMINI_STT_MODEL")
                or "gemini-3.5-transcribe"
            ).strip()

            prompt = STT_PROMPT
            audio_part = types.Part.from_bytes(data=formatted_bytes, mime_type=mime_type)

            model_name = configured_model
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=[prompt, audio_part],
                )
            except Exception as model_err:
                err_str = str(model_err)
                if (
                    "429" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "404" in err_str
                    or "NOT_FOUND" in err_str
                ) and model_name != "gemini-3.8-flash":
                    logger.warning(
                        f"Model '{model_name}' hit rate limit or error ({err_str[:80]}). "
                        f"Falling back to 'gemini-3.8-flash'."
                    )
                    model_name = "gemini-3.8-flash"
                    try:
                        response = await client.aio.models.generate_content(
                            model=model_name,
                            contents=[prompt, audio_part],
                        )
                    except Exception:
                        model_name = "gemini-flash-latest"
                        response = await client.aio.models.generate_content(
                            model=model_name,
                            contents=[prompt, audio_part],
                        )
                else:
                    raise model_err

            transcribed_texts = []
            detected_language_meta = None

            if response and response.candidates:
                for candidate in response.candidates:
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            # Extract dedicated audio_transcription part (e.g. from gemini-3.5-transcribe)
                            audio_transcription = getattr(part, "audio_transcription", None)
                            if audio_transcription is not None:
                                at_text = getattr(audio_transcription, "text", "")
                                if at_text:
                                    transcribed_texts.append(at_text.strip())
                                lang = getattr(audio_transcription, "language_code", None)
                                if lang:
                                    detected_language_meta = lang
                            # Extract standard text part
                            elif getattr(part, "text", None):
                                transcribed_texts.append(part.text.strip())

            # Fallback if no parts extracted text
            if not transcribed_texts and response:
                try:
                    if response.text:
                        transcribed_texts.append(response.text.strip())
                except Exception:
                    pass

            raw_text = " ".join([t for t in transcribed_texts if t]).strip()

            # Parse language header and verbatim text
            text, final_language = parse_stt_result(raw_text, metadata_lang=detected_language_meta)

            return STTResponse(
                text=text,
                language=final_language,
                success=True,
                error=None,
            )
        except Exception as e:
            logger.error(f"Gemini STT transcription error: {e}")
            return STTResponse(
                text="",
                language="en",
                success=False,
                error=str(e),
            )
