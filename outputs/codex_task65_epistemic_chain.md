# Codex Task 65 — Epistemic Memory Chain: Source → Claim → Belief → Principle → Doctrine + LearningEpisode

## Context

Gopher-bot currently accumulates knowledge as Observations and Episode nodes. These record
*what happened*, but not *what was learned* or *why the AI believes what it believes*. For
the system to have genuine epistemic memory — and to support behavioral updates via Doctrine
(Task 66) — it needs a structured knowledge provenance chain.

The chain: **LearningEpisode → Source → Claim → Belief → Principle → Doctrine**

- **Source**: the origin of information (a paper, web page, conversation, autonomous observation)
- **Claim**: an assertion extracted from a Source
- **Belief**: a Claim cluster with sufficient corroboration to be held as a working truth
- **Principle**: a behavioral/epistemic rule derived from one or more Beliefs
- **Doctrine**: a foundational behavioral rule — immutable once adopted; versioning creates a
  new node rather than mutating the old one
- **LearningEpisode**: a learning event that connects a foreground turn (or background tick) to
  the Source it processed and the Claims it extracted

This task adds all six node types to `world_models/graph.py`, following the exact style of the
existing Goal node (VALID_* sets, `_*_properties` helper, `create_*`, `get_*`, and linking
functions). T66 will add the Doctrine-to-behavior wiring.

---

## Security invariant — check before every commit

`world_models/config.py` is gitignored and contains Neo4j credentials and API keys.
Run `git status` before committing. If `world_models/config.py` appears, STOP — do not commit.

---

## Part 1: Valid-value sets

Add after the Goal valid-value block:

```python
# ---------------------------------------------------------------------------
# Epistemic chain node constants
# ---------------------------------------------------------------------------

VALID_SOURCE_TYPES_EPISTEMIC = {
    "paper",          # academic / research paper
    "book",           # book or long-form reference
    "web",            # web page / article
    "conversation",   # content of a prior conversation
    "observation",    # first-person observation made by the AI
    "internal",       # internally generated (e.g., dream synthesis)
}

VALID_CLAIM_STATUSES = {
    "candidate",   # newly extracted; not yet evaluated
    "supported",   # corroborated by multiple observations or claims
    "refuted",     # contradicted by stronger evidence
    "uncertain",   # insufficient evidence to resolve
}

VALID_BELIEF_STATUSES = {
    "forming",     # accumulating supporting claims — not yet stable
    "held",        # stable, current working truth
    "challenged",  # contradictory evidence encountered
    "abandoned",   # no longer held
}

VALID_PRINCIPLE_STATUSES = {
    "proposed",    # derived but not yet adopted
    "adopted",     # active — shapes reasoning
    "deprecated",  # superseded or retired
}

VALID_PRINCIPLE_SCOPES = {
    "reasoning",     # shapes how conclusions are drawn
    "interaction",   # shapes how responses are formed
    "values",        # shapes what is pursued or avoided
    "knowledge",     # shapes what is believed about the world
}

VALID_DOCTRINE_STATUSES = {
    "active",      # adopted and in effect
    "deprecated",  # retired but preserved for history
    "contested",   # under review; not yet resolved
}

VALID_LEARNING_EPISODE_TYPES = {
    "ingestion",    # processed an external Source
    "reflection",   # arose from internal synthesis (Dream/Archivist)
    "conversation", # learned from a Gopher interaction
    "autonomous",   # arose from background-loop reasoning
}
```

---

## Part 2: Property builders

### `_source_properties`

```python
def _source_properties(
    title: str,
    source_type: str,
    environment: str,
    *,
    url: str | None = None,
    author: str = "",
    summary: str = "",
) -> Dict[str, Any]:
    if source_type not in VALID_SOURCE_TYPES_EPISTEMIC:
        raise ValueError(
            f"source_type must be one of {sorted(VALID_SOURCE_TYPES_EPISTEMIC)!r}, "
            f"got {source_type!r}"
        )
    return {
        "title": str(title).strip(),
        "source_type": source_type,
        "environment": environment,
        "url": url,
        "author": str(author).strip(),
        "summary": str(summary).strip(),
        "status": "active",
        "created_at": _now_iso(),
    }
```

