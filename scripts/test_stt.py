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

try:
    import sounddevice as sd
    import numpy as np
except ImportError as e:
    print(f"Error importing audio libraries: {e}")
    print("Please ensure sounddevice and numpy are installed: pip install sounddevice numpy")
    sys.exit(1)

from backend.voice.stt_service import STTService

# Configuration
DURATION_SECONDS = 10 # length of recording
SAMPLERATE = 16000  # Hz, common for speech models
CHANNELS = 1

def record_audio(duration: int = DURATION_SECONDS, samplerate: int = SAMPLERATE) -> bytes:
    """Record audio from the default microphone and return raw PCM bytes."""
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
    args = sys.argv[1:]
    if "--server" in args or "-srv" in args:
        import urllib.request
        file_arg = next((a for a in args if a not in ("--server", "-srv")), None)
        wav_file = Path(file_arg) if file_arg else repo_root / "scripts" / "test_output.wav"
        if not wav_file.exists():
            print(f"Generating test audio file at {wav_file}...")
            from backend.voice.tts_service import TTSService
            tts = TTSService()
            audio_bytes = await tts.synthesize("Welcome to CHAI platform.", language="en")
            wav_file.write_bytes(audio_bytes)

        print(f"[ServerMode] Sending audio file '{wav_file.name}' to FastAPI server /api/stt endpoint...")
        boundary = "----CHAIFormBoundary7MA4YWxkTrZu0gW"
        body = bytearray()
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="audio"; filename="{wav_file.name}"\r\n'.encode("utf-8"))
        body.extend(b"Content-Type: audio/wav\r\n\r\n")
        body.extend(wav_file.read_bytes())
        body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

        req = urllib.request.Request(
            "http://localhost:8000/api/stt",
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                import json
                res = json.loads(resp.read().decode("utf-8"))
                print("\n================ SERVER STT TRANSCRIPTION RESPONSE ================")
                print("Status: 200 OK (Server Transcribed)")
                print(f"Transcript: {res.get('transcript')}")
                print(f"Detected Language: {res.get('detected_language')}")
                print(f"Confidence: {res.get('confidence')}")
                print(f"Wake Word Detected: {res.get('wake_word_detected')}")
                print("====================================================================\n")
                return
        except Exception as e:
            print(f"[ServerMode Error]: Could not communicate with server: {e}")
            return

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
