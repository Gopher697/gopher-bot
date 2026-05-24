# Codex Task — Persist user-provided documents and image descriptions to graph

## Context and Why This Matters

The entire point of the neurosymbolic architecture is that the LLM is stateless.
Memory lives in the graph, not in the context window. A model reload, restart, or
new session should not lose anything the user has shared.

Currently that invariant is broken for user-provided content:
- Text attachments (`.md`, `.py`, etc.) get prepended to the message and used for
  one turn. They are never written to the graph. After any LLM reload they are gone.
- Image descriptions (from `visual_percept.description`) go into the system prompt
  for one turn. Also never written to the graph.

The fix: when a user sends an attachment, write it to the graph immediately as
Observation nodes (chunked, embedded) so Memory can retrieve the content on any
future turn — including after restarts.

**Files that change:**
1. `interface/discord_bot.py` — pass text attachments as structured data alongside
   the message string (currently only the concatenated string is passed)
2. `coordinators/memory.py` — add `ingest_attachments()` called from `process()`

Do not modify `world_models/graph.py`. All graph functions needed already exist:
`create_source()`, `store()` (via `Memory.store()`).

---

## Security invariant

Run `git status` before committing. If `world_models/config.py` appears, STOP.

---

## Part 1 — `interface/discord_bot.py`

### Change `_read_all_text_attachments` return type

The function currently returns `str` (concatenated content). Change it to return
`tuple[str, list[dict]]` — the concatenated string (for prepending to the current
message as before) AND a structured list for ingestion:

```python
async def _read_all_text_attachments(
    message: discord.Message,
) -> tuple[str, list[dict]]:
    """
    Read all non-image attachments.

    Returns:
        (combined_text, structured_list)
        combined_text: concatenated content for current-turn context (prepended to message)
        structured_list: [{"filename": str, "content": str}, ...] for graph ingestion
    """
    parts: list[str] = []
    structured: list[dict] = []
    for attachment in message.attachments:
        suffix = Path(attachment.filename or "").suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            continue
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
            structured.append({"filename": attachment.filename, "content": text})
        except UnicodeDecodeError:
            parts.append(
                f"[{attachment.filename}]: (binary file — content cannot be displayed)"
            )
    return "\n\n".join(parts), structured
```

### Update `on_message` call site

Replace:
```python
attachment_text = await _read_all_text_attachments(message)
if attachment_text:
    content = f"{content}\n\n{attachment_text}".strip() if content else attachment_text
```

With:
```python
attachment_text, text_attachments = await _read_all_text_attachments(message)
if attachment_text:
    content = f"{content}\n\n{attachment_text}".strip() if content else attachment_text
```

And pass `text_attachments` to `synchronous_run`:
```python
packet = await asyncio.to_thread(
    bot.awareness.synchronous_run,
    content,
    image_attachments=image_attachments,
    text_attachments=text_attachments,
)
```

---

## Part 2 — `coordinators/memory.py`

### Add `ingest_attachments()` method to `Memory`

Add this method to the `Memory` class:

```python
def ingest_attachments(
    self,
    text_attachments: list[dict],
    visual_description: str = "",
    visual_filename: str = "",
    session_id: str = "",
) -> None:
    """
    Write user-provided content to the graph as retrievable Observations.

    Text attachments are chunked (max INGEST_CHUNK_SIZE chars each, up to
    INGEST_MAX_CHUNKS chunks per file) and stored as Observations so Memory
    can retrieve them on future turns via vector or keyword search.

    Image descriptions are stored as a single Observation if non-empty.

    Ingestion is best-effort — failures are logged and do not raise.
    """
    for attachment in text_attachments:
        filename = attachment.get("filename") or "untitled"
        content = str(attachment.get("content") or "").strip()
        if not content:
            continue
        try:
            chunks = _chunk_text(content, INGEST_CHUNK_SIZE, INGEST_MAX_CHUNKS)
            for i, chunk in enumerate(chunks):
                label = f"[{filename} chunk {i + 1}/{len(chunks)}]" if len(chunks) > 1 else f"[{filename}]"
                self.store(
                    f"{label}\n{chunk}",
                    source_type="external_content",
                )
        except Exception as exc:
            logger.warning("Failed to ingest text attachment %s: %s", filename, exc)

    if visual_description:
        try:
            label = f"[image: {visual_filename}]" if visual_filename else "[image]"
            self.store(
                f"{label}\n{visual_description}",
                source_type="external_content",
            )
        except Exception as exc:
            logger.warning("Failed to ingest image description: %s", exc)
```

### Add chunking helper and constants (module level)

Add near the top of `memory.py`, after the imports:

```python
INGEST_CHUNK_SIZE = 1500   # characters per chunk
INGEST_MAX_CHUNKS = 20     # max chunks per document (~30KB)


def _chunk_text(text: str, chunk_size: int, max_chunks: int) -> list[str]:
    """Split text into chunks of at most chunk_size characters."""
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < max_chunks:
        end = start + chunk_size
        # Prefer breaking at a newline near the boundary
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start:
                end = newline
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]
```

### Wire `ingest_attachments` into `Memory.process()`

Update `process()`:

```python
def process(self, packet: dict) -> dict:
    keywords = packet.get("keywords") or []
    packet["memory_context"] = self.retrieve(keywords)

    # Ingest user-provided content into the graph for future retrieval
    text_attachments = packet.get("text_attachments") or []
    visual_percept = packet.get("visual_percept") or {}
    visual_description = ""
    visual_filename = ""
    if visual_percept.get("scene_type") == "user_attachment":
        visual_description = str(visual_percept.get("description") or "").strip()
        # Extract filename from description prefix if present
        desc = visual_description
        if desc.startswith("[") and "]:" in desc:
            visual_filename = desc[1:desc.index("]")]

    if text_attachments or visual_description:
        self.ingest_attachments(
            text_attachments=text_attachments,
            visual_description=visual_description,
            visual_filename=visual_filename,
            session_id=str(packet.get("session_id") or ""),
        )

    return packet
```

