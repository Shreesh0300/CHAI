"""
Autonomous Voice Wake-Up Daemon for CHAI Platform.

Provides hands-free, always-on Alexa & Siri style voice activation:
1. Runs continuously in a background daemon thread started automatically when the server boots.
2. Captures audio from the microphone and analyzes speech with STTService.
3. Listens for multilingual wake phrases:
   - "Hey CHAI", "CHAI", "Welcome back CHAI", "Wake up CHAI", "OK CHAI"
   - Hindi: "नमस्ते चाय", "हे चाय", "सुनो चाय", "चाई"
   - Kannada: "ನಮಸ್ಕಾರ ಚಾಯ್", "ಹೇ ಚಾಯ್", "ಕೇಳು ಚಾಯ್", "ಚಾಯ್"
   - Sanskrit: "नमस्कारम् चाय", "चाय"
4. When wake-word is detected:
   - Immediately acknowledges and synthesizes spoken response using TTSService.
   - Speaks aloud through host system speakers (via native Windows MCI / winsound).
   - If user provided a query with the wake-word, or speaks after wake-word:
     Executes multi-agent Coordinator, synthesizes answer, and speaks it back!
5. Fault tolerant: gracefully handles absence of microphone or temporary audio device lock.
"""

import os
import sys
import time
import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List

from backend.voice.stt_service import STTService
from backend.voice.tts_service import TTSService
from backend.core.coordinator import Coordinator
from backend.core.schemas import SolveRequest
from backend.shared.logger import get_logger

logger = get_logger(__name__)

WAKE_PATTERNS = [
    "chai",
    "chay",
    "hey chai",
    "hi chai",
    "hello chai",
    "welcome back chai",
    "wake up chai",
    "ok chai",
    "okay chai",
    "ಚಾಯ್",
    "ನಮಸ್ಕಾರ ಚಾಯ್",
    "ಹೇ ಚಾಯ್",
    "ಕೇಳು ಚಾಯ್",
    "चाई",
    "नमस्ते चाई",
    "हे चाय",
    "सुनो चाई",
    "नमस्कारम्",
]

RESPONSES = {
    "en": "Hello! Welcome back. CHAI multi-agent platform is awake and listening. What problem would you like the agents to solve?",
    "kn": "ನಮಸ್ಕಾರ! ಚಾಯ್ ವೇದಿಕೆ ಸಿದ್ಧವಾಗಿದೆ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?",
    "hi": "नमस्ते! चाई प्रणाली सक्रिय है। मैं आपकी क्या मदद कर सकता हूँ?",
    "sa": "नमस्कारम्! चाय् कार्यप्रणाली सज्जा अस्ति।",
}


def play_audio_to_speakers(audio_bytes: bytes, temp_filename: str = "chai_voice_out.wav") -> bool:
    """Play audio aloud through computer speakers using native Windows APIs."""
    if not audio_bytes:
        return False

    temp_dir = Path(__file__).resolve().parent / "audio_cache"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / temp_filename

    try:
        temp_path.write_bytes(audio_bytes)
    except Exception as e:
        logger.warning(f"[VoiceWakeup] Could not write temp audio: {e}")
        return False

    header = audio_bytes[:4]
    is_wav = header.startswith(b"RIFF")

    # 1. For WAV files on Windows, winsound is immediate and lightweight
    if is_wav:
        try:
            import winsound
            winsound.PlaySound(str(temp_path), winsound.SND_FILENAME)
            return True
        except Exception as ws_err:
            logger.debug(f"[VoiceWakeup] winsound fallback: {ws_err}")

    # 2. Native Windows MCI player (supports MP3 & WAV)
    try:
        import ctypes
        mci = ctypes.windll.winmm.mciSendStringW
        alias = f"chai_spk_{int(time.time() * 1000)}"
        open_cmd = (
            f'open "{temp_path.resolve()}" type mpegvideo alias {alias}'
            if not is_wav
            else f'open "{temp_path.resolve()}" alias {alias}'
        )
        res_open = mci(open_cmd, None, 0, 0)
        if res_open == 0:
            mci(f"play {alias} wait", None, 0, 0)
            mci(f"close {alias}", None, 0, 0)
            return True
    except Exception as mci_err:
        logger.debug(f"[VoiceWakeup] MCI error: {mci_err}")

    # 3. PowerShell presentationCore player fallback
    try:
        import subprocess
        ps_cmd = (
            f"Add-Type -AssemblyName presentationCore; "
            f"$player = New-Object System.Windows.Media.MediaPlayer; "
            f"$player.Open([Uri]'{temp_path.resolve().as_uri()}'); "
            f"$player.Play(); "
            f"Start-Sleep -Seconds 5"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=False, timeout=8)
        return True
    except Exception as ps_err:
        logger.warning(f"[VoiceWakeup] PowerShell playback note: {ps_err}")

    return False