### `_claim_properties`

```python
def _claim_properties(
    content: str,
    source_id: str,
    environment: str,
    coordinator: str,
    *,
    confidence: float = 0.5,
    status: str = "candidate",
) -> Dict[str, Any]:
    if status not in VALID_CLAIM_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(VALID_CLAIM_STATUSES)!r}, got {status!r}"
        )
    return {
        "content": str(content).strip(),
        "source_id": str(source_id),
        "environment": environment,
        "coordinator": str(coordinator),
        "confidence": _clamp_unit(float(confidence)),
        "status": status,
        "evidence_count": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
```

### `_belief_properties`

```python
def _belief_properties(
    content: str,
    environment: str,
    *,
    confidence: float = 0.5,
    status: str = "forming",
) -> Dict[str, Any]:
    if status not in VALID_BELIEF_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(VALID_BELIEF_STATUSES)!r}, got {status!r}"
        )
    return {
        "content": str(content).strip(),
        "environment": environment,
        "confidence": _clamp_unit(float(confidence)),
        "status": status,
        "claim_count": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
```

### `_principle_properties`

```python
def _principle_properties(
    content: str,
    environment: str,
    scope: str,
    *,
    status: str = "proposed",
) -> Dict[str, Any]:
    if scope not in VALID_PRINCIPLE_SCOPES:
        raise ValueError(
            f"scope must be one of {sorted(VALID_PRINCIPLE_SCOPES)!r}, got {scope!r}"
        )
    if status not in VALID_PRINCIPLE_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(VALID_PRINCIPLE_STATUSES)!r}, got {status!r}"
        )
    return {
        "content": str(content).strip(),
        "environment": environment,
        "scope": scope,
        "status": status,
        "belief_count": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
```

### `_doctrine_properties`

```python
def _doctrine_properties(
    content: str,
    environment: str,
    *,
    version: int = 1,
    parent_doctrine_id: str | None = None,
    status: str = "active",
) -> Dict[str, Any]:
    if status not in VALID_DOCTRINE_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(VALID_DOCTRINE_STATUSES)!r}, got {status!r}"
        )
    return {
        "content": str(content).strip(),
        "environment": environment,
        "status": status,
        "version": max(1, int(version)),
        "parent_doctrine_id": parent_doctrine_id,
        "immutable": False,   # set to True via adopt_doctrine()
        "adopted_at": None,
        "created_at": _now_iso(),
    }
```

### `_learning_episode_properties`

```python
def _learning_episode_properties(
    session_id: str,
    environment: str,
    coordinator: str,
    learning_type: str,
    *,
    source_id: str | None = None,
    turn_id: str | None = None,
    summary: str = "",
) -> Dict[str, Any]:
    if learning_type not in VALID_LEARNING_EPISODE_TYPES:
        raise ValueError(
            f"learning_type must be one of {sorted(VALID_LEARNING_EPISODE_TYPES)!r}, "
            f"got {learning_type!r}"
        )
    return {
        "session_id": str(session_id),
        "environment": environment,
        "coordinator": str(coordinator),
        "learning_type": learning_type,
        "source_id": source_id,
        "turn_id": turn_id,
        "summary": str(summary).strip(),
        "claim_count": 0,
        "created_at": _now_iso(),
    }
```

---

## Part 3: Create functions

All follow the same pattern as `create_goal`: generate a UUID ID, build props with the
`_*_properties` helper, `CREATE` the node, return the ID string.

### `create_source(driver, title, source_type, environment, *, url, author, summary) -> str`

Returns `source_id`.

