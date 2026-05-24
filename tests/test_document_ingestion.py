"""Tests for user-provided document and image ingestion into the graph."""
from __future__ import annotations

from coordinators.memory import (
    INGEST_CHUNK_SIZE,
    INGEST_MAX_CHUNKS,
    Memory,
    _chunk_text,
)


# -- _chunk_text -------------------------------------------------------------

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


# -- Memory.ingest_attachments ----------------------------------------------

def test_ingest_text_attachment_calls_store():
    memory = Memory()
    stored = []
    memory.store = lambda content, source_type="observed": stored.append(
        (content, source_type)
    )

    memory.ingest_attachments(
        text_attachments=[
            {"filename": "notes.md", "content": "# Title\nSome content here."}
        ],
    )
    assert len(stored) == 1
    content, source_type = stored[0]
    assert "notes.md" in content
    assert "Some content here" in content
    assert source_type == "external_content"


def test_ingest_image_description_calls_store():
    memory = Memory()
    stored = []
    memory.store = lambda content, source_type="observed": stored.append(
        (content, source_type)
    )

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
    memory.store = lambda content, source_type="observed": stored.append(
        (content, source_type)
    )

    memory.ingest_attachments(
        text_attachments=[{"filename": "empty.md", "content": ""}],
    )
    assert stored == []


def test_ingest_large_document_chunked():
    memory = Memory()
    stored = []
    memory.store = lambda content, source_type="observed": stored.append(
        (content, source_type)
    )

    big_content = "paragraph\n" * 500  # ~5000 chars
    memory.ingest_attachments(
        text_attachments=[{"filename": "big.md", "content": big_content}],
    )
    assert len(stored) > 1
    assert all(source_type == "external_content" for _, source_type in stored)


def test_ingest_respects_max_chunks():
    memory = Memory()
    stored = []
    memory.store = lambda content, source_type="observed": stored.append(
        (content, source_type)
    )

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


# -- Memory.process wires ingest --------------------------------------------

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
