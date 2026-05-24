from __future__ import annotations

import base64
import json
import logging
import re
import sys
from pathlib import Path
from pathlib import Path as _Path
from typing import Any

from anthropic import Anthropic
from openai import OpenAI

from coordinators.base import Coordinator
from coordinators.percepts import AuditoryPercept, VisualPercept
from coordinators.tier_config import DEFAULT_TIER, get_tier_config

logger = logging.getLogger(__name__)


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_models import config  # noqa: E402
from sensors.vision_sensor import VisionSensor


class Sensory(Coordinator):
    name = "sensory"

    def __init__(self, lm_studio_api_key: str | None = None):
        self.lm_studio_api_key = lm_studio_api_key

    def process(self, packet: dict) -> dict:
        packet["input_type"] = packet.get("input_type") or "text"

        # Handle image attachments from the Discord bridge (or any future input source).
        # Each entry is {"filename": str, "data": bytes}.
        image_attachments = packet.pop("image_attachments", None) or []
        if image_attachments and "visual_percept" not in packet:
            tier_config = get_tier_config(packet.get("tier", DEFAULT_TIER))
            descriptions = []
            for attachment in image_attachments:
                filename = attachment.get("filename", "image")
                data = attachment.get("data", b"")
                if not data:
                    continue
                desc = _describe_image(data, filename, tier_config)
                if desc:
                    descriptions.append(f"[{filename}]: {desc}")
                else:
                    descriptions.append(f"[{filename}]: (image attached; no description available at current tier)")
            if descriptions:
                combined_description = "\n".join(descriptions)
                import time as _time_mod
                packet["visual_percept"] = {
                    "timestamp": _time_mod.time(),
                    "objects": [],
                    "motion_detected": False,
                    "motion_region": None,
                    "scene_type": "user_attachment",
                    "text_in_scene": [],
                    "faces_detected": 0,
                    "pose_summary": "",
                    "description": combined_description,
                }

        if "visual_percept" not in packet:
            latest_vp = VisionSensor.get_latest()
            if latest_vp:
                packet["visual_percept"] = latest_vp.to_dict()

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
        except Exception as e:
            import traceback as _tb
            print(f"[SENSORY ERROR] classify() failed: {e}", flush=True)
            _tb.print_exc()
            logger.exception("Sensory.classify failed: %s", e)
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
            response = _call_local_classifier(
                message,
                system_prompt,
                tier_config,
                lm_studio_api_key=self.lm_studio_api_key,
            )
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


def _call_local_classifier(
    message: str,
    system_prompt: str,
    tier_config: dict,
    lm_studio_api_key: str | None = None,
) -> Any:
    api_key = (
        config.LM_STUDIO_API_KEY
        if lm_studio_api_key is None
        else lm_studio_api_key
    )
    client = OpenAI(base_url=tier_config["base_url"], api_key=api_key)
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


def _media_type_from_filename(filename: str) -> str:
    ext = _Path(filename).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


def _describe_image(image_data: bytes, filename: str, tier_config: dict) -> str:
    """
    Generate a prose description of an image using the tier's sensory model.
    Returns an empty string if the tier is local (no vision) or if the call fails.
    Vision is only available when base_url is None (Anthropic cloud).
    """
    if tier_config.get("base_url"):
        # Local model - no vision capability
        return ""
    model = tier_config.get("sensory_model")
    if not model:
        return ""
    try:
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        media_type = _media_type_from_filename(filename)
        encoded = base64.standard_b64encode(image_data).decode("utf-8")
        response = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": encoded,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this image concisely as a factual note. "
                                "Cover what is shown, any visible text, and any context "
                                "relevant to a work log or memory system. "
                                "Two to four sentences maximum."
                            ),
                        },
                    ],
                }
            ],
        )
        return _extract_text(response).strip()
    except Exception as e:
        logger.warning("Image description failed for %s: %s", filename, e)
        return ""


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
