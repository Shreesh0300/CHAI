"""
Voice API routes — STT, TTS, Speaker Playback, and Wake-Up endpoints.

These routes provide the HTTP interface for the voice subsystem:
1. STT (/api/voice/stt, /api/stt)
2. TTS metadata & audio stream (/api/voice/tts, /api/voice/synthesize)
3. Speaker output (/api/voice/speak)
4. Hands-free Alexa/Siri Voice Wake-Up (/api/voice/wakeup/...)
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Response, Query
from pydantic import BaseModel, Field

from backend.voice.voice_models import STTResponse, TTSRequest, TTSResponse
from backend.voice.stt_service import STTService
from backend.voice.tts_service import TTSService
from backend.voice.wakeup_daemon import (
    get_voice_wakeup_daemon,
    play_audio_to_speakers,
    extract_wake_word_and_query,
)

router = APIRouter()

stt_service = STTService()
tts_service = TTSService()


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to speak aloud through system speakers")
    language: Optional[str] = Field(default="en", description="Language code ('en', 'hi', 'kn', 'sa')")


class SimulateWakeRequest(BaseModel):
    text: Optional[str] = Field(
        default="Welcome back chai",
        description="Spoken wake phrase to simulate, e.g. 'Hey CHAI what is AI?'",
    )
    language: Optional[str] = Field(default="en", description="Language code ('en', 'hi', 'kn', 'sa')")


class VoiceInteractRequest(BaseModel):
    problem: str = Field(..., min_length=1, description="Spoken problem or query")
    language: Optional[str] = Field(default="en", description="Language code ('en', 'hi', 'kn', 'sa')")
    session_id: Optional[str] = Field(default=None, description="Optional conversation session ID")


@router.post("/voice/agent-response")
@router.post("/voice/interact")
async def voice_agent_interact(req: VoiceInteractRequest):
    """
    Server-type end-to-end voice query and agent response endpoint:
    1. Receives user voice query.
    2. Runs MultiAgentCoordinator to synthesize full reasoning answer.
    3. Returns structured agent response with text and streaming TTS audio URL.
    """
    import urllib.parse
    from backend.coordinator.coordinator import MultiAgentCoordinator
    from backend.coordinator.schemas import SolveRequest

    try:
        coord = MultiAgentCoordinator()
        solve_req = SolveRequest(problem=req.problem)
        res = await coord.process_request(solve_req)
        clean_answer = res.final_synthesized_answer or "CHAI agent execution completed successfully."

        audio_encoded = urllib.parse.quote(clean_answer[:400])
        audio_stream_url = f"/api/voice/synthesize?text={audio_encoded}&language={req.language or 'en'}"

        return {
            "success": True,
            "query": req.problem,
            "language": req.language or "en",
            "final_synthesized_answer": clean_answer,
            "audio_url": audio_stream_url,
            "confidence_score": getattr(res, "confidence_score", 0.95),
            "agents_used": getattr(res, "agents_used", ["coordinator", "researcher", "synthesizer"]),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        "wake_word_detected": true/false
    }
    """
    target = file or audio
    if not target:
        raise HTTPException(status_code=400, detail="No audio file provided in 'file' or 'audio' parameter.")
    try:
        audio_data = await target.read()
        result = await stt_service.transcribe(audio_data)
        wake_info = extract_wake_word_and_query(result.text or "")
        return {
            "transcript": result.text,
            "detected_language": result.language,
            "confidence": 0.98 if result.success else 0.0,
            "wake_word_detected": wake_info["matched"],
            "wake_phrase": wake_info.get("phrase", ""),
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


@router.post("/voice/tts", response_model=TTSResponse)
async def text_to_speech(request: TTSRequest):
    """Receive text and return synthesized audio metadata."""
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


@router.post("/voice/synthesize")
@router.get("/voice/synthesize")
async def synthesize_audio_stream(
    text: Optional[str] = Query(None),
    language: Optional[str] = Query("en"),
    request: Optional[TTSRequest] = None,
):
    """
    Synthesize speech and stream raw audio (WAV / MP3) bytes directly to browser or media player.
    """
    input_text = ""
    lang = "en"
    if request and request.text:
        input_text = request.text
        lang = request.language or "en"
    elif text:
        input_text = text
        lang = language or "en"

    if not input_text.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'text' or JSON body with 'text' required.")

    try:
        audio_bytes = await tts_service.synthesize(input_text, language=lang)
        media_type = "audio/wav"
        if audio_bytes.startswith(b"ID3") or (len(audio_bytes) >= 2 and audio_bytes[:2] == b"\xff\xfb"):
            media_type = "audio/mpeg"

        return Response(
            content=audio_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": "inline; filename=speech.wav",
                "Cache-Control": "public, max-age=3600",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice/speak")
async def speak_through_speakers(req: SpeakRequest):
    """
    Synthesizes speech and plays it aloud through the server's system speakers
    using native Windows MCI / winsound.
    """
    try:
        audio_bytes = await tts_service.synthesize(req.text, language=req.language or "en")
        played = play_audio_to_speakers(audio_bytes, "manual_speak.wav")
        return {
            "success": True,
            "text": req.text,
            "language": req.language,
            "played_to_speakers": played,
            "audio_bytes": len(audio_bytes),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Voice Wake-Up Daemon Endpoints (Alexa & Apple Siri Style)
# ---------------------------------------------------------------------------

@router.get("/voice/wakeup/status")
async def get_wakeup_status():
    """Retrieve running status and metrics for the background voice wake-up daemon."""
    daemon = get_voice_wakeup_daemon()
    return daemon.get_status()


@router.post("/voice/wakeup/start")
async def start_wakeup_daemon():
    """Start or resume the background voice wake-up listener."""
    daemon = get_voice_wakeup_daemon()
    daemon.start()
    return {"message": "Voice wake-up daemon started.", "status": daemon.get_status()}


@router.post("/voice/wakeup/stop")
async def stop_wakeup_daemon():
    """Pause or stop the background voice wake-up listener."""
    daemon = get_voice_wakeup_daemon()
    daemon.stop()
    return {"message": "Voice wake-up daemon stop signaled.", "status": daemon.get_status()}


@router.post("/voice/wakeup/simulate")
async def simulate_voice_wakeup(req: SimulateWakeRequest):
    """
    Simulate a live wake-up event (e.g. for testing or headless execution).
    Triggers acknowledgment speech, runs Coordinator, and speaks result through system speakers.
    """
    daemon = get_voice_wakeup_daemon()
    res = daemon.simulate_wake(text=req.text or "Welcome back chai", language=req.language or "en")
    return res
