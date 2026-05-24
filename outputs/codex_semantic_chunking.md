# Codex Task — Semantic chunking for document ingestion

## Context and Why This Matters

`Memory.ingest_attachments()` uses `_chunk_text()` to split documents before storing
them as Observation nodes. The current implementation splits on fixed character counts
(1500 chars), preferring the nearest newline. This means a document like a whitepaper
with numbered sections (§8.2, §13.8) gets sliced mid-section: the section header ends
up in one chunk and the body in another. When the bot later tries to retrieve "Section
8.2, Hands Coordinator," neither chunk is a clean unit — the header has no body and
the body has no header. Retrieval fails even when the content is in the graph.

The fix: replace `_chunk_text()` with a structure-aware chunker that:
1. Splits first on document structure (markdown headers, numbered sections, paragraph breaks)
2. Only falls back to character-based splitting within a structural section if that
   section exceeds `INGEST_CHUNK_SIZE`
3. Preserves the section header at the top of each chunk so retrieval has full context

**Files that change:**
1. `coordinators/memory.py` — replace `_chunk_text()` with `_semantic_chunk_text()`
   and a `_char_chunk()` fallback helper; update `ingest_attachments()` call site

Do not modify `world_models/graph.py`, `world_models/config.py`, or any other file.

---

## Security invariant

Run `git status` before committing. If `world_models/config.py` appears, STOP.

---

## Changes to `coordinators/memory.py`

### 1. Replace `_chunk_text()` with `_semantic_chunk_text()` and `_char_chunk()`

Delete the existing `_chunk_text` function entirely and replace it with:

```python
import re as _re


def _char_chunk(text: str, chunk_size: int) -> list[str]:
    """
    Split text into chunks of at most chunk_size characters, preferring
    to break at newline boundaries. Used as a fallback when a structural
    section is too large to store as a single chunk.
    """
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start:
                end = newline
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


# Patterns that mark the start of a new structural section
_SECTION_BOUNDARY = _re.compile(
    r"^(?:"
    r"#{1,6}\s"           # Markdown headers: # H1 through ###### H6
    r"|§\s*[\d.]+"        # Section symbols: §8.2, § 13
    r"|\d+(?:\.\d+)+\s"   # Numbered sections: 8.2 Heading, 13.8.1 Sub
    r")",
    _re.MULTILINE,
)


def _semantic_chunk_text(
    text: str,
    chunk_size: int,
    max_chunks: int,
) -> list[str]:
    """
    Split text into semantically coherent chunks by respecting document structure.

    Strategy:
    1. Find all structural section boundaries (markdown headers, numbered sections,
       section symbols like §8.2).
    2. Each section from one boundary to the next becomes a chunk candidate.
    3. If a section candidate exceeds chunk_size characters, split it further
       using paragraph breaks (double newline), then fall back to _char_chunk().
    4. If no structural boundaries are found, fall back to paragraph splitting,
       then to _char_chunk().

    The section header is always included at the top of each sub-chunk produced
    by splitting an oversized section, so retrieval context is preserved.

    Args:
        text:       Input text to chunk.
        chunk_size: Maximum characters per chunk.
        max_chunks: Maximum number of chunks to produce.

    Returns:
        List of non-empty chunk strings, at most max_chunks long.
    """
    text = text.strip()
    if not text:
        return []

    # Find structural boundaries
    boundaries = [m.start() for m in _SECTION_BOUNDARY.finditer(text)]

    if boundaries:
        # Build raw sections: from each boundary to the next
        raw_sections: list[str] = []
        for i, start in enumerate(boundaries):
            end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
            section = text[start:end].strip()
            if section:
                raw_sections.append(section)
        # Include any leading text before the first boundary
        if boundaries[0] > 0:
            preamble = text[:boundaries[0]].strip()
            if preamble:
                raw_sections.insert(0, preamble)
    else:
        # No structural boundaries — treat the whole text as one section
        raw_sections = [text]

    chunks: list[str] = []
    for section in raw_sections:
        if len(chunks) >= max_chunks:
            break
        if len(section) <= chunk_size:
            chunks.append(section)
        else:
            # Section is too large — try paragraph splitting first
            # Extract header line (first line) to prepend to sub-chunks
            lines = section.split("\n", 1)
            header = lines[0].strip() if len(lines) > 1 else ""
            body = lines[1] if len(lines) > 1 else section

            paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
            current: list[str] = [header] if header else []
            current_len = len(header)

            for para in paragraphs:
                if len(chunks) >= max_chunks:
                    break
                if current_len + len(para) + 2 <= chunk_size:
                    current.append(para)
                    current_len += len(para) + 2
                else:
                    # Flush current accumulation
                    if current:
                        chunks.append("\n\n".join(current).strip())
                    if len(chunks) >= max_chunks:
                        break
                    if len(para) <= chunk_size:
                        # Start next accumulation with header context
                        current = [header, para] if header else [para]
                        current_len = len(header) + len(para) + 2
                    else:
                        # Paragraph itself is too large — char chunk it
                        for sub in _char_chunk(para, chunk_size):
                            if len(chunks) >= max_chunks:
                                break
                            prefix = f"{header}\n\n" if header else ""
                            chunks.append((prefix + sub).strip())
                        current = [header] if header else []
                        current_len = len(header)

            if current and len(chunks) < max_chunks:
                flushed = "\n\n".join(current).strip()
                if flushed and flushed != header:  # don't store header-only chunks
                    chunks.append(flushed)

    return [c for c in chunks if c][:max_chunks]
```

