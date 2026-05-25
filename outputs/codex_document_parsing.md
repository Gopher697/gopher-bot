# Codex Task: Parse all common document formats in the Discord bridge

## Background

`_read_all_text_attachments()` in `interface/discord_bot.py` currently downloads
any non-image/audio/video attachment and tries to decode it as UTF-8. This works
for plain text files (.txt, .md, .csv, .json, .py, .log, etc.). For binary document
formats (PDF, Word, Excel, PowerPoint) it falls back to:

    (binary file -- content cannot be displayed)

This means sending a PDF or spreadsheet to the bot produces no usable content.

## Goal

When `_read_all_text_attachments()` encounters a file it cannot decode as UTF-8,
try format-specific parsers before giving up. Return extracted text so the bot can
read the document. All parsers must degrade gracefully if the library is not installed.

## Changes required

---

### 1. `requirements.txt` — add document parsing libraries

Append these four lines:

```
# Document parsing
pdfplumber>=0.10
python-docx>=1.0
openpyxl>=3.1
python-pptx>=0.6
```

---

### 2. `interface/discord_bot.py` — add `_extract_document_text()` helper

Add this function immediately before `_read_all_text_attachments()`:

```python
def _extract_document_text(data: bytes, filename: str) -> str | None:
    """
    Attempt to extract readable text from a binary document.

    Tries format-specific parsers based on file extension. Returns the extracted
    text string (possibly empty) on success, or None if the format is unsupported
    or the required library is not installed.

    Supported formats:
        .pdf            — pdfplumber
        .docx           — python-docx
        .xlsx / .xls    — openpyxl
        .pptx           — python-pptx
        .csv            — decoded as UTF-8 (should not reach here, but handled)
        .rtf            — basic tag stripping (no extra dependency)
    """
    suffix = Path(filename).suffix.lower()

    # --- PDF ---
    if suffix == ".pdf":
        try:
            import pdfplumber
            from io import BytesIO as _BytesIO
            text_parts: list[str] = []
            with pdfplumber.open(_BytesIO(data)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        text_parts.append(page_text.strip())
            return "\n\n".join(text_parts) if text_parts else ""
        except ImportError:
            print("[discord] pdfplumber not installed; cannot parse PDF")
            return None
        except Exception as exc:
            print(f"[discord] PDF parse failed for {filename}: {exc}")
            return None

    # --- Word (.docx) ---
    if suffix == ".docx":
        try:
            import docx
            from io import BytesIO as _BytesIO
            doc = docx.Document(_BytesIO(data))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)
        except ImportError:
            print("[discord] python-docx not installed; cannot parse .docx")
            return None
        except Exception as exc:
            print(f"[discord] DOCX parse failed for {filename}: {exc}")
            return None

    # --- Excel (.xlsx / .xls) ---
    if suffix in {".xlsx", ".xls"}:
        try:
            import openpyxl
            from io import BytesIO as _BytesIO
            wb = openpyxl.load_workbook(_BytesIO(data), read_only=True, data_only=True)
            rows: list[str] = []
            for sheet in wb.worksheets:
                rows.append(f"[Sheet: {sheet.title}]")
                for row in sheet.iter_rows(values_only=True):
                    cells = [str(cell) if cell is not None else "" for cell in row]
                    if any(c.strip() for c in cells):
                        rows.append("\t".join(cells))
            return "\n".join(rows)
        except ImportError:
            print("[discord] openpyxl not installed; cannot parse .xlsx")
            return None
        except Exception as exc:
            print(f"[discord] Excel parse failed for {filename}: {exc}")
            return None

    # --- PowerPoint (.pptx) ---
    if suffix == ".pptx":
        try:
            from pptx import Presentation
            from io import BytesIO as _BytesIO
            prs = Presentation(_BytesIO(data))
            slides: list[str] = []
            for i, slide in enumerate(prs.slides, start=1):
                texts = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        texts.append(shape.text.strip())
                if texts:
                    slides.append(f"[Slide {i}]\n" + "\n".join(texts))
            return "\n\n".join(slides)
        except ImportError:
            print("[discord] python-pptx not installed; cannot parse .pptx")
            return None
        except Exception as exc:
            print(f"[discord] PPTX parse failed for {filename}: {exc}")
            return None

    # --- RTF (basic tag strip, no extra dependency) ---
    if suffix == ".rtf":
        try:
            import re as _re
            text = data.decode("latin-1", errors="replace")
            # Strip RTF control words and groups
            text = _re.sub(r"\\[a-z]+[-\d]*\s?", " ", text)
            text = _re.sub(r"[{}\\]", "", text)
            text = " ".join(text.split())
            return text
        except Exception as exc:
            print(f"[discord] RTF strip failed for {filename}: {exc}")
            return None

    # Unsupported binary format
    return None
```

#### Update `_read_all_text_attachments()` to call it

