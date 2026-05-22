# Codex Task 66 — Ethos Coordinator: Behavioral Update Mechanism for Doctrine Nodes

## Context

Task 65 built the full epistemic chain (Source→Claim→Belief→Principle→Doctrine) and the
`get_active_doctrines` graph function. Doctrine nodes adopted in the graph now exist, but
nothing reads them at runtime. Without a runtime injection mechanism, Doctrine nodes are
dead data — they exist in the graph but never influence Reason.

This task builds the **Ethos coordinator**: a lightweight foreground coordinator that reads
active Doctrine nodes from the graph and injects them into the pipeline as behavioral
constraints before Reason runs. Ethos is the runtime actuator for the epistemic chain.

The Archivist (Task 50) will handle the *creation* side — extracting Claims, promoting
Beliefs, proposing Principles and Doctrines. Ethos only handles the *consumption* side:
read active (immutable) Doctrines and make Reason aware of them.

Pipeline position: Orientation → Keeper → Mirror-Self → **Ethos** → Reason

---

## Security invariant — check before every commit

`world_models/config.py` is gitignored and contains Neo4j credentials and API keys.
Run `git status` before committing. If `world_models/config.py` appears, STOP — do not commit.

---

## Part 1: `coordinators/ethos.py` — new file

### Constants

```python
ETHOS_PRIORITY = 2          # bid priority — higher than Mirror-Self (3), below safety
ETHOS_CADENCE_SECONDS = 300 # background tick cadence (reserved; currently no-op)
ETHOS_MAX_DOCTRINES = 10    # maximum doctrines to inject per turn (cap for context length)
```

### `EthosBid` frozen dataclass

```python
@dataclass(frozen=True)
class EthosBid:
    coordinator_name: str
    content: str
    priority: int
    timestamp: float
    source: str = "ethos"
    type: str = "doctrine_signal"
```

### `_default_doctrine_reader(environment: str) -> list[dict]`

Module-level function. Connects to Neo4j, calls `graph.get_active_doctrines`, returns the
list. On any exception returns `[]`. Closes the driver in a `finally` block.

```python
def _default_doctrine_reader(environment: str) -> list[dict]:
    try:
        from world_models import graph
        driver = graph.connect()
        try:
            return graph.get_active_doctrines(driver, environment)
        finally:
            graph.close(driver)
    except Exception:
        return []
```

### `_format_doctrine_context(doctrines: list[dict]) -> str`

```python
def _format_doctrine_context(doctrines: list[dict]) -> str:
    """Format active Doctrine nodes as a memory-context block for Reason."""
    if not doctrines:
        return ""
    lines = ["Active behavioral doctrines (immutable; adopted):"]
    for d in doctrines:
        content = str(d.get("content") or "").strip()
        version = d.get("version", 1)
        scope_hint = str(d.get("scope") or "").strip()
        if not content:
            continue
        tag = f"[v{version}]" + (f" [{scope_hint}]" if scope_hint else "")
        lines.append(f"- {tag} {content}")
    if len(lines) == 1:
        return ""   # header only, no content
    return "\n".join(lines).strip()
```

### `Ethos` class

```python
class Ethos(Coordinator):
    name = "ethos"

    def __init__(
        self,
        doctrine_reader: Callable[[str], list[dict]] | None = None,
    ) -> None:
        self.doctrine_reader = doctrine_reader or _default_doctrine_reader
        self.last_doctrine_count: int = 0

    def process(self, packet: dict) -> dict:
        """
        Read active Doctrine nodes and inject them as behavioral constraints.

        Adds to packet:
            doctrine_context       (str)  — formatted list of active doctrines; "" if none
            active_doctrine_count  (int)  — number of doctrines loaded this turn
        Appends to:
            memory_context         (str)  — doctrine_context is appended (same pattern as
                                            keeper_context and orientation_context)
        """
        environment = str(packet.get("environment") or "global")
        try:
            doctrines = self.doctrine_reader(environment)
        except Exception:
            doctrines = []

        # Cap at ETHOS_MAX_DOCTRINES to avoid bloating the context window.
        doctrines = doctrines[:ETHOS_MAX_DOCTRINES]
        self.last_doctrine_count = len(doctrines)

        doctrine_context = _format_doctrine_context(doctrines)
        packet["doctrine_context"] = doctrine_context
        packet["active_doctrine_count"] = self.last_doctrine_count

        if doctrine_context:
            memory_context = str(packet.get("memory_context") or "").strip()
            packet["memory_context"] = (
                f"{memory_context}\n\n{doctrine_context}"
                if memory_context
                else doctrine_context
            )
        return packet

    async def background_tick(self, awareness_queue) -> None:
        """Reserved for future Archivist-triggered doctrine promotion signals."""
        return None
```

---

## Part 2: Wire Ethos into `coordinators/awareness.py`

### Import

```python
from coordinators.ethos import Ethos
```

