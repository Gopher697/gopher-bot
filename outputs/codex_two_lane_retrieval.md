# Codex Task — Two-lane memory retrieval: relevant + recent episodic

## Context and Why This Matters

The bot currently retrieves memory using keyword (or vector) search only. This means
retrieval is purely topic-driven: whatever observations contain the right keywords
surfaces, regardless of when it happened or what kind of content it is.

The problem this causes in practice: after a user sends a whitepaper (20 chunks stored
as `external_content`), any question touching on memory, identity, or architecture
causes those whitepaper chunks to fill the `MAX_CONTEXT_ITEMS` limit. The bot's own
recent conversation exchanges (`source_type="observed"`) never surface. The bot cannot
see what it just did or said in this session — it reports "nothing stored in episodic
memory" because its retrieval window is full of document content.

The fix: two retrieval lanes, combined into one context string passed to Reason.

- **Relevant lane** — existing keyword/vector search (unchanged logic, reduced item
  budget to make room for the second lane)
- **Recent lane** — always pull the last N `source_type="observed"` observations
  ordered by `created_at DESC`, regardless of keyword match; these are the bot's own
  lived conversational experience

The two lanes are deduped and labeled so Reason can distinguish "what I read" from
"what I experienced recently."

**Files that change:**
1. `coordinators/memory.py` — add `_retrieve_recent_episodic()`, update `retrieve()`,
   add `RECENT_EPISODIC_ITEMS` constant, update `_format_context()` callers

Do not modify `world_models/graph.py`, `world_models/config.py`, or any other file.

---

## Security invariant

Run `git status` before committing. If `world_models/config.py` appears, STOP.

---

## Changes to `coordinators/memory.py`

### 1. Add constants (after existing constants near top of file)

```python
RECENT_EPISODIC_ITEMS = 6   # always pull this many recent observed exchanges
RELEVANT_CONTEXT_ITEMS = 8  # keyword/vector lane budget (was MAX_CONTEXT_ITEMS=12)
```

Keep `MAX_CONTEXT_ITEMS = 12` in place — it is used by existing tests. The new
constants are additive.

### 2. Add `_retrieve_recent_episodic()` method to `Memory`

Add after `_retrieve_keyword_context()`:

```python
def _retrieve_recent_episodic(
    self,
    environment: str = "global",
    limit: int = RECENT_EPISODIC_ITEMS,
) -> list[dict]:
    """
    Return the most recent observed conversation exchanges from the graph,
    ordered newest-first. These are source_type='observed' Observation nodes
    written by Reason after each turn.

    Returns a list of observation property dicts, or [] on failure.
    """
    driver = None
    try:
        driver = graph.connect()
        with driver.session(database=config.NEO4J_DATABASE) as session:
            records = session.run(
                """
                MATCH (observation:Observation {environment: $environment})
                WHERE coalesce(observation.status, 'active') = 'active'
                  AND coalesce(observation.source_type, 'observed') = 'observed'
                RETURN properties(observation) AS observation
                ORDER BY observation.created_at DESC
                LIMIT $limit
                """,
                environment=environment,
                limit=limit,
            )
            return [record["observation"] for record in records]
    except Exception:
        return []
    finally:
        if driver is not None:
            graph.close(driver)
```

### 3. Update `retrieve()` to combine both lanes

Replace the existing `retrieve()` method:

```python
def retrieve(self, keywords: Iterable[str], environment: str = "global") -> str:
    terms = _normalize_keywords(keywords)

    # Lane 1: topic-relevant content (keyword or vector)
    relevant_text = ""
    if terms:
        embedding = self.embedder.embed(" ".join(terms))
        if embedding is not None:
            relevant_text = self._retrieve_vector_context(embedding, environment)
        if not relevant_text:
            relevant_text = self._retrieve_keyword_context(
                terms, environment, limit=RELEVANT_CONTEXT_ITEMS
            )

    # Lane 2: recent episodic exchanges (always, regardless of keywords)
    recent_items = self._retrieve_recent_episodic(environment)
    # Deduplicate: drop recent items whose content already appears in relevant_text
    unique_recent = [
        item for item in recent_items
        if not relevant_text or str(item.get("content", "")) not in relevant_text
    ]
    recent_text = _format_recent_episodic(unique_recent)

    # Combine: recent context first (highest signal for coherence), then broader context
    parts = []
    if recent_text:
        parts.append(f"[Recent exchanges]\n{recent_text}")
    if relevant_text:
        parts.append(f"[Relevant context]\n{relevant_text}")
    return "\n\n".join(parts)
```

### 4. Update `_retrieve_keyword_context()` signature to accept `limit`

