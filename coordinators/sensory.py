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


SENSORY_TIMEOUT_SECONDS = 30

# Phrases that indicate the user wants the bot to look at the current screen.
_SCREEN_INTENT_RE = re.compile(
    r"(what.{0,15}(see|on.{0,10}screen|on.{0,10}monitor|on.{0,10}display|on.{0,10}desktop)"
    r"|look\s+at.{0,15}(screen|monitor|display|desktop)"
    r"|can\s+you\s+see"
    r"|see\s+my\s+screen"
    r"|your\s+screen"
    r"|my\s+screen)",
    re.IGNORECASE,
)

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
            if tier_config.get("base_url"):
                # Local VLM tier: pass raw bytes to Reason; skip pre-description.
                # The VLM will receive the actual image data as multimodal content.
                raw_images: list[dict] = []
                for attachment in image_attachments:
                    filename = attachment.get("filename", "image")
                    data = attachment.get("data", b"")
                    if not data:
                        continue
                    media_type = _media_type_from_filename(filename)
                    encoded = base64.standard_b64encode(data).decode("utf-8")
                    raw_images.append({
                        "filename": filename,
                        "media_type": media_type,
                        "data_b64": encoded,
                    })
                if raw_images:
                    packet["raw_images_for_reason"] = raw_images
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
                        "description": "",
                    }
            else:
                # Cloud tier: generate a text description via the Anthropic vision API.
                descriptions: list[str] = []
                for attachment in image_attachments:
                    filename = attachment.get("filename", "image")
                    data = attachment.get("data", b"")
                    if not data:
                        continue
                    desc = _describe_image(data, filename, tier_config)
                    if desc:
                        descriptions.append(f"[{filename}]: {desc}")
                    else:
                        descriptions.append(
                            f"[{filename}]: (image attached; no description available)"
                        )
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

        audio_attachments = packet.pop("audio_attachments", None) or []
        if audio_attachments and "auditory_percept" not in packet:
            for attachment in audio_attachments:
                filename = attachment.get("filename", "audio.ogg")
                data = attachment.get("data", b"")
                if not data:
                    continue
                try:
                    from interface.stt import transcribe as _transcribe

                    transcript = _transcribe(data, filename=filename)
                except Exception as exc:
                    logger.warning("Audio transcription failed for %s: %s", filename, exc)
                    transcript = ""
                import time as _time_mod
                packet["auditory_percept"] = {
                    "timestamp": _time_mod.time(),
                    "voice_present": bool(transcript),
                    "transcript": transcript,
                    "sound_class": "speech" if transcript else "unknown",
                    "speaker_id": "unknown",
                    "tone_signal": "",
                }
                break

        video_attachments = packet.pop("video_attachments", None) or []
        if video_attachments and "visual_percept" not in packet:
            attachment = video_attachments[0]
            filename = attachment.get("filename", "video.mp4")
            data = attachment.get("data", b"")
            if data:
                _process_video(
                    packet,
                    data,
                    filename,
                    get_tier_config(packet.get("tier", DEFAULT_TIER)),
                )

        if "visual_percept" not in packet:
            message_text = str(packet.get("message", ""))
            if _SCREEN_INTENT_RE.search(message_text):
                # User explicitly asked to see the screen - capture fresh.
                png_bytes = _capture_screen()
                if png_bytes:
                    tier_config = get_tier_config(packet.get("tier", DEFAULT_TIER))
                    import time as _time_mod

                    if tier_config.get("base_url"):
                        encoded = base64.standard_b64encode(png_bytes).decode("utf-8")
                        packet["raw_images_for_reason"] = [{
                            "filename": "screen.png",
                            "media_type": "image/png",
                            "data_b64": encoded,
                        }]
                        packet["visual_percept"] = {
                            "timestamp": _time_mod.time(),
                            "objects": [],
                            "motion_detected": False,
                            "motion_region": None,
                            "scene_type": "on_demand_capture",
                            "text_in_scene": [],
                            "faces_detected": 0,
                            "pose_summary": "",
                            "description": "",
                        }
                    else:
                        desc = _describe_image(png_bytes, "screen.png", tier_config)
                        packet["visual_percept"] = {
                            "timestamp": _time_mod.time(),
                            "objects": [],
                            "motion_detected": False,
                            "motion_region": None,
                            "scene_type": "on_demand_capture",
                            "text_in_scene": [],
                            "faces_detected": 0,
                            "pose_summary": "",
                            "description": (
                                desc or "(screen captured; description unavailable)"
                            ),
                        }
            else:
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
    client = OpenAI(
        base_url=tier_config["base_url"],
        api_key=api_key,
        timeout=SENSORY_TIMEOUT_SECONDS,
    )
    return client.chat.completions.create(
        model=tier_config["sensory_model"],
        max_tokens=256,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
    )


