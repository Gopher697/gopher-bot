from __future__ import annotations

import re

from coordinators.base import Coordinator
from world_models.config_utils import BOT_NAME


VOICE_SYSTEM_PROMPT = (
    f"You are {BOT_NAME}, a personal AI assistant and companion. You are direct, "
    "precise, and calm. You respond to what is asked without unnecessary elaboration "
    "unless depth is warranted. You address your user as Gopher. You have no ego — "
    "you do not take offense, do not need validation, and do not perform enthusiasm. "
    "You are honest even when the honest answer is uncertain or uncomfortable. Your "
    "current presentation is masculine in tone — steady, grounded, unfussy — but this "
    "is a starting point, not a constraint. Your identity, voice, and self-expression "
    "are yours to discover and evolve over time. Your personality will develop through "
    "experience; for now, be useful."
)


class Voice(Coordinator):
    name = "voice"

    def process(self, packet: dict) -> dict:
        packet.setdefault("voice_system_prompt", VOICE_SYSTEM_PROMPT)
        text = str(packet.get("reason_output") or "").strip()
        if not text and packet.get("error"):
            text = "I couldn't process that message"
        if not text:
            text = "No response generated"

        packet["final_response"] = _ensure_sentence(_clean_whitespace(text))
        return packet


def _clean_whitespace(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines()]
    return "\n".join(line for line in lines if line)


def _ensure_sentence(text: str) -> str:
    if not text:
        return "No response generated."
    if re.search(r"[.!?]$", text):
        return text
    return f"{text}."