The existing method hard-codes `limit=MAX_CONTEXT_ITEMS`. Add a `limit` parameter
so `retrieve()` can pass `RELEVANT_CONTEXT_ITEMS`:

```python
def _retrieve_keyword_context(
    self,
    terms: Iterable[str],
    environment: str = "global",
    limit: int = MAX_CONTEXT_ITEMS,
) -> str:
```

Replace both occurrences of `limit=MAX_CONTEXT_ITEMS` inside the method body with
`limit=limit`. No other change to the method.

### 5. Add `_format_recent_episodic()` module-level helper

Add after the existing `_chunk_text` function:

```python
def _format_recent_episodic(items: list[dict]) -> str:
    """Format recent observed observations into a readable context string."""
    if not items:
        return ""
    lines = []
    for item in reversed(items):  # oldest first so conversation reads chronologically
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(content)
    return "\n---\n".join(lines)
```

---

## Tests (`tests/test_two_lane_retrieval.py`)

Create this new test file:

```python
"""Tests for two-lane memory retrieval (relevant + recent episodic)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from coordinators.memory import (
    Memory,
    RECENT_EPISODIC_ITEMS,
    RELEVANT_CONTEXT_ITEMS,
    _format_recent_episodic,
)


# ── _format_recent_episodic ──────────────────────────────────────────────────

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


# ── Memory._retrieve_recent_episodic ────────────────────────────────────────

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
    # Patch graph.connect to raise
    with patch("coordinators.memory.graph.connect", side_effect=RuntimeError("db down")):
        result = memory._retrieve_recent_episodic()
    assert result == []


# ── Memory.retrieve() two-lane combination ───────────────────────────────────

def test_retrieve_includes_recent_section_when_exchanges_exist():
    memory = Memory()
    memory.embedder.embed = lambda _: None  # disable vector lane
    memory._retrieve_keyword_context = lambda terms, environment="global", limit=12: "relevant stuff"
    memory._retrieve_recent_episodic = lambda environment="global", limit=RECENT_EPISODIC_ITEMS: [
        {"content": "User said: hello\nGopher-bot replied: hi"}
    ]

    result = memory.retrieve(["hello"])
    assert "[Recent exchanges]" in result
    assert "User said: hello" in result


def test_retrieve_includes_relevant_section_when_keywords_match():
    memory = Memory()
    memory.embedder.embed = lambda _: None
    memory._retrieve_keyword_context = lambda terms, environment="global", limit=12: "whitepaper content"
    memory._retrieve_recent_episodic = lambda environment="global", limit=RECENT_EPISODIC_ITEMS: []

    result = memory.retrieve(["whitepaper"])
    assert "[Relevant context]" in result
    assert "whitepaper content" in result


def test_retrieve_deduplicates_across_lanes():
    """Content in relevant lane should not appear again in recent lane."""
    shared_content = "User said: hello\nGopher-bot replied: hi"
    memory = Memory()
    memory.embedder.embed = lambda _: None
    memory._retrieve_keyword_context = lambda terms, environment="global", limit=12: shared_content
    memory._retrieve_recent_episodic = lambda environment="global", limit=RECENT_EPISODIC_ITEMS: [
        {"content": shared_content}
    ]

    result = memory.retrieve(["hello"])
    # The shared content should appear only once
    assert result.count(shared_content) == 1


def test_retrieve_returns_empty_string_when_nothing_found():
    memory = Memory()
    memory.embedder.embed = lambda _: None
    memory._retrieve_keyword_context = lambda terms, environment="global", limit=12: ""
    memory._retrieve_recent_episodic = lambda environment="global", limit=RECENT_EPISODIC_ITEMS: []

    result = memory.retrieve(["nomatch"])
    assert result == ""


def test_retrieve_works_with_no_keywords():
    """Even with no keywords, recent episodic lane should still fire."""
    memory = Memory()
    memory.embedder.embed = lambda _: None
    memory._retrieve_keyword_context = lambda terms, environment="global", limit=12: ""
    memory._retrieve_recent_episodic = lambda environment="global", limit=RECENT_EPISODIC_ITEMS: [
        {"content": "recent exchange"}
    ]

    result = memory.retrieve([])
    assert "recent exchange" in result


# ── Constants sanity ─────────────────────────────────────────────────────────

def test_recent_episodic_items_is_positive():
    assert RECENT_EPISODIC_ITEMS > 0


def test_relevant_context_items_is_positive():
    assert RELEVANT_CONTEXT_ITEMS > 0
```

---

## Verification

```
pytest tests/test_two_lane_retrieval.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_twolane -v
```

Confirm `world_models/config.py` is not staged:
```
git status
```

Commit:
```
git commit -m "feat: two-lane memory retrieval — recent episodic always surfaces alongside keyword-relevant context"
```