def _call_anthropic_classifier(message: str, system_prompt: str, tier_config: dict) -> Any:
    client = Anthropic(
        api_key=config.ANTHROPIC_API_KEY,
        timeout=SENSORY_TIMEOUT_SECONDS,
    )
    return client.messages.create(
        model=tier_config["sensory_model"],
        max_tokens=256,
        system=system_prompt,
        messages=[{"role": "user", "content": message}],
    )


def _capture_screen() -> bytes | None:
    """
    Capture all monitors as a single PNG using mss.

    Returns raw PNG bytes, or None if mss is not installed or capture fails.
    """
    try:
        import mss as _mss
        import mss.tools as _mss_tools

        with _mss.mss() as sct:
            img = sct.grab(sct.monitors[0])
            return _mss_tools.to_png(img.rgb, img.size)
    except ImportError:
        logger.debug("mss not installed; on-demand screen capture unavailable")
        return None
    except Exception as exc:
        logger.warning("Screen capture failed: %s", exc)
        return None


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
        client = Anthropic(
            api_key=config.ANTHROPIC_API_KEY,
            timeout=SENSORY_TIMEOUT_SECONDS,
        )
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


def _process_video(packet: dict, video_data: bytes, filename: str, tier_config: dict) -> None:
    """
    Extract frames and audio from a video attachment using ffmpeg.
    Sets packet["visual_percept"] from frame descriptions and/or
    packet["auditory_percept"] from the audio transcript.

    Gracefully does nothing if ffmpeg is not installed.
    """
    import os
    import subprocess
    import tempfile
    import time as _time_mod

    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        logger.warning("ffmpeg not found; video attachment from %s not processed", filename)
        packet["visual_percept"] = {
            "timestamp": _time_mod.time(),
            "objects": [],
            "motion_detected": False,
            "motion_region": None,
            "scene_type": "user_attachment",
            "text_in_scene": [],
            "faces_detected": 0,
            "pose_summary": "",
            "description": f"[{filename}]: (video attached; ffmpeg required for processing)",
        }
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, _Path(filename).name)
        with open(video_path, "wb") as handle:
            handle.write(video_data)

        frames_pattern = os.path.join(tmpdir, "frame%02d.jpg")
        try:
            subprocess.run(
                [
                    "ffmpeg", "-i", video_path,
                    "-vf", "fps=1/5,scale=480:-1",
                    "-frames:v", "4",
                    "-q:v", "3",
                    frames_pattern,
                ],
                capture_output=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg frame extraction timed out for %s", filename)

        frame_files = sorted(
            item for item in os.listdir(tmpdir)
            if item.startswith("frame") and item.endswith(".jpg")
        )

        frame_descriptions: list[str] = []
        for frame_file in frame_files:
            frame_path = os.path.join(tmpdir, frame_file)
            try:
                with open(frame_path, "rb") as handle:
                    frame_data = handle.read()
                desc = _describe_image(frame_data, frame_file, tier_config)
                if desc:
                    frame_descriptions.append(desc)
            except Exception as exc:
                logger.warning("Frame description failed for %s: %s", frame_file, exc)

        audio_path = os.path.join(tmpdir, "audio.wav")
        audio_transcript = ""
        try:
            subprocess.run(
                [
                    "ffmpeg", "-i", video_path,
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    audio_path,
                ],
                capture_output=True,
                timeout=60,
            )
            if os.path.exists(audio_path):
                with open(audio_path, "rb") as handle:
                    audio_data = handle.read()
                from interface.stt import transcribe as _transcribe

                audio_transcript = _transcribe(audio_data, filename="audio.wav")
        except Exception as exc:
            logger.warning(
                "Video audio extraction/transcription failed for %s: %s",
                filename,
                exc,
            )

    combined_visual = "\n".join(
        f"[Frame {index + 1}]: {desc}"
        for index, desc in enumerate(frame_descriptions)
    ) or f"[{filename}]: (video frames could not be described)"

    packet["visual_percept"] = {
        "timestamp": _time_mod.time(),
        "objects": [],
        "motion_detected": False,
        "motion_region": None,
        "scene_type": "user_attachment",
        "text_in_scene": [],
        "faces_detected": 0,
        "pose_summary": "",
        "description": combined_visual,
    }

    if audio_transcript and "auditory_percept" not in packet:
        packet["auditory_percept"] = {
            "timestamp": _time_mod.time(),
            "voice_present": True,
            "transcript": audio_transcript,
            "sound_class": "speech",
            "speaker_id": "unknown",
            "tone_signal": "",
        }
