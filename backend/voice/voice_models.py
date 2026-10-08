"""
Pydantic models for voice request/response contracts.

These models define the data shapes exchanged between
the frontend, the voice API routes, and the STT/TTS services.
"""

from pydantic import BaseModel
from typing import Optional


# ── STT (Speech-to-Text) ──────────────────────────────────────────────

class STTResponse(BaseModel):
    """Structured result returned by the STT service."""
    text: str = ""
    language: str = "en"
    success: bool = False
    error: Optional[str] = None


# ── TTS (Text-to-Speech) ──────────────────────────────────────────────

class TTSRequest(BaseModel):
    """Payload sent to the TTS service."""
    text: str
    language: str = "en"
    voice: str = "default"


class TTSResponse(BaseModel):
    """Structured result returned by the TTS service."""
    success: bool = False
    audio_content_type: str = ""
    audio_size_bytes: int = 0
    error: Optional[str] = None
