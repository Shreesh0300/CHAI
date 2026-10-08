"""
Voice API routes — STT and TTS endpoints.

These routes are the HTTP interface for the voice subsystem.
They do NOT interact with CHAI agents directly.

Phase 1: Placeholder responses only.
"""

from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.voice.voice_models import STTResponse, TTSRequest, TTSResponse
from backend.voice.stt_service import STTService
from backend.voice.tts_service import TTSService

router = APIRouter()

stt_service = STTService()
tts_service = TTSService()


@router.post("/voice/stt", response_model=STTResponse)
async def speech_to_text(audio: UploadFile = File(...)):
    """Receive an audio file and return its transcription."""
    try:
        audio_data = await audio.read()
        result = await stt_service.transcribe(audio_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stt")
async def speech_to_text_alias(
    file: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
):
    """
    Standard STT endpoint accepting multipart/form-data with file or audio parameter.
    Returns:
    {
        "transcript": "...",
        "detected_language": "en",
        "confidence": 0.98,
        "wake_word_detected": false
    }
    """
    target = file or audio
    if not target:
        raise HTTPException(status_code=400, detail="No audio file provided in 'file' or 'audio' parameter.")
    try:
        audio_data = await target.read()
        result = await stt_service.transcribe(audio_data)
        return {
            "transcript": result.text,
            "detected_language": result.language,
            "confidence": 0.98 if result.success else 0.0,
            "wake_word_detected": False,
            "success": result.success,
            "error": result.error,
        }
    except Exception as e:
        return {
            "transcript": "",
            "detected_language": "en",
            "confidence": 0.0,
            "wake_word_detected": False,
            "success": False,
            "error": str(e),
        }


from fastapi.responses import Response

@router.post("/voice/tts")
async def text_to_speech(
    request: TTSRequest,
    stream: bool = False,
):
    """
    Receive text and return synthesized audio metadata or raw audio stream.
    If query parameter stream=true, returns raw audio stream for playback.
    Otherwise returns TTSResponse JSON metadata.
    """
    try:
        audio_bytes = await tts_service.synthesize(request.text, language=request.language)
        content_type = "audio/wav"
        if audio_bytes.startswith(b"ID3") or (len(audio_bytes) >= 2 and audio_bytes[:2] == b"\xff\xfb"):
            content_type = "audio/mpeg"

        if stream:
            return Response(content=audio_bytes, media_type=content_type)

        return TTSResponse(
            success=True,
            audio_content_type=content_type,
            audio_size_bytes=len(audio_bytes),
            error=None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice/tts/stream")
@router.post("/tts/stream")
@router.post("/tts")
async def text_to_speech_stream(request: TTSRequest):
    """Receive text and return raw audio stream directly for browser audio playback."""
    try:
        audio_bytes = await tts_service.synthesize(request.text, language=request.language)
        content_type = "audio/wav"
        if audio_bytes.startswith(b"ID3") or (len(audio_bytes) >= 2 and audio_bytes[:2] == b"\xff\xfb"):
            content_type = "audio/mpeg"
        return Response(content=audio_bytes, media_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
