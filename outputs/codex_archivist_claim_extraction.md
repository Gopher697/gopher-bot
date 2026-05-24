# Codex Task — Archivist Claim Extraction

## Context

This task comes from a Director (Claude) session. The Director has read all
relevant source files before writing this prompt. Do not redesign — implement
exactly what is described.

## The Problem

The epistemic pipeline is hollow. `Archivist.background_tick()` creates
`Source` + `LearningEpisode` nodes but never writes `Claim` nodes. Nothing
downstream (Wisdom, organic node emergence) can work until Claims exist.

Root cause has two parts:

1. `build_turn_log_entry()` in `coordinators/base.py` stores only metrics.
   It does not store the user message or bot response, so Archivist has no
   text to extract claims from.

2. `archivist.py` has no claim extraction logic and no call to
   `graph.create_claim()` or the link functions.

## Changes Required

### Part 1 — coordinators/base.py

In `build_turn_log_entry()`, add two fields to the returned dict:

```python
"message":  str(packet.get("message")  or "")[:2000],
"response": str(packet.get("response") or "")[:2000],
```

Place them after `"has_error"`. Cap at 2000 chars each — the claim extractor
needs the gist, not the full text.

Do NOT change any other part of `base.py`.

---

### Part 2 — coordinators/archivist.py

#### 2a. Add a claim extractor function

Add this function near the top of the module (before `Archivist`):

```python
def _extract_claims(message: str, response: str) -> list[dict]:
    """
    Call the local LLM (qwen2.5-3b-instruct via LM Studio) to extract
    1–3 durable factual claims from a conversation turn.

    Returns a list of dicts: [{"text": str, "confidence": float}, ...]
    Returns [] on any failure — extraction is always optional.
    """
    import json

    text = f"User: {message}\nAssistant: {response}".strip()
    if not text or text == "User: \nAssistant:":
        return []

    prompt = (
        "Extract 1 to 3 factual, durable claims from this conversation turn.\n"
        "A claim is a short declarative statement about what is true or was observed.\n"
        "Return a JSON array of objects with keys: \"text\" (string) and "
        "\"confidence\" (float 0.0–1.0).\n"
        "Return ONLY the JSON array. No explanation.\n\n"
        f"{text}"
    )

    try:
        from openai import OpenAI

        client = OpenAI(
            base_url="http://localhost:1234/v1",
            api_key="lm-studio",
        )
        completion = client.chat.completions.create(
            model="qwen2.5-3b-instruct",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.2,
        )
        raw = (completion.choices[0].message.content or "").strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []
        result = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            text_val = str(item.get("text") or "").strip()
            if not text_val:
                continue
            conf = float(item.get("confidence") or 0.5)
            conf = max(0.0, min(1.0, conf))
            result.append({"text": text_val, "confidence": conf})
        return result[:3]
    except Exception:
        return []
```

#### 2b. Add a default claim writer

Add this function after `_default_graph_writer`:

```python
def _default_claim_writer(
    source_id: str,
    learning_id: str,
    claims: list[dict],
    environment: str,
) -> list[str]:
    """
    Write extracted claims to the graph and link them to the given
    Source and LearningEpisode. Returns list of created claim_ids.
    """
    if not claims or not source_id:
        return []

    driver = None
    try:
        from world_models import graph

        driver = graph.connect()
        claim_ids: list[str] = []
        for claim in claims:
            claim_id = graph.create_claim(
                driver=driver,
                content=claim["text"],
                source_id=source_id,
                environment=environment,
                coordinator="archivist",
                confidence=claim.get("confidence", 0.5),
                status="candidate",
            )
            graph.link_source_to_claim(driver, source_id, claim_id, environment)
            if learning_id:
                graph.link_learning_episode_to_claim(
                    driver, learning_id, claim_id, environment
                )
            claim_ids.append(claim_id)
        return claim_ids
    except Exception:
        return []
    finally:
        if driver is not None:
            try:
                graph.close(driver)
            except Exception:
                pass
```

#### 2c. Add `claim_writer` to `Archivist.__init__`

Add a `claim_writer` parameter with default `None`:

```python
def __init__(
    self,
    turn_log_reader: Callable[[int], list[dict]] | None = None,
    research_log_writer: Callable[[dict], None] | None = None,
    graph_writer: Callable[
        [str, str, str, str, str | None],
        tuple[str, str],
    ] | None = None,
    claim_writer: Callable[
        [str, str, list[dict], str],
        list[str],
    ] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> None:
    self.turn_log_reader = turn_log_reader or _default_turn_log_reader
    self.research_log_writer = research_log_writer or _default_research_log_writer
    self.graph_writer = graph_writer or _default_graph_writer
    self.claim_writer = claim_writer or _default_claim_writer
    self.clock = clock or (lambda: datetime.now(UTC))
    self.state = ArchivistState()
```

#### 2d. Wire extraction into `_build_research_entry`

`_build_research_entry` currently takes `(turn, graph_writer)`. Add `claim_writer`
as a third argument:

```python
def _build_research_entry(
    turn: dict,
    graph_writer: Callable,
    claim_writer: Callable,
) -> dict:
```

After the `source_id, learning_id = graph_writer(...)` call, add:

```python
# Claim extraction — optional, fails silently
message = str(turn.get("message") or "")
response = str(turn.get("response") or "")
claims: list[dict] = []
claim_ids: list[str] = []
if message or response:
    claims = _extract_claims(message, response)
    if claims and source_id:
        claim_ids = claim_writer(source_id, learning_id, claims, "global")
```

Add `"claim_count"` and `"claim_ids"` to the returned dict:

```python
return {
    ...existing fields...,
    "claim_count": len(claim_ids),
    "claim_ids": claim_ids,
}
```

#### 2e. Update the call site in `background_tick`

The `_build_research_entry` call in `background_tick` currently passes
`(turn, self.graph_writer)`. Update to:

```python
entry = _build_research_entry(turn, self.graph_writer, self.claim_writer)
```

---

## What NOT to change

- Do not modify `graph.py` — `create_claim`, `link_source_to_claim`, and
  `link_learning_episode_to_claim` already exist and are ready to use.
- Do not modify any other coordinator.
- Do not modify any existing test assertions.
- Do not use cloud models (Anthropic API) anywhere in Archivist.

---

## Tests

Add tests to `tests/test_archivist.py` covering:

1. **`test_build_turn_log_entry_includes_message_and_response`** (in
   `tests/test_coordinators.py` or wherever `build_turn_log_entry` is tested):
   - Pass a packet with `"message": "hello"` and `"response": "world"`
   - Assert both appear in the returned dict

2. **`test_extract_claims_returns_empty_on_empty_input`**:
   - Call `_extract_claims("", "")` — must return `[]` without making any
     network call (the early-exit guard handles this)

3. **`test_build_research_entry_calls_claim_writer`**:
   - Supply a fake `claim_writer` that records its arguments and returns `["cid-1"]`
   - Supply a fake `graph_writer` that returns `("src-1", "le-1")`
   - Supply a turn dict with `"message": "test"`, `"response": "response"`,
     and a fake `_extract_claims` (monkeypatch it to return
     `[{"text": "A claim.", "confidence": 0.8}]`)
   - Assert `claim_writer` was called with `source_id="src-1"`,
     `learning_id="le-1"`, and the extracted claims
   - Assert the returned entry has `"claim_count": 1`

4. **`test_build_research_entry_skips_claims_on_empty_text`**:
   - Supply a turn with no `"message"` or `"response"` fields
   - Supply a `claim_writer` that records calls
   - Assert `claim_writer` is never called

5. **`test_archivist_accepts_claim_writer_override`**:
   - Construct `Archivist(claim_writer=lambda *a, **kw: [])` — must not raise

---

## Verification

```
pytest tests/test_archivist.py -v
pytest tests/test_coordinators.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_archivist_claims -v
```

All 810+ tests must pass.

---

## Security invariant

Run `git status` before committing. If `world_models/config.py` appears, STOP.

## Commit

```
git commit -m "feat: Archivist claim extraction — turn log stores message/response, Archivist extracts and writes Claim nodes"
```
