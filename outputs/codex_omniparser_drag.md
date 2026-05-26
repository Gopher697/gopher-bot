# Codex Task: OmniParser element detection + drag primitives

Add general-purpose screen element location (via OmniParser) and drag
execution (via pyautogui) to Hands. This is the foundation for any task
that requires the bot to interact with on-screen UI — chess boards, game
windows, file managers, sliders, anything.

---

## Context

`coordinators/hands.py` already has:
- `screenshot` (whitelist) — captures screen via mss, returns base64 PNG
- `click_label` (greylist) — clicks elements from VisionSensor's latest percept
- `click_bbox` (greylist) — clicks by explicit bbox coordinates
- `mouse_move`, `left_click`, `right_click` — basic pyautogui primitives

What's missing:
- **Drag** — no drag primitive exists at all
- **On-demand element location** — `click_label` only works from the cached
  VisionSensor percept (background frame, possibly stale). There's no way to
  capture a fresh frame and ask "where is X?" at action time.
- **GUI-aware detection** — YOLO is trained on real-world objects, not UI
  elements. OmniParser (Microsoft's model) is trained on GUI screenshots and
  returns bounding boxes for buttons, icons, and interactive regions.

---

## Changes required

### 1. `sensors/omni_parser.py` — new file

Lazy-loading wrapper around OmniParser. Expose a single function:

```python
def locate_element(
    image_bytes: bytes,
    description: str,
) -> dict | None:
```

- Takes a PNG screenshot (bytes) and a natural-language description.
- Runs OmniParser inference on the image to get all detected elements with
  bounding boxes and labels.
- Finds the best-matching element by comparing `description` against each
  element's label using case-insensitive substring match first, then
  falls back to difflib `SequenceMatcher` ratio (threshold 0.5).
- Returns `{"label": str, "bbox": [x1, y1, x2, y2], "center": [cx, cy]}`
  or `None` if no match found or model unavailable.

OmniParser loading:

```python
import importlib

def _get_model():
    """Lazy-load OmniParser. Returns (processor, model) or (None, None)."""
    try:
        from transformers import AutoProcessor, AutoModelForCausalLM
        import torch
        MODEL_ID = "microsoft/OmniParser-v2.0"
        processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            trust_remote_code=True,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )
        if torch.cuda.is_available():
            model = model.cuda()
        model.eval()
        return processor, model
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("OmniParser unavailable: %s", exc)
        return None, None
```

Cache the loaded model in a module-level `_MODEL_CACHE` dict so it's only
loaded once per process.

OmniParser returns elements as a list of dicts. Each element has at minimum
`bbox` (normalized 0–1 coordinates or absolute pixels — check which format
the model version uses and convert to absolute pixels if needed) and a text
`label` or `content` field. Consult the model card at
`https://huggingface.co/microsoft/OmniParser-v2.0` for the exact output
schema and convert accordingly.

If OmniParser is unavailable (model not downloaded, transformers not
installed, CUDA OOM), `locate_element` returns `None` with a warning log
and does NOT raise. Graceful degradation is mandatory.

### 2. `coordinators/hands.py` — three new handlers

#### `_handle_locate_on_screen(args)` → str (JSON)

```
args: {"description": str, "monitor": int (optional, default 0)}
```

1. Capture a fresh screenshot via mss (monitor index from args, default 0 =
   all monitors combined).
2. Call `sensors.omni_parser.locate_element(png_bytes, description)`.
3. Return JSON string:
   - On success: `{"found": true, "label": "...", "bbox": [...], "center": [cx, cy]}`
   - On miss: `{"found": false, "description": "..."}`
   - On OmniParser unavailable: `{"found": false, "error": "OmniParser unavailable"}`

Policy: **whitelist** — read-only perception, no side effects.

#### `_handle_drag_to(args)` → str

```
args: {
    "x1": int, "y1": int,   # drag start (pixels)
    "x2": int, "y2": int,   # drag end (pixels)
    "duration": float        # optional, default 0.4 seconds
}
```

```python
import pyautogui
pyautogui.FAILSAFE = False
duration = float(args.get("duration", 0.4))
pyautogui.moveTo(x1, y1, duration=0.1)
pyautogui.dragTo(x2, y2, duration=duration, button="left")
return f"Dragged ({x1},{y1}) → ({x2},{y2}) over {duration}s"
```

If pyautogui is not installed, return an error string (do not raise).

Policy: **greylist** — modifies real-world state (moves UI elements).

#### `_handle_drag_element(args)` → str

```
args: {
    "source": str,       # description of element to drag from
    "target": str,       # description of element to drag to
    "monitor": int,      # optional
    "duration": float    # optional, default 0.4
}
```

Convenience wrapper:
1. Capture fresh screenshot (mss, same monitor logic as locate_on_screen).
2. Call `locate_element(png_bytes, source)` → source result.
3. If not found: return error string naming the missing element.
4. Call `locate_element(png_bytes, target)` → target result.
5. If not found: return error string naming the missing element.
6. Extract center coordinates from both results.
7. Call `_handle_drag_to` with those coordinates and the duration arg.
8. Return composite result string.

Note: both `locate_element` calls use the same screenshot (taken once at
step 1). Do not capture a second screenshot between the two calls.

Policy: **greylist**.

### 3. `coordinators/hands_policy.py` — update taxonomy

Add to `WHITELIST_ACTIONS`:
```python
"locate_on_screen",
```

Add to `GREYLIST_ACTIONS`:
```python
"drag_to",
"drag_element",
```

### 4. `coordinators/hands.py` — register handlers

In `_WHITELIST_HANDLERS`:
```python
"locate_on_screen": _handle_locate_on_screen,
```

Add a `_GREYLIST_HANDLERS` dict (parallel to `_WHITELIST_HANDLERS`) and
register greylist handlers there, OR simply add the new handlers to
`_WHITELIST_HANDLERS` and let the policy layer gate execution — whichever
pattern is cleaner given the existing dispatch architecture. Do not change
the dispatch logic beyond what's necessary.

### 5. `pyproject.toml` — optional extras

Add an `[omniparser]` extra (or add to the existing `[vision]` extra):
```toml
omniparser = [
    "transformers>=4.40",
    "accelerate>=0.27",
]
```

These are likely already installed via ultralytics/torch. Only add if not
already present in the dependency list.

---

## Tests

Add `tests/test_hands_drag.py`. Cover:

1. **`locate_on_screen` — OmniParser unavailable**: mock
   `sensors.omni_parser.locate_element` to return `None`. Call
   `_handle_locate_on_screen({"description": "submit button"})`. Assert
   result is valid JSON with `"found": false`.

2. **`locate_on_screen` — element found**: mock `locate_element` to return
   `{"label": "OK", "bbox": [100, 200, 150, 220], "center": [125, 210]}`.
   Mock mss. Assert result JSON has `"found": true` and correct center.

3. **`drag_to` — pyautogui present**: mock pyautogui. Assert
   `_handle_drag_to({"x1": 10, "y1": 20, "x2": 30, "y2": 40})` calls
   `dragTo(30, 40, ...)` and returns a non-empty string.

4. **`drag_to` — pyautogui absent**: patch `pyautogui` to `None` in
   `coordinators.hands`. Assert result is an error string (not an exception).

5. **`drag_element` — source not found**: mock `locate_element` to return
   `None`. Assert result names the missing source element.

6. **`drag_element` — target not found**: mock `locate_element` to return
   a hit for source and `None` for target. Assert result names the missing
   target element.

7. **`drag_element` — both found**: mock both `locate_element` calls and
   pyautogui. Assert `dragTo` is called with target center coordinates.

8. **Policy — `locate_on_screen` is whitelisted**: call
   `classify_action("locate_on_screen", {})`. Assert `policy_class ==
   "whitelist"`.

9. **Policy — `drag_to` is greylisted**: call
   `classify_action("drag_to", {})`. Assert `policy_class == "greylist"`.

10. **Policy — `drag_element` is greylisted**: same pattern.

---

## Security note

OmniParser model weights (~1–2 GB) will auto-download to the HuggingFace
cache on first use (`~/.cache/huggingface/`). Add `**/.cache/huggingface/`
to `.gitignore` if not already covered by an existing pattern. Do NOT
commit model weights.

---

## Commit instructions

```
git status
# Verify world_models/config.py is NOT staged. If it appears, run:
#   git reset HEAD world_models/config.py
# before committing.

git add sensors/omni_parser.py coordinators/hands.py coordinators/hands_policy.py pyproject.toml tests/test_hands_drag.py
git commit -m "feat: OmniParser element detection + drag primitives

- sensors/omni_parser.py: lazy-load OmniParser-v2.0, locate_element()
  returns best-match element bbox/center from a screenshot
- hands: locate_on_screen (whitelist), drag_to + drag_element (greylist)
- hands_policy: taxonomy updated for new action types
- 10 new tests"
git push origin main
```
