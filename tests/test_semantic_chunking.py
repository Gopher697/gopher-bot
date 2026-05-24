"""Tests for semantic (structure-aware) document chunking."""
from __future__ import annotations

from coordinators.memory import _char_chunk, _semantic_chunk_text


# -- _char_chunk (fallback) --------------------------------------------------

def test_char_chunk_short_is_one_chunk():
    assert _char_chunk("hello world", 1500) == ["hello world"]


def test_char_chunk_splits_long_content():
    text = "a" * 4000
    chunks = _char_chunk(text, 1500)
    assert len(chunks) > 1
    assert all(len(c) <= 1500 for c in chunks)


def test_char_chunk_empty_returns_empty():
    assert _char_chunk("", 1500) == []


# -- _semantic_chunk_text: basic contracts -----------------------------------

def test_semantic_chunk_empty_returns_empty():
    assert _semantic_chunk_text("", 1500, 20) == []


def test_semantic_chunk_short_content_is_one_chunk():
    result = _semantic_chunk_text("hello world", 1500, 20)
    assert result == ["hello world"]


def test_semantic_chunk_respects_max_chunks():
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


# -- _semantic_chunk_text: structural boundary detection ---------------------

def test_semantic_chunk_splits_on_markdown_headers():
    text = (
        "# Introduction\nSome intro text.\n"
        "## Section One\nContent one.\n"
        "## Section Two\nContent two."
    )
    chunks = _semantic_chunk_text(text, 1500, 20)
    assert any("Introduction" in c for c in chunks)
    assert any("Section One" in c for c in chunks)
    assert any("Section Two" in c for c in chunks)


def test_semantic_chunk_splits_on_numbered_sections():
    text = (
        "8.1 First Section\nContent of first.\n"
        "8.2 Second Section\nContent of second.\n"
        "8.3 Third Section\nContent of third."
    )
    chunks = _semantic_chunk_text(text, 1500, 20)
    assert any("8.1" in c for c in chunks)
    assert any("8.2" in c for c in chunks)
    assert any("8.3" in c for c in chunks)


def test_semantic_chunk_splits_on_section_symbols():
    text = (
        "§5.3 Authority and Truth\nThis section covers authority.\n"
        "§8.2 Hands Coordinator\nThis section covers Hands."
    )
    chunks = _semantic_chunk_text(text, 1500, 20)
    assert any("§5.3" in c for c in chunks)
    assert any("§8.2" in c for c in chunks)


def test_semantic_chunk_header_preserved_in_sub_chunks():
    """Oversized sections keep their header in sub-chunks."""
    header = "## Section 8.2 Hands Coordinator"
    body = ("detailed content paragraph. " * 60 + "\n\n") * 5
    text = f"{header}\n{body}"
    chunks = _semantic_chunk_text(text, 1500, 20)
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
    assert len(chunks) == 1
    assert "§8.2" in chunks[0]
    assert "default-to-review" in chunks[0]
