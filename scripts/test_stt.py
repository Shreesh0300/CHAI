import asyncio
import sys
from pathlib import Path

# Add project root to sys.path so backend modules can be imported
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

# Optional audio libraries for interactive microphone testing
from backend.voice.stt_service import STTService

# Configuration
DURATION_SECONDS = 10 # length of recording
SAMPLERATE = 16000  # Hz, common for speech models
CHANNELS = 1

def record_audio(duration: int = DURATION_SECONDS, samplerate: int = SAMPLERATE) -> bytes:
    """Record audio from the default microphone and return raw PCM bytes."""
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError as e:
        print(f"Error importing audio libraries: {e}")
        print("Please ensure sounddevice and numpy are installed: pip install sounddevice numpy")
        sys.exit(1)

    try:
        dev = sd.query_devices(kind="input")
        dev_name = dev["name"] if dev else "Default"
    except Exception:
        dev_name = "Default"

    print(f"Using input device: {dev_name}")
    print(f"🎤 Recording {duration}s of audio... Speak now!")
    audio = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=CHANNELS, dtype="int16")
    sd.wait()
    peak = int(np.max(np.abs(audio)))
    peak_pct = (peak / 32767.0) * 100.0
    print(f"Recording complete (audio peak level: {peak_pct:.1f}%).")
    if peak < 300:
        print("⚠️ Warning: Very low volume detected. If Text is empty, check if your mic is muted or if the wrong device is selected.")
    return audio.tobytes()

async def main() -> None:
    stt_service = STTService()
    audio_bytes = record_audio()
    print("Transcribing audio...")
    response = await stt_service.transcribe(audio_bytes)
    print("--- STT Result ---")
    print(f"Text: {response.text}")
    print(f"Language: {response.language}")
    print(f"Error: {response.error}")

    if not response.text and response.success:
        print("(Note: Empty text means no intelligible speech was recognized in the 5s recording.)")

if __name__ == "__main__":
    asyncio.run(main())
