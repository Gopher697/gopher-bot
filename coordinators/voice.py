from __future__ import annotations

import re

from coordinators.base import Coordinator


class Voice(Coordinator):
    name = "voice"

    def process(self, packet: dict) -> dict:
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
