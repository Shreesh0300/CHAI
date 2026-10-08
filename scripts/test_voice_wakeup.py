"""
Interactive Voice Wake-Up & Text-To-Speech (TTS) Verification Script for CHAI.

Features:
1. Records speech from your microphone (using sounddevice).
2. Transcribes spoken speech and identifies language using STT (STTService).
3. Detects wake phrases: 'chai', 'welcome back chai', 'hey chai', 'ಚಾಯ್', 'चाई', etc.
4. On wake-up, synthesizes spoken response using TTS (TTSService).
5. Plays the synthesized voice response aloud through your laptop/PC speakers (winsound).

Usage:
  # Live microphone mode (speak 'Welcome back chai' or 'Hey chai'):
  python scripts/test_voice_wakeup.py

  # Test wake-up TTS immediately without microphone:
  python scripts/test_voice_wakeup.py --simulate
"""

import asyncio
import sys
import os
from pathlib import Path

# Ensure repo root is on sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
    from dotenv import load_dotenv
    env_file = repo_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        load_dotenv()
except ImportError:
    pass

from backend.voice.stt_service import STTService
from backend.voice.tts_service import TTSService

# Wake words & greetings across supported languages
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
    "ನಮಸ್ಕಾರ",
    "ಹಲೋ ಚಾಯ್",
    "चाई",
    "नमस्ते चाई",
    "हेलो चाई",
]

RESPONSES = {
    "en": "Hello! Welcome back. CHAI multi-agent platform is awake and ready. What problem would you like the agents to solve?",
    "kn": "ನಮಸ್ಕಾರ! ಚಾಯ್ ವೇದಿಕೆ ಸಿದ್ಧವಾಗಿದೆ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?",
    "hi": "नमस्ते! चाई प्रणाली सक्रिय है। मैं आपकी क्या मदद कर सकता हूँ?",
    "sa": "नमस्कारम्! चाय् कार्यप्रणाली सज्जा अस्ति।",
}


def is_wake_word_present(text: str) -> bool:
    """Check if any wake phrase is present in transcribed text."""
    lower = text.lower()
    for phrase in WAKE_PATTERNS:
        if phrase in lower:
            return True
    return False


def play_audio(audio_path: Path) -> None:
    """Play audio (MP3 or WAV) aloud through computer speakers using native Windows APIs."""
    audio_path = audio_path.resolve()
    print("🔊 Speaking aloud through system speakers...")

    try:
        header = audio_path.read_bytes()[:4]
    except Exception:
        header = b""

    is_wav = header.startswith(b"RIFF")

    # For WAV files, try winsound first
    if is_wav:
        try:
            import winsound
            winsound.PlaySound(str(audio_path), winsound.SND_FILENAME)
            return
        except Exception:
            pass

    # Native Windows MCI player (supports MP3, WAV, AAC natively on all Windows systems)
    try:
        import ctypes
        import time
        mci = ctypes.windll.winmm.mciSendStringW
        alias = f"chai_sound_{int(time.time() * 1000)}"
        open_cmd = (
            f'open "{audio_path}" type mpegvideo alias {alias}'
            if not is_wav
            else f'open "{audio_path}" alias {alias}'
        )
        res_open = mci(open_cmd, None, 0, 0)
        if res_open == 0:
            mci(f"play {alias} wait", None, 0, 0)
            mci(f"close {alias}", None, 0, 0)
            return
    except Exception as mci_err:
        print(f"MCI playback error: {mci_err}")

    # Fallback: Windows PowerShell presentationCore MediaPlayer
    try:
        import subprocess
        ps_cmd = (
            f"Add-Type -AssemblyName presentationCore; "
            f"$player = New-Object System.Windows.Media.MediaPlayer; "
            f"$player.Open([Uri]'{audio_path.as_uri()}'); "
            f"$player.Play(); "
            f"Start-Sleep -Seconds 6"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=False)
    except Exception as ps_err:
        print(f"Audio playback note: {ps_err}")


