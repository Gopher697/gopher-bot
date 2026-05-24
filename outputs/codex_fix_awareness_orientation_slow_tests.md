# Codex Task — Fix Slow tests/test_awareness_orientation.py

## Problem

`tests/test_awareness_orientation.py` takes ~44 seconds per test, causing full suite runs
to time out. Root cause: `_make_awareness()` only passes `sensory`, `memory`, `reason`,
`voice`, and `orientation` as noop coordinators. `Awareness.__init__` still instantiates
real `Keeper`, `MirrorUser`, `MirrorSelf`, `Ethos`, and `Drive` for every test. At least
one of these (most likely `Ethos`, which reads Doctrine nodes from Neo4j) hits a connection
timeout on every construction.

## Fix — tests/test_awareness_orientation.py only

No production code changes. Test isolation fix only.

### Step 1: Update `_make_awareness()`

Replace the existing helper:

```python
def _make_awareness(orientation=None, memory=None) -> Awareness:
    """Minimal Awareness with noop coordinators, no external calls."""
    return Awareness(
        sensory=_NoopCoordinator(),
        memory=memory or _NoopCoordinator(),
        reason=_NoopCoordinator(),
        voice=_NoopCoordinator(),
        orientation=orientation or _MockOrientation(),
    )
```

With:

```python
def _make_awareness(orientation=None, memory=None) -> Awareness:
    """Minimal Awareness with all noop coordinators — no external calls, no Neo4j."""
    return Awareness(
        sensory=_NoopCoordinator(),
        memory=memory or _NoopCoordinator(),
        reason=_NoopCoordinator(),
        voice=_NoopCoordinator(),
        orientation=orientation or _MockOrientation(),
        keeper=_NoopCoordinator(),
        mirror_user=_NoopCoordinator(),
        mirror_self=_NoopCoordinator(),
        ethos=_NoopCoordinator(),
        drive=_NoopCoordinator(),
    )
```

### Step 2: Update `test_awareness_instantiates_orientation_by_default`

This test currently constructs `Awareness` with only 4 noop coordinators, letting real
coordinators instantiate. Update it to also pass all optional coordinators as noops:

```python
def test_awareness_instantiates_orientation_by_default():
    aw = Awareness(
        sensory=_NoopCoordinator(),
        memory=_NoopCoordinator(),
        reason=_NoopCoordinator(),
        voice=_NoopCoordinator(),
        keeper=_NoopCoordinator(),
        mirror_user=_NoopCoordinator(),
        mirror_self=_NoopCoordinator(),
        ethos=_NoopCoordinator(),
        drive=_NoopCoordinator(),
        # orientation intentionally omitted — testing that it defaults to a real Orientation
    )
    assert aw.orientation is not None
```

This still tests what it claims to test (that `orientation` defaults to a real `Orientation`
instance) while preventing all other real coordinators from instantiating.

---

## Verification

```
pytest tests/test_awareness_orientation.py -v
```

All 11 tests should pass and the full file should complete in under 5 seconds.

Then run:

```
pytest --ignore=tests/test_graph.py -v
```

The full suite should now complete without timing out.

---

## Security invariant

Run `git status` before committing. If `world_models/config.py` appears, STOP.

## Commit

```
git commit -m "fix: isolate awareness_orientation tests from real coordinator init (Ethos/Neo4j timeout)"
```