Replace the `except UnicodeDecodeError` block:

```python
        except UnicodeDecodeError:
            # Binary file — try format-specific parser before giving up
            extracted = _extract_document_text(data, attachment.filename or "")
            if extracted is not None:
                label = f"[{attachment.filename}]:\n{extracted}" if extracted.strip() else f"[{attachment.filename}]: (document contained no extractable text)"
                parts.append(label)
                if extracted.strip():
                    structured.append({"filename": attachment.filename, "content": extracted})
            else:
                parts.append(
                    f"[{attachment.filename}]: (binary file — format not supported for text extraction)"
                )
```

---

### 3. `tests/test_document_parsing.py` — new test file

Create `tests/test_document_parsing.py`. No real files needed — build minimal
in-memory documents using the same libraries.

```
test_extract_pdf_returns_text:
    Build a minimal PDF in memory using pdfplumber/reportlab or a known byte
    sequence. OR: patch pdfplumber.open to return a mock with one page whose
    extract_text() returns "Hello PDF". Call _extract_document_text(data, "doc.pdf").
    Assert result == "Hello PDF".

test_extract_pdf_missing_library_returns_none:
    Patch the pdfplumber import to raise ImportError.
    Call _extract_document_text(b"fake", "doc.pdf").
    Assert result is None.

test_extract_docx_returns_paragraphs:
    Patch docx.Document to return a mock with two paragraphs ("Line one", "Line two").
    Call _extract_document_text(b"fake", "report.docx").
    Assert "Line one" in result and "Line two" in result.

test_extract_docx_missing_library_returns_none:
    Patch docx import to raise ImportError.
    Assert _extract_document_text(b"fake", "report.docx") is None.

test_extract_xlsx_returns_cell_values:
    Patch openpyxl.load_workbook to return a mock workbook with one sheet
    containing one row: ("Name", "Score").
    Call _extract_document_text(b"fake", "data.xlsx").
    Assert "Name" in result and "Score" in result.

test_extract_xlsx_missing_library_returns_none:
    Patch openpyxl import to raise ImportError.
    Assert _extract_document_text(b"fake", "data.xlsx") is None.

test_extract_pptx_returns_slide_text:
    Patch pptx.Presentation to return a mock with one slide containing
    one shape whose .text is "Slide title here".
    Call _extract_document_text(b"fake", "deck.pptx").
    Assert "Slide title here" in result.

test_extract_pptx_missing_library_returns_none:
    Patch pptx import to raise ImportError.
    Assert _extract_document_text(b"fake", "deck.pptx") is None.

test_extract_rtf_strips_tags:
    Provide a minimal RTF bytestring like b"{\\rtf1 Hello world}".
    Call _extract_document_text(data, "notes.rtf").
    Assert "Hello" in result and "world" in result.

test_extract_unsupported_format_returns_none:
    Call _extract_document_text(b"binary", "archive.zip").
    Assert result is None.

test_read_all_text_attachments_parses_pdf:
    Build a mock Discord message with one attachment: filename="report.pdf",
    size=1000, data=b"fake".
    Patch _extract_document_text to return "Extracted PDF text".
    Call _read_all_text_attachments(message) (using asyncio.run or pytest-asyncio).
    Assert "Extracted PDF text" in the combined_text result.
    Assert structured list contains {"filename": "report.pdf", "content": "Extracted PDF text"}.

test_read_all_text_attachments_binary_fallback:
    Patch _extract_document_text to return None (unsupported format).
    Build mock attachment with filename="data.bin", binary data.
    Assert result contains "format not supported".
```

---

### 4. Install the new dependencies

After making the code changes, run:

```
pip install pdfplumber python-docx openpyxl python-pptx --break-system-packages
```

---

## What NOT to change

- Image, audio, and video attachment handlers — already correct.
- `coordinators/sensory.py` — text attachments already flow through unchanged.
- `world_models/config.py` — no config changes needed.

## Acceptance criteria

```
pip install pdfplumber python-docx openpyxl python-pptx --break-system-packages
pytest tests/test_document_parsing.py -v   # all tests pass
pytest --basetemp .tmp/pytest-tmp -q       # full suite still passes
```

## Commit instructions

```
git add interface/discord_bot.py requirements.txt tests/test_document_parsing.py
git reset HEAD world_models/config.py
git commit -m "feat: parse PDF, Word, Excel, PowerPoint and RTF attachments in Discord bridge

- Add _extract_document_text() with pdfplumber, python-docx, openpyxl, python-pptx
- RTF handled with lightweight tag stripping (no extra dependency)
- All parsers degrade gracefully if library not installed
- Unsupported binary formats get a clear 'format not supported' note
- requirements.txt updated with four new document parsing deps
- 1000+ tests still passing"
git push origin main
```

## Security reminder

Do not stage or commit `world_models/config.py`. Run `git status` before committing.
