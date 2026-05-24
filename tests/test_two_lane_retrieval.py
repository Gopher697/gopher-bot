"""Tests for two-lane memory retrieval (relevant + recent episodic)."""
from __future__ import annotations

from unittest.mock import patch

from coordinators.memory import (
    Memory,
    RECENT_EPISODIC_ITEMS,
    RELEVANT_CONTEXT_ITEMS,
    _format_recent_episodic,
)


# -- _format_recent_episodic -------------------------------------------------

def test_format_recent_episodic_empty():
    assert _format_recent_episodic([]) == ""


def test_format_recent_episodic_single():
    items = [{"content": "User said: hi\nGopher-bot replied: hello"}]
    result = _format_recent_episodic(items)
    assert "User said: hi" in result


def test_format_recent_episodic_multiple_chronological():
    """Items come in newest-first; output should be oldest-first."""
    items = [
        {"content": "second exchange"},
        {"content": "first exchange"},
    ]
    result = _format_recent_episodic(items)
    assert result.index("first exchange") < result.index("second exchange")


# -- Memory._retrieve_recent_episodic ---------------------------------------

def test_retrieve_recent_episodic_returns_observed_only():
    """Only source_type='observed' nodes are returned by the query."""
    memory = Memory()
    fake_items = [
        {"content": "exchange 1", "source_type": "observed"},
        {"content": "exchange 2", "source_type": "observed"},
    ]

    def fake_retrieve(environment="global", limit=RECENT_EPISODIC_ITEMS):
        return fake_items

    memory._retrieve_recent_episodic = fake_retrieve
    result = memory._retrieve_recent_episodic()
    assert len(result) == 2
    assert all(item["source_type"] == "observed" for item in result)


def test_retrieve_recent_episodic_returns_empty_on_failure():
    memory = Memory()
    with patch("coordinators.memory.graph.connect", side_effect=RuntimeError("db down")):
        result = memory._retrieve_recent_episodic()
    assert result == []


# -- Memory.retrieve() two-lane combination ----------------------------------

def test_retrieve_includes_recent_section_when_exchanges_exist():
    memory = Memory()
    memory.embedder.embed = lambda _: None
    memory._retrieve_keyword_context = (
        lambda terms, environment="global", limit=12: "relevant stuff"
    )
    memory._retrieve_recent_episodic = (
        lambda environment="global", limit=RECENT_EPISODIC_ITEMS: [
            {"content": "User said: hello\nGopher-bot replied: hi"}
        ]
    )

    result = memory.retrieve(["hello"])
    assert "[Recent exchanges]" in result
    assert "User said: hello" in result


def test_retrieve_includes_relevant_section_when_keywords_match():
    memory = Memory()
    memory.embedder.embed = lambda _: None
    memory._retrieve_keyword_context = (
        lambda terms, environment="global", limit=12: "whitepaper content"
    )
    memory._retrieve_recent_episodic = (
        lambda environment="global", limit=RECENT_EPISODIC_ITEMS: []
    )

    result = memory.retrieve(["whitepaper"])
    assert "[Relevant context]" in result
    assert "whitepaper content" in result


def test_retrieve_deduplicates_across_lanes():
    """Content in relevant lane should not appear again in recent lane."""
    shared_content = "User said: hello\nGopher-bot replied: hi"
    memory = Memory()
    memory.embedder.embed = lambda _: None
    memory._retrieve_keyword_context = (
        lambda terms, environment="global", limit=12: shared_content
    )
    memory._retrieve_recent_episodic = (
        lambda environment="global", limit=RECENT_EPISODIC_ITEMS: [
            {"content": shared_content}
        ]
    )

    result = memory.retrieve(["hello"])
    assert result.count(shared_content) == 1


def test_retrieve_returns_empty_string_when_nothing_found():
    memory = Memory()
    memory.embedder.embed = lambda _: None
    memory._retrieve_keyword_context = lambda terms, environment="global", limit=12: ""
    memory._retrieve_recent_episodic = (
        lambda environment="global", limit=RECENT_EPISODIC_ITEMS: []
    )

    result = memory.retrieve(["nomatch"])
    assert result == ""


def test_retrieve_works_with_no_keywords():
    """Even with no keywords, recent episodic lane should still fire."""
    memory = Memory()
    memory.embedder.embed = lambda _: None
    memory._retrieve_keyword_context = lambda terms, environment="global", limit=12: ""
    memory._retrieve_recent_episodic = (
        lambda environment="global", limit=RECENT_EPISODIC_ITEMS: [
            {"content": "recent exchange"}
        ]
    )

    result = memory.retrieve([])
    assert "recent exchange" in result


# -- Constants sanity --------------------------------------------------------

def test_recent_episodic_items_is_positive():
    assert RECENT_EPISODIC_ITEMS > 0


def test_relevant_context_items_is_positive():
    assert RELEVANT_CONTEXT_ITEMS > 0
