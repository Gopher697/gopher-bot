"""Tests for Discord bridge binary document text extraction."""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# We test the Discord helper without starting the Discord client.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_attachment(filename: str, data: bytes, size: int | None = None) -> MagicMock:
    attachment = MagicMock()
    attachment.filename = filename
    attachment.size = size if size is not None else len(data)
    attachment.read = AsyncMock(return_value=data)
    return attachment


def _make_message(*attachments) -> MagicMock:
    message = MagicMock()
    message.attachments = list(attachments)
    return message


def run(coro):
    return asyncio.run(coro)


from interface.discord_bot import (  # noqa: E402
    _extract_document_text,
    _read_all_text_attachments,
)


def test_extract_pdf_returns_text():
    class FakePdf:
        pages = [MagicMock(extract_text=MagicMock(return_value="Hello PDF"))]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_pdfplumber = types.SimpleNamespace(open=MagicMock(return_value=FakePdf()))
    with patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
        result = _extract_document_text(b"fake", "doc.pdf")

    assert result == "Hello PDF"


def test_extract_pdf_missing_library_returns_none():
    with patch.dict(sys.modules, {"pdfplumber": None}):
        result = _extract_document_text(b"fake", "doc.pdf")

    assert result is None


def test_extract_docx_returns_paragraphs():
    fake_docx = types.SimpleNamespace(
        Document=MagicMock(
            return_value=types.SimpleNamespace(
                paragraphs=[
                    types.SimpleNamespace(text="Line one"),
                    types.SimpleNamespace(text="Line two"),
                ]
            )
        )
    )
    with patch.dict(sys.modules, {"docx": fake_docx}):
        result = _extract_document_text(b"fake", "report.docx")

    assert result is not None
    assert "Line one" in result
    assert "Line two" in result


def test_extract_docx_missing_library_returns_none():
    with patch.dict(sys.modules, {"docx": None}):
        result = _extract_document_text(b"fake", "report.docx")

    assert result is None


def test_extract_xlsx_returns_cell_values():
    fake_sheet = MagicMock()
    fake_sheet.title = "Scores"
    fake_sheet.iter_rows.return_value = [("Name", "Score")]
    fake_workbook = types.SimpleNamespace(worksheets=[fake_sheet])
    fake_openpyxl = types.SimpleNamespace(
        load_workbook=MagicMock(return_value=fake_workbook)
    )

    with patch.dict(sys.modules, {"openpyxl": fake_openpyxl}):
        result = _extract_document_text(b"fake", "data.xlsx")

    assert result is not None
    assert "[Sheet: Scores]" in result
    assert "Name" in result
    assert "Score" in result


def test_extract_xlsx_missing_library_returns_none():
    with patch.dict(sys.modules, {"openpyxl": None}):
        result = _extract_document_text(b"fake", "data.xlsx")

    assert result is None


def test_extract_pptx_returns_slide_text():
    fake_pptx = types.ModuleType("pptx")
    fake_pptx.Presentation = MagicMock(
        return_value=types.SimpleNamespace(
            slides=[
                types.SimpleNamespace(
                    shapes=[types.SimpleNamespace(text="Slide title here")]
                )
            ]
        )
    )

    with patch.dict(sys.modules, {"pptx": fake_pptx}):
        result = _extract_document_text(b"fake", "deck.pptx")

    assert result is not None
    assert "Slide title here" in result


def test_extract_pptx_missing_library_returns_none():
    with patch.dict(sys.modules, {"pptx": None}):
        result = _extract_document_text(b"fake", "deck.pptx")

    assert result is None


def test_extract_rtf_strips_tags():
    result = _extract_document_text(b"{\\rtf1 Hello world}", "notes.rtf")

    assert result is not None
    assert "Hello" in result
    assert "world" in result


def test_extract_unsupported_format_returns_none():
    result = _extract_document_text(b"binary", "archive.zip")

    assert result is None


def test_read_all_text_attachments_parses_pdf():
    message = _make_message(_make_attachment("report.pdf", b"\xff\xfe\x00fake"))

    with patch(
        "interface.discord_bot._extract_document_text",
        return_value="Extracted PDF text",
    ):
        combined_text, structured = run(_read_all_text_attachments(message))

    assert "Extracted PDF text" in combined_text
    assert structured == [
        {"filename": "report.pdf", "content": "Extracted PDF text"}
    ]


def test_read_all_text_attachments_binary_fallback():
    message = _make_message(_make_attachment("data.bin", b"\xff\xfe\x00binary"))

    with patch("interface.discord_bot._extract_document_text", return_value=None):
        combined_text, structured = run(_read_all_text_attachments(message))

    assert "format not supported" in combined_text
    assert structured == []