### `Awareness.__init__` — add `ethos` parameter

```python
def __init__(
    self,
    ...,
    ethos: Ethos | Coordinator | None = None,
) -> None:
    ...
    self.ethos = ethos or Ethos()
```

### `synchronous_run` — insert after Mirror-Self block, before Reason

```python
# --- Ethos: behavioral doctrine injection --------------------------------
# Runs after Mirror-Self (prediction state) and before Reason (needs all
# behavioral context). Reads active immutable Doctrine nodes from graph
# and injects them as doctrine_context into memory_context.
try:
    packet = self.ethos.process(packet)
except Exception:
    pass  # Ethos failure is non-fatal — pipeline continues without doctrine context
# -------------------------------------------------------------------------
```

The pipeline position is: Orientation → Keeper → Mirror-Self → **Ethos** → Reason.

---

## Part 3: Update `COORDINATOR_REGISTRY.md`

Add Ethos after the Keeper entry. Follow the exact table format of existing entries.

Key fields:
- **name:** `ethos`
- **Status:** Active — built (`coordinators/ethos.py`)
- **Model tier:** Tier 0 — no LLM calls; reads Neo4j graph at foreground turn start
- **Primary role:** Behavioral doctrine injection. Reads adopted (immutable) Doctrine nodes
  from the epistemic memory chain and injects them as behavioral constraints into
  `memory_context` before Reason runs.
- **Foreground position:** After Mirror-Self, before Reason
- **Background cadence:** None (reserved — no-op `background_tick`)
- **Notes:** Consumption side of the epistemic chain only. Archivist (T50) handles
  creation (LearningEpisode, Source, Claim, Belief, Principle promotion). Ethos only
  reads `status='active', immutable=True` Doctrine nodes.

---

## Part 4: Tests — `tests/test_ethos.py` (new file)

All pure Python. Use an injectable `doctrine_reader` — no Neo4j, no disk.

**`_format_doctrine_context`:**
- `test_format_empty_list` — `[]` → `""`
- `test_format_single_doctrine` — one doctrine dict with content → formatted string contains content
- `test_format_includes_version_tag` — `version=2` → `"[v2]"` in output
- `test_format_skips_empty_content` — doctrine with `content=""` → skipped; result is `""`
- `test_format_multiple_doctrines` — 3 doctrines → all appear in output

**`Ethos.process`:**
- `test_ethos_no_doctrines_adds_empty_context` — reader returns `[]` →
  `packet["doctrine_context"] == ""`, `packet["active_doctrine_count"] == 0`
- `test_ethos_doctrines_appended_to_memory_context` — reader returns 1 doctrine, packet has
  `memory_context="prior context"` → final `memory_context` contains both "prior context"
  and doctrine content
- `test_ethos_no_doctrines_does_not_clobber_memory_context` — reader returns `[]`, packet has
  `memory_context="prior context"` → `memory_context` unchanged ("prior context")
- `test_ethos_active_doctrine_count` — reader returns 3 doctrines →
  `packet["active_doctrine_count"] == 3`
- `test_ethos_reader_exception_graceful` — reader raises `RuntimeError` → packet returned
  without exception; `packet["active_doctrine_count"] == 0`
- `test_ethos_caps_at_max_doctrines` — reader returns 15 doctrines →
  `packet["active_doctrine_count"] == ETHOS_MAX_DOCTRINES` (10)
- `test_ethos_returns_packet` — `process(packet)` returns same packet dict object

**Awareness wiring:**
- `test_awareness_has_ethos_attribute` — `Awareness()` → `hasattr(awareness, "ethos")` is True
- `test_awareness_ethos_injectable` — pass `ethos=mock_ethos` to `Awareness()`; mock records
  its `process()` call; call `awareness.synchronous_run("hello")`; assert mock was called

---

## Verification

```
pytest tests/test_ethos.py --basetemp .tmp/pytest_codex_task66 -v
pytest tests/test_awareness_orientation.py --basetemp .tmp/pytest_codex_task66 -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_codex_task66 -v
```

Confirm `world_models/config.py` is NOT staged:
```
git status
```

Commit:
```
git commit -m "feat: Ethos coordinator — behavioral doctrine injection from epistemic chain (Task 66)"
```

---

## Summary of changes

| File | Change |
|---|---|
| `coordinators/ethos.py` | New file — Ethos coordinator; `ETHOS_PRIORITY`, `ETHOS_MAX_DOCTRINES`; `EthosBid`; `_default_doctrine_reader`; `_format_doctrine_context`; `Ethos.process` + no-op `background_tick` |
| `coordinators/awareness.py` | Add `ethos` param to `__init__`; wire into `synchronous_run` after Mirror-Self, before Reason |
| `COORDINATOR_REGISTRY.md` | Register Ethos |
| `tests/test_ethos.py` | New — ~14 unit tests |