### 2. Update the call site in `ingest_attachments()`

Find the call to `_chunk_text` inside `ingest_attachments()`:

```python
chunks = _chunk_text(content, INGEST_CHUNK_SIZE, INGEST_MAX_CHUNKS)
```

Replace with:

```python
chunks = _semantic_chunk_text(content, INGEST_CHUNK_SIZE, INGEST_MAX_CHUNKS)
```

No other change to `ingest_attachments()`.

### 3. Update existing tests that imported `_chunk_text`

In `tests/test_document_ingestion.py`, the following imports will break:
```python
from coordinators.memory import Memory, _chunk_text, INGEST_CHUNK_SIZE, INGEST_MAX_CHUNKS
```

Replace with:
```python
from coordinators.memory import Memory, _semantic_chunk_text, INGEST_CHUNK_SIZE, INGEST_MAX_CHUNKS
```

Then update the five `_chunk_text` test functions to call `_semantic_chunk_text`
instead. The test assertions remain valid — `_semantic_chunk_text` is a drop-in
replacement that satisfies all the same contracts (returns list of non-empty strings,
respects max_chunks, each chunk ≤ chunk_size chars, handles empty input).

The one test that checks newline boundary preference (`test_chunk_text_prefers_newline_boundaries`)
remains valid because `_semantic_chunk_text` uses `_char_chunk` as its fallback, which
also prefers newline breaks.

---

## Tests (`tests/test_semantic_chunking.py`)

Create this new test file:

```python
"""Tests for semantic (structure-aware) document chunking."""
from __future__ import annotations

import pytest

from coordinators.memory import _semantic_chunk_text, _char_chunk, INGEST_CHUNK_SIZE, INGEST_MAX_CHUNKS


# ── _char_chunk (fallback) ───────────────────────────────────────────────────

def test_char_chunk_short_is_one_chunk():
    assert _char_chunk("hello world", 1500) == ["hello world"]


def test_char_chunk_splits_long_content():
    text = "a" * 4000
    chunks = _char_chunk(text, 1500)
    assert len(chunks) > 1
    assert all(len(c) <= 1500 for c in chunks)


def test_char_chunk_empty_returns_empty():
    assert _char_chunk("", 1500) == []


# ── _semantic_chunk_text: basic contracts ─────────────────────────────────────

def test_semantic_chunk_empty_returns_empty():
    assert _semantic_chunk_text("", 1500, 20) == []


def test_semantic_chunk_short_content_is_one_chunk():
    result = _semantic_chunk_text("hello world", 1500, 20)
    assert result == ["hello world"]


def test_semantic_chunk_respects_max_chunks():
    # Many small sections
    text = "\n".join(f"## Section {i}\nContent {i}" for i in range(50))
    chunks = _semantic_chunk_text(text, 1500, 5)
    assert len(chunks) <= 5


def test_semantic_chunk_each_chunk_within_size():
    text = "a" * 10000
    chunks = _semantic_chunk_text(text, 1500, 20)
    for chunk in chunks:
        assert len(chunk) <= 1500


def test_semantic_chunk_no_empty_chunks():
    text = "\n\n".join(["paragraph one", "paragraph two", "paragraph three"])
    chunks = _semantic_chunk_text(text, 1500, 20)
    assert all(c.strip() for c in chunks)


# ── _semantic_chunk_text: structural boundary detection ──────────────────────

def test_semantic_chunk_splits_on_markdown_headers():
    text = "# Introduction\nSome intro text.\n## Section One\nContent one.\n## Section Two\nContent two."
    chunks = _semantic_chunk_text(text, 1500, 20)
    # Each section should be its own chunk (all fit within chunk_size)
    assert any("Introduction" in c for c in chunks)
    assert any("Section One" in c for c in chunks)
    assert any("Section Two" in c for c in chunks)


def test_semantic_chunk_splits_on_numbered_sections():
    text = "8.1 First Section\nContent of first.\n8.2 Second Section\nContent of second.\n8.3 Third Section\nContent of third."
    chunks = _semantic_chunk_text(text, 1500, 20)
    assert any("8.1" in c for c in chunks)
    assert any("8.2" in c for c in chunks)
    assert any("8.3" in c for c in chunks)


def test_semantic_chunk_splits_on_section_symbols():
    text = "§5.3 Authority and Truth\nThis section covers authority.\n§8.2 Hands Coordinator\nThis section covers Hands."
    chunks = _semantic_chunk_text(text, 1500, 20)
    assert any("§5.3" in c for c in chunks)
    assert any("§8.2" in c for c in chunks)


def test_semantic_chunk_header_preserved_in_sub_chunks():
    """When a section is split because it's too large, the header is prepended to sub-chunks."""
    header = "## Section 8.2 Hands Coordinator"
    body = ("detailed content paragraph. " * 60 + "\n\n") * 5  # definitely > 1500 chars
    text = f"{header}\n{body}"
    chunks = _semantic_chunk_text(text, 1500, 20)
    # At least some sub-chunks should contain the header for context
    assert any("Section 8.2" in c for c in chunks)


def test_semantic_chunk_no_structural_boundaries_falls_back_gracefully():
    """Plain prose with no headers is still chunked correctly."""
    text = ("This is a sentence. " * 40 + "\n\n") * 5
    chunks = _semantic_chunk_text(text, 1500, 20)
    assert len(chunks) > 0
    assert all(len(c) <= 1500 for c in chunks)


def test_semantic_chunk_section_8_2_stays_together():
    """A realistic section that fits in chunk_size is not split."""
    section = (
        "§8.2 Hands Coordinator\n\n"
        "The Hands coordinator manages OS-level computer use actions.\n\n"
        "The intended safety policy is default-to-review. Any action type not "
        "explicitly recognized and approved must be routed to the Awareness "
        "coordinator for policy evaluation rather than being treated as safe "
        "by omission.\n\n"
        "This posture prevents silent inheritance of unsafe permissions."
    )
    chunks = _semantic_chunk_text(section, 1500, 20)
    # Should be a single chunk since the whole section is < 1500 chars
    assert len(chunks) == 1
    assert "§8.2" in chunks[0]
    assert "default-to-review" in chunks[0]
```

---

## Verification

```
pytest tests/test_semantic_chunking.py -v
pytest tests/test_document_ingestion.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_semchunk -v
```

Confirm `world_models/config.py` is not staged:
```
git status
```

Commit:
```
git commit -m "feat: semantic chunking for document ingestion — splits on section headers, preserves structural context"
```
