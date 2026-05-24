"""Tests for discord_bot all-attachment handling."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock

# We test the helper in isolation without booting the full Discord client.
# Import the module; the client is not started by import.
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
    return asyncio.run(coro)


# Import after path setup
from interface.discord_bot import (  # noqa: E402
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
