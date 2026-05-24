# Codex Task — Fix Awareness noop isolation across all test files

## Problem

`Awareness.__init__` has 10 optional coordinator parameters. When a test only passes 4–5
of them, the rest are instantiated as real coordinators — including `Ethos` (reads Neo4j)
and `Drive`. In a test environment without Neo4j running, this causes 30–45 second timeouts
per `Awareness(...)` construction.

The fix in `tests/test_awareness_orientation.py` (commit 045e209) confirmed this: going
from partial to full noop isolation dropped 45s → 1.46s for the full file.

The same pattern exists across 9 more test files.

---

## Approach

### Step 1 — Add a shared helper to `tests/conftest.py`

Create `tests/conftest.py` (or append to it if it already exists) with a factory function
that returns a fully-isolated `Awareness`:

```python
"""Shared test helpers — loaded automatically by pytest."""
from __future__ import annotations

from coordinators.awareness import Awareness
from coordinators.base import Coordinator


class _Noop(Coordinator):
    """Noop coordinator for test isolation."""
    name = "noop"

    def process(self, packet: dict) -> dict:
        return packet


# All optional coordinator kwargs wired to noops.
# Use this dict in every Awareness(...) construction that doesn't need real coordinators.
_NOOP_EXTRAS = {
    "keeper": None,       # replaced at call time — see isolated_awareness()
    "mirror_user": None,
    "mirror_self": None,
    "ethos": None,
    "drive": None,
}


def isolated_awareness(**overrides) -> Awareness:
    """
    Return an Awareness with all optional coordinators set to noops.
    Pass keyword overrides to substitute specific coordinators under test.

    Example:
        aw = isolated_awareness(keeper=real_keeper)
    """
    kwargs = dict(
        keeper=_Noop(),
        mirror_user=_Noop(),
        mirror_self=_Noop(),
        ethos=_Noop(),
        drive=_Noop(),
    )
    kwargs.update(overrides)
    return Awareness(**kwargs)
```

### Step 2 — Update each affected test file

For each file below, the fix is the same: every `Awareness(...)` construction that is
missing `ethos=`, `drive=`, `keeper=`, `mirror_user=`, or `mirror_self=` must have them
added as noops. Use the file's existing noop class if one exists; otherwise add
`from tests.conftest import isolated_awareness` and replace the bare construction.

**Do NOT change any test logic, assertions, or coordinator-specific kwargs.** Only add
the missing isolation kwargs.

---

### tests/test_coordinators.py

This file has many `Awareness(...)` constructions. Each one that is missing the five
isolation kwargs needs them added. The file likely has its own noop/stub coordinator
class already — use that. If not, add:

```python
class _Noop(Coordinator):
    name = "noop"
    def process(self, packet: dict) -> dict:
        return packet
```

Then for every `Awareness(sensory=..., memory=..., reason=..., voice=...)` call, add:
```python
keeper=_Noop(),
mirror_user=_Noop(),
mirror_self=_Noop(),
ethos=_Noop(),
drive=_Noop(),
```

Special cases in this file:
- `Awareness()` (bare, no args) — also needs all five added
- `Awareness(voice=None, memory=None, sensory=None)` — add the five kwargs

---

### tests/test_awareness_mirror_user.py

The `_make_awareness()` helper (or inline `Awareness(...)`) is missing the five isolation
kwargs. Add them.

---

### tests/test_ethos.py

Two patterns:
1. `_make_awareness(ethos=...)` helper — add the four remaining isolation kwargs
   (`keeper`, `mirror_user`, `mirror_self`, `drive`) to the `Awareness(...)` inside it.
   Keep the `ethos=` parameter wired through from the caller.
2. `Awareness()` bare in `test_awareness_has_ethos_attribute` — this test only needs to
   assert `hasattr(awareness, "ethos")`. Replace with:
   ```python
   aw = isolated_awareness()   # import from conftest
   assert hasattr(aw, "ethos")
   ```
   This still passes because `isolated_awareness()` constructs a real `Awareness` and
   `ethos` is always set in `__init__`.

---

### tests/test_hands.py

`Awareness(sensory=..., memory=..., ...)` constructions are missing the five kwargs.
The file likely already has a noop/fake coordinator class — use it. Add the five kwargs
to every `Awareness(...)` call.

---

### tests/test_keeper.py

Two `Awareness(sensory=..., memory=..., ...)` constructions — add the five isolation
kwargs to each. Keep the `keeper=` kwarg that is already being explicitly tested.

---

### tests/test_inner_defender.py

Multiple patterns:
- `Awareness()` bare — two occurrences. Add all five kwargs.
- `Awareness(sensory=FakeCoord(), memory=FakeCoord(), reason=FakeCoord(), voice=FakeCoord())`
  — three occurrences. Add the five kwargs using `FakeCoord()` or whichever noop is defined
  in this file.

---

### tests/test_brain_loop.py

`Awareness(voice=FakeVoice(), bid_queue=BidQueue())` and similar — missing most coordinators.
Add the five isolation kwargs. The file likely has a fake/noop coordinator class.

---

### tests/test_turn_log.py

`Awareness(sensory=Noop(), memory=Noop(), ...)` — add `keeper`, `mirror_user`,
`mirror_self`, `ethos`, `drive` as `Noop()` (using whatever noop class is already defined).

---

### tests/test_feeling.py

Multiple `Awareness(sensory=..., memory=..., ...)` constructions. Add the five isolation
kwargs. Use the file's existing fake/step coordinator class.

---

### tests/test_mirror_self.py

`Awareness(sensory=Noop(), memory=Noop(), ...)` — add the five isolation kwargs.

---

## What NOT to change

- Do not modify any production code.
- Do not remove or change any test assertions.
- Do not change coordinator-specific kwargs that are intentionally under test
  (e.g., `keeper=real_keeper` in keeper tests, `ethos=mock_ethos` in ethos tests).
- Do not modify `tests/test_awareness_orientation.py` — already fixed in 045e209.
- Do not modify `tests/test_graph.py` — excluded from the standard suite.

---

## Verification

```
pytest tests/test_coordinators.py -v
pytest tests/test_awareness_mirror_user.py -v
pytest tests/test_ethos.py -v
pytest tests/test_hands.py -v
pytest tests/test_keeper.py -v
pytest tests/test_inner_defender.py -v
pytest tests/test_brain_loop.py -v
pytest tests/test_turn_log.py -v
pytest tests/test_feeling.py -v
pytest tests/test_mirror_self.py -v
```

All should pass. Then run the full suite:

```
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_noop_isolation -v
```

This should complete in under 2 minutes.

---

## Security invariant

`git status` before commit — `world_models/config.py` must not appear.

## Commit

```
git commit -m "fix: full noop isolation for Awareness construction across all test files"
```
