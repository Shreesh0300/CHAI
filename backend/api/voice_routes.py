"""
Voice API routes — STT and TTS endpoints.

These routes are the HTTP interface for the voice subsystem.
They do NOT interact with CHAI agents directly.

Phase 1: Placeholder responses only.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.voice.voice_models import STTResponse, TTSRequest, TTSResponse
from backend.voice.stt_service import STTService
from backend.voice.tts_service import TTSService

router = APIRouter()

stt_service = STTService()
tts_service = TTSService()


@router.post("/voice/stt", response_model=STTResponse)
async def speech_to_text(audio: UploadFile = File(...)):
    """
    Receive an audio file and return its transcription.

    Future flow:
      Audio → STT service → Cloud STT provider → Text
    """
    try:
        audio_data = await audio.read()
        result = await stt_service.transcribe(audio_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice/tts", response_model=TTSResponse)
async def text_to_speech(request: TTSRequest):
    """
    Receive text and return synthesized audio metadata.

    Future flow:
      Text → TTS service → Cloud TTS provider → Audio

    NOTE: In the implementation phase this endpoint will return
    audio bytes via a StreamingResponse instead of JSON.
    """
    try:
        audio_bytes = await tts_service.synthesize(request.text, language=request.language)
        return TTSResponse(
            success=True,
            audio_content_type="audio/wav",
            audio_size_bytes=len(audio_bytes),
            error=None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
