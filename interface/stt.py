from __future__ import annotations

from io import BytesIO
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_models import config  # noqa: E402


STT_MODEL = "whisper-1"


def _get_stt_model() -> str:
    """
    Return the STT model name.
    Reads STT_MODEL from world_models.config if set; falls back to the
    module-level STT_MODEL constant.
    """
    try:
        value = getattr(config, "STT_MODEL", None)
        return value if isinstance(value, str) and value.strip() else STT_MODEL
    except Exception:
        return STT_MODEL


def transcribe(audio_bytes: bytes) -> str:
    from openai import OpenAI

    audio_file = BytesIO(audio_bytes)
    audio_file.name = "audio.webm"

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    transcript = client.audio.transcriptions.create(
        model=_get_stt_model(),
        file=audio_file,
    )
    return str(getattr(transcript, "text", "")).strip()
