# Codex Task — Discord bridge: handle all attachment types

## Context

`interface/discord_bot.py` currently splits attachment handling into two narrow functions:

- `_read_text_attachments()` — only processes `.txt` files. All other text formats
  (`.md`, `.py`, `.json`, `.yaml`, `.csv`, etc.) are silently dropped.
- `_download_image_attachments()` — correctly handles image formats via the Sensory
  vision pipeline (Task 68, commit b2b683f). **Do not touch this function.**

The result: a user sending `whitepaper.md` gets no response because the bridge drops
the attachment entirely. The fix is to replace `_read_text_attachments` with a
function that attempts to read *any* attachment that isn't already claimed by the
image pipeline — try UTF-8 decode, inject if it works, leave a note if it doesn't.

**Only `interface/discord_bot.py` changes.** No other files.

---

## Security invariant

Run `git status` before committing. If `world_models/config.py` appears, STOP.

---

## Changes to `interface/discord_bot.py`

### 1. Replace `_read_text_attachments` with `_read_all_text_attachments`

Delete the existing `_read_text_attachments` function entirely and replace it with:

```python
async def _read_all_text_attachments(message: discord.Message) -> str:
    """
    Read all non-image attachments and return their combined content as text.

    For each attachment not in IMAGE_EXTENSIONS:
    - If the file decodes as UTF-8: inject the full content under a filename header.
    - If the file is binary (decode fails): inject a note so the bot knows
      something was sent even if it cannot read it.
    - Files over MAX_ATTACHMENT_BYTES are skipped with a console note.
    """
    parts: list[str] = []
    for attachment in message.attachments:
        suffix = Path(attachment.filename or "").suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            continue  # handled by _download_image_attachments
        if attachment.size and attachment.size > MAX_ATTACHMENT_BYTES:
            print(f"[discord] Skipping oversized attachment: {attachment.filename}")
            parts.append(f"[{attachment.filename}]: (file too large to transmit)")
            continue
        try:
            data = await attachment.read()
        except Exception as exc:
            print(f"[discord] Failed to download {attachment.filename}: {exc}")
            parts.append(f"[{attachment.filename}]: (download failed)")
            continue
        try:
            text = data.decode("utf-8", errors="strict")
            parts.append(f"[{attachment.filename}]:\n{text}")
        except UnicodeDecodeError:
            # Binary file — note it so the bot is aware something was sent
            parts.append(
                f"[{attachment.filename}]: (binary file — content cannot be displayed)"
            )
    return "\n\n".join(parts)
```

### 2. Update the call site in `on_message`

Replace:
```python
attachment_text = await _read_text_attachments(message)
```
With:
```python
attachment_text = await _read_all_text_attachments(message)
```

### 3. Fix the empty-content guard

The current guard:
```python
if not content.strip():
    return
```

Replace with:
```python
if not content.strip() and not image_attachments:
    return
```

This ensures image-only messages (no text body) still route through Awareness instead
of being silently dropped.

---

## Tests — `tests/test_discord_all_attachments.py`

Create this new test file:

```python
"""Tests for discord_bot all-attachment handling."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# We test the helper in isolation without booting the full Discord client.
# Import the module; the client is not started by import.
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_attachment(filename: str, data: bytes, size: int | None = None) -> MagicMock:
    att = MagicMock()
    att.filename = filename
    att.size = size if size is not None else len(data)
    att.read = AsyncMock(return_value=data)
    return att


def _make_message(*attachments) -> MagicMock:
    msg = MagicMock()
    msg.attachments = list(attachments)
    return msg


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# Import after path setup
from interface.discord_bot import (
    IMAGE_EXTENSIONS,
    MAX_ATTACHMENT_BYTES,
    _read_all_text_attachments,
)


def test_md_file_is_read():
    content = b"# Hello\nThis is a whitepaper."
    msg = _make_message(_make_attachment("whitepaper.md", content))
    result = run(_read_all_text_attachments(msg))
    assert "whitepaper.md" in result
    assert "Hello" in result


def test_txt_file_is_read():
    msg = _make_message(_make_attachment("notes.txt", b"some notes"))
    result = run(_read_all_text_attachments(msg))
    assert "notes.txt" in result
    assert "some notes" in result


def test_py_file_is_read():
    msg = _make_message(_make_attachment("script.py", b"print('hi')"))
    result = run(_read_all_text_attachments(msg))
    assert "script.py" in result
    assert "print" in result


def test_json_file_is_read():
    msg = _make_message(_make_attachment("data.json", b'{"key": "value"}'))
    result = run(_read_all_text_attachments(msg))
    assert "data.json" in result


def test_image_attachment_is_skipped():
    """Image attachments are handled by _download_image_attachments, not here."""
    msg = _make_message(_make_attachment("photo.png", b"\x89PNG fake"))
    result = run(_read_all_text_attachments(msg))
    assert result == ""


def test_binary_file_leaves_note():
    msg = _make_message(_make_attachment("archive.zip", b"\x50\x4b\x03\x04binary"))
    result = run(_read_all_text_attachments(msg))
    assert "archive.zip" in result
    assert "binary" in result.lower() or "cannot" in result.lower()


def test_oversized_attachment_skipped():
    att = _make_attachment("huge.md", b"x", size=MAX_ATTACHMENT_BYTES + 1)
    msg = _make_message(att)
    result = run(_read_all_text_attachments(msg))
    assert "too large" in result or "huge.md" in result
    att.read.assert_not_called()


def test_multiple_attachments_combined():
    msg = _make_message(
        _make_attachment("a.md", b"Alpha"),
        _make_attachment("b.txt", b"Beta"),
    )
    result = run(_read_all_text_attachments(msg))
    assert "a.md" in result
    assert "b.txt" in result
    assert "Alpha" in result
    assert "Beta" in result


def test_empty_attachments_returns_empty_string():
    msg = _make_message()
    result = run(_read_all_text_attachments(msg))
    assert result == ""
```

---

## Verification

```
pytest tests/test_discord_all_attachments.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_task69 -v
```

Confirm `world_models/config.py` is not staged:
```
git status
```

Commit:
```
git commit -m "feat: Discord bridge reads all attachment types — md, py, json, binary note (Task 69)"
```