def record_microphone(duration: int = 7, samplerate: int = 16000) -> bytes:
    """Capture raw microphone audio."""
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        print("sounddevice or numpy not installed. Run with --simulate to test without mic.")
        sys.exit(1)

    try:
        dev = sd.query_devices(kind="input")
        dev_name = dev["name"] if dev else "Default"
    except Exception:
        dev_name = "Default"

    print("=" * 60)
    print("           CHAI VOICE WAKE-UP & TTS TEST            ")
    print("=" * 60)
    print(f"Using input device: {dev_name}")
    print(f"🎤 Recording {duration}s of audio... Speak now! (e.g. 'Welcome back CHAI')")
    
    audio = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype="int16")
    sd.wait()
    peak = int(np.max(np.abs(audio)))
    peak_pct = (peak / 32767.0) * 100.0
    print(f"Recording complete (audio peak level: {peak_pct:.1f}%).")
    
    if peak < 300:
        print("⚠️ Very low volume detected. Check if your microphone is unmuted.")
    return audio.tobytes()


async def wake_up_and_speak(spoken_text: str, detected_language: str = "en") -> None:
    """Handle wake-up event by synthesizing voice and speaking back."""
    tts = TTSService()
    output_path = repo_root / "scripts" / "test_output.wav"

    lang = detected_language if detected_language in RESPONSES else "en"
    reply_text = RESPONSES.get(lang, RESPONSES["en"])

    print("\n" + "=" * 60)
    print("✨ 🌟 [WAKE-UP EVENT TRIGGERED] 🌟 ✨")
    print("=" * 60)
    print(f"Spoken User Input: '{spoken_text}'")
    print(f"Detected Language: {lang}")
    print(f"CHAI Spoken Reply: '{reply_text}'")
    print("\nSynthesizing speech response...")

    audio_bytes = await tts.synthesize(reply_text, language=lang)
    output_path.write_bytes(audio_bytes)
    print(f"TTS Audio Generated: {len(audio_bytes):,} bytes (saved to {output_path.name})")

    # Speak aloud through speakers!
    play_audio(output_path)
    print("Wake-up and TTS playback complete!\n")


async def main() -> None:
    stt = STTService()
    args = sys.argv[1:]

    # Simulation mode
    if "--simulate" in args or "-s" in args:
        print("Running in simulated wake-up mode...")
        simulated_text = "yellow yellow yellow red green blue white orange Welcome back chai"
        await wake_up_and_speak(simulated_text, detected_language="en")
        return

    # Custom text mode
    if len(args) > 0 and not args[0].startswith("-"):
        custom_text = " ".join(args)
        lang = "kn" if any("\u0c80" <= c <= "\u0cff" for c in custom_text) else "en"
        await wake_up_and_speak(custom_text, detected_language=lang)
        return

    # Live microphone recording
    audio_bytes = record_microphone()
    print("Transcribing audio with STT...")
    stt_res = await stt.transcribe(audio_bytes)

    print("\n--- STT Result ---")
    print(f"Transcribed Text: '{stt_res.text}'")
    print(f"Detected Language: {stt_res.language}")
    print(f"STT Status: {'Success' if stt_res.success else 'Failed: ' + str(stt_res.error)}")

    if not stt_res.text:
        print("\nNo intelligible speech detected in the recording.")
        print("Tip: Run with 'python scripts/test_voice_wakeup.py --simulate' to test TTS wake-up directly.")
        return

    # Check wake word
    if is_wake_word_present(stt_res.text):
        await wake_up_and_speak(stt_res.text, detected_language=stt_res.language)
    else:
        print(f"\nNo wake word detected in '{stt_res.text}'.")
        print("Recognized wake phrases: 'chai', 'welcome back chai', 'hey chai', 'ಚಾಯ್', etc.")
        # Ask user if they still want to hear the wake response
        print("Triggering wake-up response anyway to test TTS:")
        await wake_up_and_speak(stt_res.text, detected_language=stt_res.language)


if __name__ == "__main__":
    asyncio.run(main())