---

## Part 3 — Tests (`tests/test_document_ingestion.py`)

Create this new test file:

```python
"""Tests for user-provided document and image ingestion into the graph."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from coordinators.memory import Memory, _chunk_text, INGEST_CHUNK_SIZE, INGEST_MAX_CHUNKS


# ── _chunk_text ─────────────────────────────────────────────────────────────

def test_chunk_text_short_content_is_one_chunk():
    result = _chunk_text("hello world", 1500, 20)
    assert result == ["hello world"]


def test_chunk_text_splits_long_content():
    text = "a" * 4000
    chunks = _chunk_text(text, 1500, 20)
    assert len(chunks) > 1
    assert all(len(c) <= 1500 for c in chunks)


def test_chunk_text_respects_max_chunks():
    text = "line\n" * 10000
    chunks = _chunk_text(text, 100, 5)
    assert len(chunks) <= 5


def test_chunk_text_prefers_newline_boundaries():
    text = "first line\nsecond line\nthird line"
    chunks = _chunk_text(text, 20, 20)
    # Should not split mid-word at the exact char boundary
    combined = "\n".join(chunks)
    assert "first line" in combined
    assert "second line" in combined


def test_chunk_text_empty_returns_empty():
    assert _chunk_text("", 1500, 20) == []


# ── Memory.ingest_attachments ───────────────────────────────────────────────

def test_ingest_text_attachment_calls_store():
    memory = Memory()
    stored = []
    memory.store = lambda content, source_type="observed": stored.append((content, source_type))

    memory.ingest_attachments(
        text_attachments=[{"filename": "notes.md", "content": "# Title\nSome content here."}],
    )
    assert len(stored) == 1
    content, source_type = stored[0]
    assert "notes.md" in content
    assert "Some content here" in content
    assert source_type == "external_content"


def test_ingest_image_description_calls_store():
    memory = Memory()
    stored = []
    memory.store = lambda content, source_type="observed": stored.append((content, source_type))

    memory.ingest_attachments(
        text_attachments=[],
        visual_description="A hallway with a wet floor sign.",
        visual_filename="photo.jpg",
    )
    assert len(stored) == 1
    content, source_type = stored[0]
    assert "hallway" in content
    assert source_type == "external_content"


def test_ingest_empty_content_skipped():
    memory = Memory()
    stored = []
    memory.store = lambda content, source_type="observed": stored.append((content, source_type))

    memory.ingest_attachments(
        text_attachments=[{"filename": "empty.md", "content": ""}],
    )
    assert stored == []


def test_ingest_large_document_chunked():
    memory = Memory()
    stored = []
    memory.store = lambda content, source_type="observed": stored.append((content, source_type))

    big_content = "paragraph\n" * 500  # ~5000 chars
    memory.ingest_attachments(
        text_attachments=[{"filename": "big.md", "content": big_content}],
    )
    assert len(stored) > 1
    assert all(source_type == "external_content" for _, source_type in stored)


def test_ingest_respects_max_chunks():
    memory = Memory()
    stored = []
    memory.store = lambda content, source_type="observed": stored.append((content, source_type))

    huge_content = "x" * (INGEST_CHUNK_SIZE * (INGEST_MAX_CHUNKS + 10))
    memory.ingest_attachments(
        text_attachments=[{"filename": "huge.md", "content": huge_content}],
    )
    assert len(stored) <= INGEST_MAX_CHUNKS


def test_ingest_failure_does_not_raise():
    memory = Memory()

    def bad_store(content, source_type="observed"):
        raise RuntimeError("graph down")

    memory.store = bad_store
    # Must not raise
    memory.ingest_attachments(
        text_attachments=[{"filename": "doc.md", "content": "some content"}],
    )


# ── Memory.process wires ingest ──────────────────────────────────────────────

def test_memory_process_calls_ingest_for_text_attachments():
    memory = Memory()
    ingested = []
    memory.ingest_attachments = lambda **kw: ingested.append(kw)
    memory.retrieve = lambda keywords: ""

    packet = {
        "keywords": [],
        "text_attachments": [{"filename": "doc.md", "content": "hello"}],
    }
    memory.process(packet)
    assert len(ingested) == 1
    assert ingested[0]["text_attachments"][0]["filename"] == "doc.md"


def test_memory_process_calls_ingest_for_user_attachment_image():
    memory = Memory()
    ingested = []
    memory.ingest_attachments = lambda **kw: ingested.append(kw)
    memory.retrieve = lambda keywords: ""

    packet = {
        "keywords": [],
        "text_attachments": [],
        "visual_percept": {
            "scene_type": "user_attachment",
            "description": "[photo.jpg]: A desk with a laptop.",
        },
    }
    memory.process(packet)
    assert len(ingested) == 1
    assert "A desk" in ingested[0]["visual_description"]


def test_memory_process_skips_ingest_when_no_attachments():
    memory = Memory()
    ingested = []
    memory.ingest_attachments = lambda **kw: ingested.append(kw)
    memory.retrieve = lambda keywords: ""

    packet = {"keywords": ["hello"]}
    memory.process(packet)
    assert ingested == []
```

---

## Verification

```
pytest tests/test_document_ingestion.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_ingestion -v
```

Confirm `world_models/config.py` is not staged:
```
git status
```

Commit:
```
git commit -m "feat: persist user-provided documents and image descriptions to graph via Memory ingestion"
```
