from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_models import config  # noqa: E402


def speak(text: str) -> bytes:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    response = client.audio.speech.create(
        model="tts-1",
        voice="fable",
        input=text,
    )

    content = getattr(response, "content", None)
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    if hasattr(response, "read"):
        return response.read()
    return bytes(response)
