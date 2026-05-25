from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_models import config  # noqa: E402


TTS_MODEL = "tts-1"
TTS_VOICE = "fable"


def _get_tts_model() -> str:
    """
    Return the TTS model name.
    Reads TTS_MODEL from world_models.config if set; falls back to the
    module-level TTS_MODEL constant.
    """
    try:
        value = getattr(config, "TTS_MODEL", None)
        return value if isinstance(value, str) and value.strip() else TTS_MODEL
    except Exception:
        return TTS_MODEL


def _get_tts_voice() -> str:
    """
    Return the TTS voice name.
    Reads TTS_VOICE from world_models.config if set; falls back to the
    module-level TTS_VOICE constant.
    """
    try:
        value = getattr(config, "TTS_VOICE", None)
        return value if isinstance(value, str) and value.strip() else TTS_VOICE
    except Exception:
        return TTS_VOICE


def speak(text: str) -> bytes:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    response = client.audio.speech.create(
        model=_get_tts_model(),
        voice=_get_tts_voice(),
        input=text,
    )

    content = getattr(response, "content", None)
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    if hasattr(response, "read"):
        return response.read()
    return bytes(response)
