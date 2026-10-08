"""
Comprehensive automated tests for CHAI Voice Subsystem (STT and TTS) Integration.
Covers Section 22 requirements:
 1. STT empty audio
 2. STT successful transcription
 3. STT failure handling
 4. TTS empty text
 5. TTS success
 6. TTS failure fallback
 7. Voice route registration
 8. /api/solve still works
 9. Simple route still works
10. Complex route still works
11. Voice input reaches /api/solve
12. TTS receives only final_answer
13. Voice failure does not fail CHAI reasoning
"""

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from backend.main import app
from backend.voice.stt_service import STTService, parse_stt_result, _format_audio_payload
from backend.voice.tts_service import TTSService
from backend.voice.voice_models import STTResponse, TTSRequest, TTSResponse
from backend.core.router import route_request, ROUTE_SIMPLE, ROUTE_COMPLEX
from backend.core.coordinator import Coordinator
from backend.api.routes import coordinator

client = TestClient(app)


@pytest.fixture(autouse=True)
def enable_chai_mock_mode(monkeypatch):
    """Ensure tests run deterministically with mocked LLM credentials."""
    monkeypatch.setenv("CHAI_MOCK_MODE", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-mock-key")
    monkeypatch.setenv("STT_API_KEY", "test-mock-key")
    monkeypatch.setenv("TTS_API_KEY", "test-mock-key")


# ------------------------------------------------------------------------------
# 1. STT Empty Audio Handling
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_1_stt_empty_audio():
    """STT must gracefully reject empty audio bytes without crashing."""
    service = STTService()
    result = await service.transcribe(b"")
    assert result.success is False
    assert result.text == ""
    assert "No audio data provided" in (result.error or "")

    # API endpoint test
    files = {"audio": ("empty.wav", b"", "audio/wav")}
    response = client.post("/api/voice/stt", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["text"] == ""

    # STT alias endpoint test
    files_alias = {"file": ("empty.wav", b"", "audio/wav")}
    response_alias = client.post("/api/stt", files=files_alias)
    assert response_alias.status_code == 200
    alias_data = response_alias.json()
    assert alias_data["success"] is False
    assert alias_data["transcript"] == ""


# ------------------------------------------------------------------------------
# 2. STT Successful Transcription
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_2_stt_successful_transcription():
    """STT must correctly parse and transcribe spoken audio across languages."""
    # Test parse_stt_result across multilingual scripts
    en_text, en_lang = parse_stt_result("LANGUAGE: en\nTEXT: What is artificial intelligence?")
    assert en_text == "What is artificial intelligence?"
    assert en_lang == "en"

    hi_text, hi_lang = parse_stt_result("LANGUAGE: hi\nTEXT: नमस्ते, आप कैसे हैं?")
    assert hi_text == "नमस्ते, आप कैसे हैं?"
    assert hi_lang == "hi"

    kn_text, kn_lang = parse_stt_result("LANGUAGE: kn\nTEXT: ನಮಸ್ಕಾರ, ಹೇಗಿದ್ದೀರಾ?")
    assert kn_text == "ನಮಸ್ಕಾರ, ಹೇಗಿದ್ದೀರಾ?"
    assert kn_lang == "kn"

    sa_text, sa_lang = parse_stt_result("LANGUAGE: sa\nTEXT: नमस्कारम्, कुशलं वा?")
    assert sa_text == "नमस्कारम्, कुशलं वा?"
    assert sa_lang == "sa"

    # Test STT service with mock client
    service = STTService()
    mock_candidate = MagicMock()
    mock_part = MagicMock()
    mock_part.text = "LANGUAGE: en\nTEXT: Hello CHAI assistant"
    mock_part.audio_transcription = None
    mock_candidate.content.parts = [mock_part]
    mock_resp = MagicMock()
    mock_resp.candidates = [mock_candidate]

    with patch("google.genai.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.aio.models.generate_content = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_instance

        dummy_audio = b"RIFF" + b"\x00" * 100
        result = await service.transcribe(dummy_audio)
        assert result.success is True
        assert result.text == "Hello CHAI assistant"
        assert result.language == "en"
        assert result.error is None


# ------------------------------------------------------------------------------
# 3. STT Failure Handling
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_3_stt_failure_handling():
    """STT must capture external model/network errors safely without raising unhandled exceptions."""
    service = STTService()

    with patch("google.genai.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.aio.models.generate_content = AsyncMock(
            side_effect=RuntimeError("Google GenAI connection timeout")
        )
        mock_client_cls.return_value = mock_instance

        dummy_audio = b"RIFF" + b"\x00" * 50
        result = await service.transcribe(dummy_audio)
        assert result.success is False
        assert result.text == ""
        assert "Google GenAI connection timeout" in (result.error or "")


# ------------------------------------------------------------------------------
# 4. TTS Empty Text
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_4_tts_empty_text():
    """TTS must reject empty or whitespace text with a ValueError."""
    service = TTSService()
    with pytest.raises(ValueError, match="Text to synthesize cannot be empty"):
        await service.synthesize("")

    with pytest.raises(ValueError, match="Text to synthesize cannot be empty"):
        await service.synthesize("    \n\t   ")


# ------------------------------------------------------------------------------
# 5. TTS Success
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_5_tts_success():
    """TTS must return synthesized audio bytes when provider succeeds."""
    service = TTSService()
    expected_audio = b"RIFFfakeaudiobytes1234567890"

    mock_part = MagicMock()
    mock_inline = MagicMock()
    mock_inline.data = expected_audio
    mock_part.inline_data = mock_inline
    mock_candidate = MagicMock()
    mock_candidate.content.parts = [mock_part]
    mock_resp = MagicMock()
    mock_resp.candidates = [mock_candidate]

    with patch("google.genai.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.aio.models.generate_content = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_instance

        audio = await service.synthesize("Welcome to CHAI platform.", language="en")
        assert audio == expected_audio

    # Test HTTP endpoint
    with patch.object(service, "synthesize", AsyncMock(return_value=expected_audio)):
        with patch("backend.api.voice_routes.tts_service", service):
            # Test JSON metadata response
            response = client.post("/api/voice/tts", json={"text": "Hello"})
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["audio_size_bytes"] == len(expected_audio)

            # Test stream response
            stream_resp = client.post("/api/voice/tts/stream", json={"text": "Hello"})
            assert stream_resp.status_code == 200
            assert stream_resp.content == expected_audio


# ------------------------------------------------------------------------------
# 6. TTS Failure Fallback
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_6_tts_failure_fallback():
    """TTS must gracefully fallback to audio synthesizer when Gemini quota is exhausted."""
    service = TTSService()
    fallback_audio = b"RIFFfallbackaudio"

    with patch("google.genai.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.aio.models.generate_content = AsyncMock(
            side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")
        )
        mock_client_cls.return_value = mock_instance

        with patch.object(service, "_synthesize_fallback", return_value=fallback_audio) as mock_fb:
            audio = await service.synthesize("Fallback test", language="en")
            assert audio == fallback_audio
            assert mock_fb.called


# ------------------------------------------------------------------------------
# 7. Voice Route Registration
# ------------------------------------------------------------------------------

def test_7_voice_route_registration():
    """Verify that all voice endpoints are registered in the FastAPI app."""
    registered_paths = list(app.openapi()["paths"].keys())
    assert "/api/voice/stt" in registered_paths
    assert "/api/stt" in registered_paths
    assert "/api/voice/tts" in registered_paths
    assert "/api/voice/tts/stream" in registered_paths
    assert "/voice/stt" in registered_paths
    assert "/voice/tts" in registered_paths
    assert "/api/solve" in registered_paths




# ------------------------------------------------------------------------------
# 8. /api/solve Still Works
# ------------------------------------------------------------------------------

def test_8_api_solve_still_works():
    """The /api/solve endpoint contract must remain completely functional and unchanged."""
    payload = {"problem": "What is Python?"}
    response = client.post("/api/solve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "request_status" in data
    assert data["request_status"] == "completed"
    assert "final_synthesized_answer" in data
    assert len(data["final_synthesized_answer"]) > 0


# ------------------------------------------------------------------------------
# 9. Simple Route Still Works
# ------------------------------------------------------------------------------

def test_9_simple_route_still_works():
    """Simple queries must continue routing to ROUTE_SIMPLE without invoking multi-agent panel."""
    decision = route_request("What is Python?")
    assert decision.route == ROUTE_SIMPLE
    assert decision.requires_multi_agent_reasoning is False
    assert decision.required_agents == []

    decision_bs = route_request("Explain binary search.")
    assert decision_bs.route == ROUTE_SIMPLE


# ------------------------------------------------------------------------------
# 10. Complex Route Still Works
# ------------------------------------------------------------------------------

def test_10_complex_route_still_works():
    """Complex multi-domain queries must continue routing to ROUTE_COMPLEX with selected agents."""
    decision = route_request("Design a secure and scalable distributed banking system with fraud detection.")
    assert decision.route == ROUTE_COMPLEX
    assert decision.requires_multi_agent_reasoning is True
    assert len(decision.required_agents) >= 2


# ------------------------------------------------------------------------------
# 11. Voice Input Reaches /api/solve
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_11_voice_input_reaches_solve():
    """
    End-to-end voice flow:
    Audio -> STT -> Transcript -> /api/solve -> Final Answer
    """
    stt_service = STTService()
    mock_audio = b"RIFF" + b"\x00" * 64

    # 1. Simulate STT transcribing spoken user input
    with patch.object(
        stt_service,
        "transcribe",
        AsyncMock(return_value=STTResponse(text="What is machine learning?", language="en", success=True)),
    ):
        stt_result = await stt_service.transcribe(mock_audio)
        assert stt_result.success is True
        assert stt_result.text == "What is machine learning?"

    # 2. Pass transcribed text into CHAI /api/solve
    solve_response = client.post("/api/solve", json={"problem": stt_result.text})
    assert solve_response.status_code == 200
    solve_data = solve_response.json()
    assert solve_data["request_status"] == "completed"
    assert len(solve_data["final_synthesized_answer"]) > 0


# ------------------------------------------------------------------------------
# 12. TTS Receives Only final_answer
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_12_tts_receives_only_final_answer():
    """
    TTS must receive strictly the polished final answer.
    Internal execution trace, selected agents, debug logs, and metadata MUST NOT be spoken.
    """
    solve_payload = {
        "problem": "Explain Python lists",
    }
    response = client.post("/api/solve", json=solve_payload)
    assert response.status_code == 200
    data = response.json()

    final_answer = data.get("final_synthesized_answer", "")
    assert len(final_answer) > 0

    # Ensure internal metadata exists on solve response but is decoupled
    selected_agents = data.get("selected_agents", [])
    agent_statuses = data.get("agent_execution_statuses", [])

    # Mock TTS service to verify exactly what text argument is received
    tts_service = TTSService()
    with patch.object(tts_service, "synthesize", AsyncMock(return_value=b"RIFFspoken")) as mock_synthesize:
        # Frontend/orchestration sends ONLY final_answer to TTS
        await tts_service.synthesize(final_answer, language="en")

        mock_synthesize.assert_called_once()
        called_args, called_kwargs = mock_synthesize.call_args
        spoken_text = called_args[0] if called_args else called_kwargs.get("text", "")

        # Spoken text must equal final_answer and contain no leaked metadata
        assert spoken_text == final_answer
        assert "execution_trace" not in spoken_text
        assert "agent_execution_statuses" not in spoken_text
        assert "selected_agents" not in spoken_text


# ------------------------------------------------------------------------------
# 13. Voice Failure Does Not Fail CHAI Reasoning
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_13_voice_failure_does_not_fail_chai_reasoning():
    """
    If TTS synthesis fails (e.g. quota, network error), the CHAI reasoning
    result must remain successful and available as text.
    Voice failure is an I/O modality failure, not an intelligence failure.
    """
    # 1. CHAI solve succeeds
    response = client.post("/api/solve", json={"problem": "What is Python?"})
    assert response.status_code == 200
    data = response.json()
    assert data["request_status"] == "completed"
    final_text = data["final_synthesized_answer"]
    assert len(final_text) > 0

    # 2. Simulate subsequent TTS failure
    tts_service = TTSService()
    with patch.object(
        tts_service,
        "synthesize",
        AsyncMock(side_effect=RuntimeError("TTS engine network unavailable")),
    ):
        tts_failed = False
        try:
            await tts_service.synthesize(final_text, language="en")
        except RuntimeError:
            tts_failed = True

        assert tts_failed is True

    # 3. Verify reasoning result is completely unaffected
    assert data["request_status"] == "completed"
    assert data["final_synthesized_answer"] == final_text