```python
def create_source(
    driver,
    title: str,
    source_type: str,
    environment: str,
    *,
    url: str | None = None,
    author: str = "",
    summary: str = "",
) -> str:
    import uuid
    source_id = uuid.uuid4().hex
    props = _source_properties(title, source_type, environment, url=url,
                               author=author, summary=summary)
    props["source_id"] = source_id

    def write(tx):
        tx.run("CREATE (s:Source $props)", props=props)

    with _session(driver) as session:
        session.execute_write(write)
    return source_id
```

### `create_claim(driver, content, source_id, environment, coordinator, *, confidence, status) -> str`

Returns `claim_id`.

### `create_belief(driver, content, environment, *, confidence, status) -> str`

Returns `belief_id`.

### `create_principle(driver, content, environment, scope, *, status) -> str`

Returns `principle_id`.

### `create_doctrine(driver, content, environment, *, version, parent_doctrine_id, status) -> str`

Returns `doctrine_id`.

### `create_learning_episode(driver, session_id, environment, coordinator, learning_type, *, source_id, turn_id, summary) -> str`

Returns `learning_id`.

Write all six using the pattern shown for `create_source`. Node labels match function names:
`Source`, `Claim`, `Belief`, `Principle`, `Doctrine`, `LearningEpisode`.

---

## Part 4: Linking functions

These create directed relationships between nodes.
All follow the same guard pattern: MATCH both nodes by their ID + environment, then MERGE
the relationship (idempotent). Return `True` if both nodes matched, `False` if either was
absent.

### Chain links

```python
def link_learning_episode_to_source(driver, learning_id: str, source_id: str, environment: str) -> bool:
    """(LearningEpisode)-[:PROCESSED]->(Source)"""

def link_source_to_claim(driver, source_id: str, claim_id: str, environment: str) -> bool:
    """(Source)-[:YIELDS]->(Claim)"""

def link_learning_episode_to_claim(driver, learning_id: str, claim_id: str, environment: str) -> bool:
    """(LearningEpisode)-[:YIELDED]->(Claim)"""

def link_claim_to_belief(driver, claim_id: str, belief_id: str, environment: str) -> bool:
    """(Claim)-[:SUPPORTS]->(Belief); also increments belief.claim_count"""

def link_belief_to_principle(driver, belief_id: str, principle_id: str, environment: str) -> bool:
    """(Belief)-[:GROUNDS]->(Principle); also increments principle.belief_count"""

def link_principle_to_doctrine(driver, principle_id: str, doctrine_id: str, environment: str) -> bool:
    """(Principle)-[:INSTANTIATES]->(Doctrine)"""
```

For `link_claim_to_belief`: after MERGING the relationship, SET `belief.claim_count =
belief.claim_count + 1` and `belief.updated_at = $now_iso` only if the MERGE created a new
relationship (use `ON CREATE SET`).

For `link_belief_to_principle`: same — `ON CREATE SET principle.belief_count = principle.belief_count + 1`.

---

## Part 5: Status update functions

### `update_claim_status(driver, claim_id, environment, status, *, confidence=None) -> bool`

Validates `status` ∈ `VALID_CLAIM_STATUSES`. Updates `status`, `updated_at`, and optionally
`confidence`. Returns True if matched.

### `update_belief_status(driver, belief_id, environment, status, *, confidence=None) -> bool`

Same pattern for `VALID_BELIEF_STATUSES`.

### `update_principle_status(driver, principle_id, environment, status) -> bool`

Same for `VALID_PRINCIPLE_STATUSES`.

### `adopt_doctrine(driver, doctrine_id, environment) -> bool`

Sets `status = "active"`, `immutable = True`, `adopted_at = _now_iso()`. Returns True if matched.
Validates: if doctrine is already `immutable`, raises `ValueError("Doctrine is already adopted
and immutable")`.

### `deprecate_doctrine(driver, doctrine_id, environment) -> bool`

Sets `status = "deprecated"`. Does NOT mutate `content` or `immutable`. Returns True if matched.

---

## Part 6: Read functions

### `get_active_doctrines(driver, environment) -> list[dict]`