def extract_wake_word_and_query(text: str) -> Dict[str, Any]:
    """Check if any wake phrase is present and extract trailing question."""
    lower = text.lower().strip()
    for phrase in WAKE_PATTERNS:
        idx = lower.find(phrase)
        if idx != -1:
            query = lower[idx + len(phrase):].strip(" ,:;.!?")
            return {
                "matched": True,
                "phrase": phrase,
                "query": query,
            }
    return {"matched": False, "phrase": "", "query": ""}


class VoiceWakeupDaemon:
    """
    Background daemon running continuous microphone listening for wake phrases.
    Like Apple Siri & Amazon Alexa, starts automatically with the server.
    """

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_active: bool = False
        self._last_wake_time: Optional[str] = None
        self._last_detected_phrase: Optional[str] = None
        self._status_message: str = "Initialized"
        self._lock = threading.Lock()
        self._stt: Optional[STTService] = None
        self._tts: Optional[TTSService] = None
        self._coordinator: Optional[Coordinator] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_active(self) -> bool:
        return self._is_active

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running": self.is_running,
                "active": self._is_active,
                "status_message": self._status_message,
                "last_wake_time": self._last_wake_time,
                "last_detected_phrase": self._last_detected_phrase,
                "wake_patterns": WAKE_PATTERNS[:8],
            }

    def start(self) -> None:
        """Start the background daemon thread if not already running."""
        with self._lock:
            if self.is_running:
                logger.info("[VoiceWakeup] Daemon already running.")
                return

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="VoiceWakeupDaemon", daemon=True)
            self._thread.start()
            logger.info("[VoiceWakeup] 🚀 Background Voice Wake-Up Daemon started (Alexa/Siri style).")

    def stop(self) -> None:
        """Signal the background daemon to stop."""
        with self._lock:
            if not self.is_running:
                return
            self._stop_event.set()
            logger.info("[VoiceWakeup] Stopping voice wake-up daemon...")

    def _ensure_services(self) -> None:
        if self._stt is None:
            self._stt = STTService()
        if self._tts is None:
            self._tts = TTSService()
        if self._coordinator is None:
            self._coordinator = Coordinator()

    def _record_audio_slice(self, duration: float = 3.5, samplerate: int = 16000) -> Optional[bytes]:
        """Record audio chunk from system microphone using sounddevice or pyaudio."""
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            return None

        try:
            audio = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype="int16")
            # Wait for recording or stop event
            t0 = time.time()
            while time.time() - t0 < duration:
                if self._stop_event.is_set():
                    sd.stop()
                    return None
                time.sleep(0.1)
            sd.wait()

            # Check peak energy to avoid calling STT on pure silence
            peak = int(np.max(np.abs(audio)))
            if peak < 350:  # Silence or near silence
                return None
            return audio.tobytes()
        except Exception as e:
            logger.debug(f"[VoiceWakeup] Microphone slice read exception: {e}")
            return None

    def _handle_wake_event(self, spoken_text: str, query: str, language: str = "en") -> None:
        """Handle detected wake event: acknowledge, run multi-agent query, speak answer."""
        self._is_active = True
        self._last_wake_time = time.strftime("%Y-%m-%d %H:%M:%S")
        self._status_message = f"Awake! Processing user voice command ({language})"
        logger.info(f"[VoiceWakeup] 🌟 WAKE-UP EVENT TRIGGERED! Phrase: '{spoken_text}' | Query: '{query}'")

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)

            # 1. Acknowledge wake-up with speech
            lang = language if language in RESPONSES else "en"
            ack_text = RESPONSES.get(lang, RESPONSES["en"])

            try:
                ack_audio = loop.run_until_complete(self._tts.synthesize(ack_text, language=lang))
                play_audio_to_speakers(ack_audio, "chai_ack.wav")
            except Exception as e:
                logger.warning(f"[VoiceWakeup] Acknowledgement TTS error: {e}")

            # 2. Determine command to execute
            user_command = query.strip()
            if not user_command:
                # User only said wake phrase, listen for command
                logger.info("[VoiceWakeup] Listening for user follow-up command...")
                time.sleep(0.5)
                cmd_audio = self._record_audio_slice(duration=6.0)
                if cmd_audio:
                    stt_res = loop.run_until_complete(self._stt.transcribe(cmd_audio))
                    if stt_res and stt_res.success and stt_res.text:
                        user_command = stt_res.text.strip()
                        lang = stt_res.language or lang

            # 3. If there is a command, coordinate with AI agents and synthesize response
            if user_command:
                logger.info(f"[VoiceWakeup] Coordinating AI agents for command: '{user_command}'")
                solve_req = SolveRequest(problem=user_command, language=lang)
                solve_resp = loop.run_until_complete(self._coordinator.process_request(solve_req))

                ans = solve_resp.final_synthesized_answer or "Your request has been processed."
                # Speak first 2-3 sentences aloud so it's not overly lengthy on speakers
                spoken_summary = ". ".join(ans.split(". ")[:3])
                if not spoken_summary.endswith("."):
                    spoken_summary += "."

                logger.info(f"[VoiceWakeup] Speaking synthesized answer aloud: '{spoken_summary[:100]}...'")
                ans_audio = loop.run_until_complete(self._tts.synthesize(spoken_summary, language=lang))
                play_audio_to_speakers(ans_audio, "chai_answer.wav")

        except Exception as err:
            logger.error(f"[VoiceWakeup] Error during wake-up flow: {err}", exc_info=True)
        finally:
            loop.close()
            self._is_active = False
            self._status_message = "Listening for wake word..."

    def simulate_wake(self, text: str = "Welcome back chai", language: str = "en") -> Dict[str, Any]:
        """Manually trigger wake flow (useful for verification or remote trigger)."""
        self._ensure_services()
        wake_info = extract_wake_word_and_query(text)
        query = wake_info.get("query", "") if wake_info.get("matched") else text
        threading.Thread(
            target=self._handle_wake_event,
            args=(text, query, language),
            daemon=True,
        ).start()
        return {
            "success": True,
            "simulated_text": text,
            "language": language,
            "extracted_query": query,
        }

    def _run_loop(self) -> None:
        """Continuous background listening loop."""
        self._ensure_services()
        self._status_message = "Listening for wake word..."

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Brief warmup delay after server boots
        time.sleep(2.0)

        while not self._stop_event.is_set():
            try:
                # Capture short listening slice
                audio_bytes = self._record_audio_slice(duration=3.5)
                if not audio_bytes:
                    time.sleep(0.3)
                    continue

                # Run STT transcription
                stt_res = loop.run_until_complete(self._stt.transcribe(audio_bytes))
                if not stt_res or not stt_res.success or not stt_res.text:
                    time.sleep(0.1)
                    continue

                transcript = stt_res.text.strip()
                wake_info = extract_wake_word_and_query(transcript)
                if wake_info["matched"]:
                    self._last_detected_phrase = wake_info["phrase"]
                    self._handle_wake_event(
                        spoken_text=transcript,
                        query=wake_info["query"],
                        language=stt_res.language or "en",
                    )
                    time.sleep(1.0)

            except Exception as e:
                logger.debug(f"[VoiceWakeup] Listener loop iteration note: {e}")
                self._status_message = f"Standby: {str(e)[:50]}"
                time.sleep(2.0)

        loop.close()
        self._status_message = "Stopped"
        logger.info("[VoiceWakeup] Background daemon stopped.")


# Singleton instance
_daemon_instance: Optional[VoiceWakeupDaemon] = None


def get_voice_wakeup_daemon() -> VoiceWakeupDaemon:
    global _daemon_instance
    if _daemon_instance is None:
        _daemon_instance = VoiceWakeupDaemon()
    return _daemon_instance
