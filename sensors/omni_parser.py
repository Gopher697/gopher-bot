"""Lazy OmniParser wrapper for GUI element location."""
from __future__ import annotations

import importlib
import json
import logging
from difflib import SequenceMatcher
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

MODEL_ID = "microsoft/OmniParser-v2.0"
MATCH_THRESHOLD = 0.50

_MODEL_CACHE: dict[str, Any] = {
    "loaded": False,
    "processor": None,
    "model": None,
    "last_error": None,
}


def _get_model():
    """Lazy-load OmniParser. Returns (processor, model) or (None, None)."""
    if _MODEL_CACHE["loaded"]:
        return _MODEL_CACHE["processor"], _MODEL_CACHE["model"]

    _MODEL_CACHE["loaded"] = True
    try:
        transformers = importlib.import_module("transformers")
        torch = importlib.import_module("torch")
        processor = transformers.AutoProcessor.from_pretrained(
            MODEL_ID,
            trust_remote_code=True,
        )
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        try:
            model = transformers.AutoModelForCausalLM.from_pretrained(
                MODEL_ID,
                trust_remote_code=True,
                torch_dtype=dtype,
            )
        except Exception:
            model = transformers.AutoModel.from_pretrained(
                MODEL_ID,
                trust_remote_code=True,
                dtype="auto",
            )
        if torch.cuda.is_available():
            model = model.cuda()
        model.eval()
        _MODEL_CACHE.update(
            {
                "processor": processor,
                "model": model,
                "last_error": None,
            }
        )
        return processor, model
    except Exception as exc:
        _MODEL_CACHE["last_error"] = str(exc)
        logger.warning("OmniParser unavailable: %s", exc)
        return None, None


def last_error() -> str | None:
    """Return the most recent OmniParser availability/inference error."""
    error = _MODEL_CACHE.get("last_error")
    return str(error) if error else None


def locate_element(image_bytes: bytes, description: str) -> dict | None:
    """
    Locate the best matching GUI element in a PNG screenshot.

    Returns {"label": str, "bbox": [x1, y1, x2, y2], "center": [cx, cy]} or
    None if OmniParser is unavailable, inference fails, or no match is found.
    """
    query = str(description or "").strip()
    if not image_bytes or not query:
        return None

    processor, model = _get_model()
    if processor is None or model is None:
        return None

    image, size = _load_image(image_bytes)
    if image is None:
        return None

    try:
        raw_output = _run_inference(processor, model, image)
        elements = _extract_elements(raw_output, size)
        _MODEL_CACHE["last_error"] = None
        return _best_match(elements, query)
    except Exception as exc:
        _MODEL_CACHE["last_error"] = str(exc)
        logger.warning("OmniParser inference failed: %s", exc)
        return None


def _load_image(image_bytes: bytes):
    try:
        from PIL import Image

        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        return image, image.size
    except Exception as exc:
        _MODEL_CACHE["last_error"] = str(exc)
        logger.warning("OmniParser image load failed: %s", exc)
        return None, (0, 0)


def _run_inference(processor: Any, model: Any, image: Any) -> Any:
    if hasattr(model, "parse"):
        return model.parse(image)
    if hasattr(processor, "parse"):
        return processor.parse(image)

    if callable(processor) and hasattr(model, "generate"):
        inputs = processor(images=image, return_tensors="pt")
        try:
            device = next(model.parameters()).device
            inputs = {
                key: value.to(device) if hasattr(value, "to") else value
                for key, value in inputs.items()
            }
        except Exception:
            pass
        output = model.generate(**inputs, max_new_tokens=1024)
        if hasattr(processor, "batch_decode"):
            decoded = processor.batch_decode(output, skip_special_tokens=True)
            return decoded[0] if decoded else ""
        if hasattr(processor, "decode"):
            return processor.decode(output[0], skip_special_tokens=True)
        return output

    if callable(model):
        return model(image)
    return None


def _extract_elements(raw_output: Any, image_size: tuple[int, int]) -> list[dict]:
    payload = _loads_payload(raw_output)
    elements: list[dict] = []
    _collect_elements(payload, image_size, elements)
    return elements


def _loads_payload(raw_output: Any) -> Any:
    if isinstance(raw_output, str):
        text = raw_output.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start_candidates = [idx for idx in (text.find("["), text.find("{")) if idx >= 0]
            if not start_candidates:
                return raw_output
            start = min(start_candidates)
            end = max(text.rfind("]"), text.rfind("}"))
            if end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    return raw_output
            return raw_output
    if hasattr(raw_output, "to_dict"):
        return raw_output.to_dict()
    return raw_output


def _collect_elements(payload: Any, image_size: tuple[int, int], out: list[dict]) -> None:
    if isinstance(payload, list):
        for item in payload:
            _collect_elements(item, image_size, out)
        return

    if not isinstance(payload, dict):
        return

    label = _extract_label(payload)
    bbox = _extract_bbox(payload, image_size)
    if label and bbox:
        center = [
            int(round((bbox[0] + bbox[2]) / 2)),
            int(round((bbox[1] + bbox[3]) / 2)),
        ]
        out.append({"label": label, "bbox": bbox, "center": center})

    for value in payload.values():
        if isinstance(value, (list, dict)):
            _collect_elements(value, image_size, out)


def _extract_label(element: dict) -> str:
    for key in ("label", "content", "text", "caption", "description", "name"):
        value = element.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = element.get("type")
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _extract_bbox(element: dict, image_size: tuple[int, int]) -> list[int] | None:
    raw_bbox = None
    for key in ("bbox", "box", "coordinates", "rect", "region"):
        if key in element:
            raw_bbox = element[key]
            break

    if isinstance(raw_bbox, dict):
        if all(key in raw_bbox for key in ("x1", "y1", "x2", "y2")):
            values = [raw_bbox["x1"], raw_bbox["y1"], raw_bbox["x2"], raw_bbox["y2"]]
        elif all(key in raw_bbox for key in ("x", "y", "w", "h")):
            x = float(raw_bbox["x"])
            y = float(raw_bbox["y"])
            values = [x, y, x + float(raw_bbox["w"]), y + float(raw_bbox["h"])]
        else:
            return None
    elif isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
        values = list(raw_bbox[:4])
    else:
        return None

    try:
        coords = [float(value) for value in values]
    except (TypeError, ValueError):
        return None

    width, height = image_size
    if width > 0 and height > 0 and all(0.0 <= value <= 1.0 for value in coords):
        coords = [coords[0] * width, coords[1] * height, coords[2] * width, coords[3] * height]

    x1, y1, x2, y2 = coords
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]


def _best_match(elements: list[dict], description: str) -> dict | None:
    query = description.strip().lower()
    if not query:
        return None

    for element in elements:
        label = str(element.get("label") or "")
        label_lower = label.lower()
        if query in label_lower or label_lower in query:
            return element

    best: tuple[float, dict | None] = (0.0, None)
    for element in elements:
        label = str(element.get("label") or "")
        score = SequenceMatcher(None, query, label.lower()).ratio()
        if score > best[0]:
            best = (score, element)

    return best[1] if best[0] >= MATCH_THRESHOLD else None
