"""
Voice configuration — reads cloud STT/TTS provider settings from environment.

IMPORTANT:
- Never hardcode API keys.
- Never expose backend keys to the frontend.
- Provider-specific SDKs will be added in the implementation phase.
"""

from pydantic_settings import BaseSettings
from typing import List


class VoiceSettings(BaseSettings):
    """Configuration for the voice subsystem (STT + TTS)."""

    # --- STT provider ---
    stt_provider: str = ""
    stt_api_key: str = ""
    stt_api_url: str = ""

    # --- Gemini API Key fallback ---
    gemini_api_key: str = ""

    # --- TTS provider ---
    tts_provider: str = ""
    tts_api_key: str = ""
    tts_api_url: str = ""
    gemini_tts_model: str = ""

    # --- Shared ---
    supported_languages: List[str] = ["en"]
    default_voice: str = "default"

    class Config:
        env_file = ".env"
        extra = "ignore"


def get_voice_settings() -> VoiceSettings:
    """Return voice settings loaded from environment variables."""
    return VoiceSettings()
