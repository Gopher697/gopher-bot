from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from openai import OpenAI

from coordinators.base import Coordinator
from coordinators.percepts import AuditoryPercept, VisualPercept
from coordinators.tier_config import DEFAULT_TIER, get_tier_config


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_models import config  # noqa: E402


class Sensory(Coordinator):
    name = "sensory"

    def process(self, packet: dict) -> dict:
        packet["input_type"] = packet.get("input_type") or "text"

        # Parse percept schemas if present
        if "visual_percept" in packet and isinstance(packet["visual_percept"], dict):
            try:
                packet["parsed_visual_percept"] = VisualPercept.from_dict(packet["visual_percept"])
            except Exception as e:
                packet["percept_error"] = f"Failed to parse visual percept: {e}"

        if "auditory_percept" in packet and isinstance(packet["auditory_percept"], dict):
            try:
                percept = AuditoryPercept.from_dict(packet["auditory_percept"])
                packet["parsed_auditory_percept"] = percept
                # If there's a transcript and no explicit message, promote it
                if percept.transcript and not packet.get("message"):
                    packet["message"] = percept.transcript
                    packet["input_type"] = "audio"
            except Exception as e:
                packet["percept_error"] = f"Failed to parse auditory percept: {e}"

        message = str(packet.get("message", "")).strip()
        if not message:
            packet["error"] = "empty message"
            return packet

        try:
            classification = self.classify(message, packet.get("tier", DEFAULT_TIER))
        except Exception:
            packet["error"] = "input classification failed"
            return packet

        packet["intent"] = classification["intent"]
        packet["keywords"] = classification["keywords"]
        return packet

    def classify(self, message: str, tier: int = DEFAULT_TIER) -> dict:
        tier_config = get_tier_config(tier)
        system_prompt = (
            "Classify the user's message for a coordinator pipeline. "
            "Return only JSON with keys intent and keywords. "
            "intent must be a short string. keywords must be a list of short strings. "
            "Do not answer the user."
        )
        if tier_config["base_url"]:
            response = _call_local_classifier(message, system_prompt, tier_config)
        else:
            response = _call_anthropic_classifier(message, system_prompt, tier_config)
        return _parse_classification(_extract_text(response))


def _extract_text(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if choices:
        content = getattr(getattr(choices[0], "message", None), "content", None)
        if content is None and isinstance(choices[0], dict):
            content = choices[0].get("message", {}).get("content")
        if content:
            return str(content).strip()

    parts = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            parts.append(str(text))
    return "\n".join(parts).strip()


def _call_local_classifier(message: str, system_prompt: str, tier_config: dict) -> Any:
    client = OpenAI(base_url=tier_config["base_url"], api_key="local")
    return client.chat.completions.create(
        model=tier_config["sensory_model"],
        max_tokens=256,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
    )


def _call_anthropic_classifier(message: str, system_prompt: str, tier_config: dict) -> Any:
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return client.messages.create(
        model=tier_config["sensory_model"],
        max_tokens=256,
        system=system_prompt,
        messages=[{"role": "user", "content": message}],
    )


def _parse_classification(text: str) -> dict:
    payload = _loads_json_object(text)
    intent = str(payload.get("intent") or "unknown").strip() or "unknown"
    raw_keywords = payload.get("keywords") or []
    if not isinstance(raw_keywords, list):
        raw_keywords = []

    keywords = []
    for keyword in raw_keywords:
        value = str(keyword).strip().lower()
        if value and value not in keywords:
            keywords.append(value)

    return {"intent": intent, "keywords": keywords}


def _loads_json_object(text: str) -> dict:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

    return payload if isinstance(payload, dict) else {}
