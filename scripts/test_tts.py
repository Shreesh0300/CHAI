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

from backend.voice.tts_service import TTSService


async def main() -> None:
    service = TTSService()
    test_language = "en"
    test_text = "Welcome to CHAI. Speech synthesis is operational."
    output_path = repo_root / "scripts" / "test_output.wav"

    print("TTS Test")
    print(f"Language: {test_language}")
    print(f"Model: {service.model_name}")

    try:
        audio_bytes = await service.synthesize(test_text, language=test_language)
        output_path.write_bytes(audio_bytes)
        print(f"Output file: {output_path}")
        print(f"Audio bytes: {len(audio_bytes)}")
        print("Status: Success")

        # Play audio aloud through system speakers
        try:
            print("🔊 Playing synthesized speech through system speakers...")
            header = audio_bytes[:4]
            is_wav = header.startswith(b"RIFF")
            if is_wav:
                try:
                    import winsound
                    winsound.PlaySound(str(output_path), winsound.SND_FILENAME)
                except Exception:
                    pass
            else:
                import ctypes
                import time
                mci = ctypes.windll.winmm.mciSendStringW
                alias = f"test_tts_{int(time.time() * 1000)}"
                mci(f'open "{output_path.resolve()}" type mpegvideo alias {alias}', None, 0, 0)
                mci(f"play {alias} wait", None, 0, 0)
                mci(f"close {alias}", None, 0, 0)
        except Exception as play_err:
            print(f"(Speaker playback skipped: {play_err})")
    except Exception as e:
        print(f"Output file: None")
        print(f"Audio bytes: 0")
        print(f"Status: Failed - {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
