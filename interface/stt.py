from __future__ import annotations

from io import BytesIO
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_models import config  # noqa: E402


def transcribe(audio_bytes: bytes) -> str:
    from openai import OpenAI

    audio_file = BytesIO(audio_bytes)
    audio_file.name = "audio.webm"

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
    )
    return str(getattr(transcript, "text", "")).strip()