Returns all Doctrine nodes with `status = "active"` and `immutable = True`.
Returns `[]` on any exception. Results are properties dicts sorted by `adopted_at` ascending.

```python
def get_active_doctrines(driver, environment: str) -> list[dict]:
    def read(tx):
        result = tx.run(
            """
            MATCH (d:Doctrine {environment: $environment, status: 'active', immutable: true})
            RETURN properties(d) AS doctrine
            ORDER BY d.adopted_at ASC
            """,
            environment=environment,
        )
        return [dict(r["doctrine"]) for r in result]

    try:
        with _session(driver) as session:
            return session.execute_read(read)
    except Exception:
        return []
```

### `get_claims_for_source(driver, source_id, environment) -> list[dict]`

Returns all Claim nodes with `source_id` matching. Sorted by `created_at` descending.

### `get_beliefs_for_claim(driver, claim_id, environment) -> list[dict]`

Returns all Belief nodes that `(Claim)-[:SUPPORTS]->(Belief)` links to.

---

## Part 7: Tests — `tests/test_epistemic_chain.py` (new file)

All pure Python. Test property builders and validators directly — no Neo4j required.

**Valid-value validation:**
- `test_source_type_valid` — each value in `VALID_SOURCE_TYPES_EPISTEMIC` → no error
- `test_source_type_invalid` → `ValueError`
- `test_claim_status_valid` — all `VALID_CLAIM_STATUSES` → no error
- `test_claim_status_invalid` → `ValueError`
- `test_belief_status_invalid` → `ValueError`
- `test_principle_scope_invalid` → `ValueError`
- `test_principle_status_invalid` → `ValueError`
- `test_doctrine_status_invalid` → `ValueError`
- `test_learning_episode_type_invalid` → `ValueError`

**Property contents:**
- `test_source_properties_fields` — build source props, assert required keys present:
  title, source_type, environment, url, author, summary, status, created_at
- `test_claim_properties_confidence_clamped` — `confidence=1.5` → `props["confidence"] == 1.0`
- `test_claim_properties_confidence_floor` — `confidence=-0.1` → `props["confidence"] == 0.0`
- `test_claim_properties_default_status` — no status arg → `"candidate"`
- `test_belief_properties_default_status` — no status arg → `"forming"`
- `test_belief_properties_claim_count_zero` → `props["claim_count"] == 0`
- `test_principle_properties_scope_stored` — `scope="values"` → in props
- `test_doctrine_properties_version_floor` — `version=0` → `props["version"] == 1`
- `test_doctrine_properties_immutable_false_by_default` → `props["immutable"] is False`
- `test_doctrine_properties_parent_id` — `parent_doctrine_id="abc"` → in props
- `test_learning_episode_properties_fields` — all required keys present
- `test_learning_episode_properties_source_id_none_default` → `props["source_id"] is None`
- `test_learning_episode_properties_turn_id_stored` — `turn_id="xyz"` → in props

---

## Verification

```
pytest tests/test_epistemic_chain.py --basetemp .tmp/pytest_codex_task65 -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_codex_task65 -v
```

Confirm `world_models/config.py` is NOT staged:
```
git status
```

Commit:
```
git commit -m "feat: epistemic memory chain — Source/Claim/Belief/Principle/Doctrine + LearningEpisode (Task 65)"
```

---

## Summary of changes

| File | Change |
|---|---|
| `world_models/graph.py` | 7 new `VALID_*` sets; 6 `_*_properties` helpers; 6 `create_*` functions; 6 linking functions; 5 status-update functions including `adopt_doctrine` + `deprecate_doctrine`; 3 read functions |
| `tests/test_epistemic_chain.py` | New — ~22 pure-Python tests |

**Node labels added:** `Source`, `Claim`, `Belief`, `Principle`, `Doctrine`, `LearningEpisode`

**Relationship types added:** `PROCESSED`, `YIELDED`, `YIELDS`, `SUPPORTS`, `GROUNDS`, `INSTANTIATES`
