# Codex Task 51 — Coordinator Skill Layer: SkillNodes in Graph

## Context

Gopher-bot's coordinators currently have no mechanism to record which capabilities they have
practiced or how proficient they have become. A coordinator that successfully predicts topics
dozens of times should have a higher "prediction" skill than one that just started. A
coordinator that correctly applies retrieval dozens of times should have a measurable record.

This task adds **SkillNode** to `world_models/graph.py` — the graph schema for per-coordinator
practiced capability accumulation. The pattern follows the T65 epistemic chain exactly: valid-
value sets, a `_skill_properties` helper, `create_skill`, `record_skill_practice`, `get_*`
queries, and `update_skill_status`.

The coordinator wiring (which coordinators actually call `record_skill_practice` and when) is
a later enhancement. T51 builds the graph API layer only. Tests are pure Python (property
builder and validator tests) following the T65 pattern.

---

## Security invariant — check before every commit

`world_models/config.py` is gitignored and contains Neo4j credentials and API keys.
Run `git status` before committing. If `world_models/config.py` appears, STOP — do not commit.

---

## Part 1: Constants and valid-value sets

Add after the epistemic chain constants:

```python
# ---------------------------------------------------------------------------
# Skill node constants
# ---------------------------------------------------------------------------

SKILL_EMA_ALPHA = 0.2   # weight for newest practice event vs. history

VALID_SKILL_STATUSES = {
    "active",      # being practiced; tracked
    "dormant",     # coordinator no longer uses it actively
    "deprecated",  # removed from tracking; archived
}

VALID_SKILL_DOMAINS = {
    "prediction",         # predicting upcoming topics (Mirror-Self)
    "retrieval",          # knowledge retrieval accuracy (Memory)
    "reasoning",          # multi-step reasoning quality (Reason)
    "interaction",        # conversation shaping (Voice)
    "pattern_detection",  # anomaly and pattern identification (Pattern Monitor)
    "introspection",      # self-state accuracy (Mirror-Self, Mirror-Chad)
    "research",           # gap detection and knowledge synthesis (Curiosity, Archivist)
    "tool_use",           # Hands action success rate
}
```

---

## Part 2: `_skill_properties` helper

```python
def _skill_properties(
    coordinator: str,
    skill_name: str,
    domain: str,
    environment: str,
    *,
    initial_proficiency: float = 0.5,
    status: str = "active",
) -> Dict[str, Any]:
    """
    Build the property dict for a Skill node.

    Args:
        coordinator:         Name of the coordinator that owns this skill.
        skill_name:          Human-readable skill identifier (e.g., "topic_prediction").
        domain:              One of VALID_SKILL_DOMAINS.
        environment:         Graph environment scope.
        initial_proficiency: Starting proficiency (0.0–1.0, default 0.5).
        status:              One of VALID_SKILL_STATUSES (default "active").

    Returns:
        Property dict suitable for writing to Neo4j.

    Raises:
        ValueError: If domain or status is invalid.
    """
    if domain not in VALID_SKILL_DOMAINS:
        raise ValueError(
            f"domain must be one of {sorted(VALID_SKILL_DOMAINS)!r}, got {domain!r}"
        )
    if status not in VALID_SKILL_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(VALID_SKILL_STATUSES)!r}, got {status!r}"
        )
    return {
        "coordinator": str(coordinator).strip(),
        "skill_name": str(skill_name).strip(),
        "domain": domain,
        "environment": environment,
        "proficiency": _clamp_unit(float(initial_proficiency)),
        "status": status,
        "practice_count": 0,
        "success_count": 0,
        "created_at": _now_iso(),
        "last_practiced_at": None,
    }
```

---

## Part 3: `create_skill`

```python
def create_skill(
    driver,
    coordinator: str,
    skill_name: str,
    domain: str,
    environment: str,
    *,
    initial_proficiency: float = 0.5,
    status: str = "active",
) -> str:
    """
    Create a Skill node and return its skill_id.

    Skill nodes are per-coordinator capability records. They accumulate practice
    events via record_skill_practice() and update their proficiency via EMA.

    Returns:
        The skill_id (UUID hex string) of the new node.
    """
    import uuid
    skill_id = uuid.uuid4().hex
    props = _skill_properties(
        coordinator=coordinator,
        skill_name=skill_name,
        domain=domain,
        environment=environment,
        initial_proficiency=initial_proficiency,
        status=status,
    )
    props["skill_id"] = skill_id

    def write(tx):
        tx.run("CREATE (s:Skill $props)", props=props)

    with _session(driver) as session:
        session.execute_write(write)
    return skill_id
```

---

## Part 4: `record_skill_practice`

```python
def record_skill_practice(
    driver,
    skill_id: str,
    environment: str,
    *,
    success: bool,
) -> bool:
    """
    Record one practice event on a Skill node and update its proficiency via EMA.

    Each call:
    - Increments practice_count by 1
    - Increments success_count by 1 if success is True
    - Updates proficiency: SKILL_EMA_ALPHA * outcome + (1 - SKILL_EMA_ALPHA) * proficiency
      where outcome is 1.0 for success, 0.0 for failure
    - Updates last_practiced_at to now

    Args:
        driver:      Active Neo4j driver.
        skill_id:    Target Skill node.
        environment: Graph environment scope.
        success:     Whether this practice event was successful.

    Returns:
        True if the Skill node was found and updated; False if not found.
    """
    success_delta = 1 if success else 0
    success_val = 1.0 if success else 0.0
    now = _now_iso()

    def write(tx):
        result = tx.run(
            """
            MATCH (s:Skill {skill_id: $skill_id, environment: $environment})
            SET s.practice_count  = s.practice_count + 1,
                s.success_count   = s.success_count + $success_delta,
                s.proficiency     = $alpha * $success_val + (1.0 - $alpha) * s.proficiency,
                s.last_practiced_at = $now
            RETURN count(s) AS matched
            """,
            skill_id=skill_id,
            environment=environment,
            success_delta=success_delta,
            success_val=success_val,
            alpha=SKILL_EMA_ALPHA,
            now=now,
        )
        record = result.single()
        return bool(record and record["matched"] > 0)

    with _session(driver) as session:
        return session.execute_write(write)
```

---

## Part 5: Read functions

### `get_skills_for_coordinator`

```python
def get_skills_for_coordinator(
    driver,
    coordinator: str,
    environment: str,
    *,
    status: str | None = None,
) -> list[dict]:
    """
    Return all Skill nodes owned by a coordinator, sorted by proficiency descending.

    Args:
        coordinator: Name of the coordinator to query.
        environment: Graph environment scope.
        status:      Optional filter — only return skills with this status.
                     If None, returns all statuses.

    Returns:
        List of property dicts. Returns [] on any exception.
    """
    def read(tx):
        if status is not None:
            result = tx.run(
                """
                MATCH (s:Skill {coordinator: $coordinator, environment: $environment, status: $status})
                RETURN properties(s) AS skill
                ORDER BY s.proficiency DESC
                """,
                coordinator=coordinator,
                environment=environment,
                status=status,
            )
        else:
            result = tx.run(
                """
                MATCH (s:Skill {coordinator: $coordinator, environment: $environment})
                RETURN properties(s) AS skill
                ORDER BY s.proficiency DESC
                """,
                coordinator=coordinator,
                environment=environment,
            )
        return [dict(r["skill"]) for r in result]

    try:
        with _session(driver) as session:
            return session.execute_read(read)
    except Exception:
        return []
```

### `get_top_skills`

```python
def get_top_skills(
    driver,
    environment: str,
    *,
    limit: int = 10,
    domain: str | None = None,
) -> list[dict]:
    """
    Return top-N Skill nodes by proficiency across all coordinators.

    Args:
        driver:      Active Neo4j driver.
        environment: Graph environment scope.
        limit:       Max results (default 10).
        domain:      Optional domain filter.

    Returns:
        List of property dicts sorted by proficiency descending. [] on exception.
    """
    def read(tx):
        if domain is not None:
            result = tx.run(
                """
                MATCH (s:Skill {environment: $environment, status: 'active', domain: $domain})
                RETURN properties(s) AS skill
                ORDER BY s.proficiency DESC
                LIMIT $limit
                """,
                environment=environment,
                domain=domain,
                limit=limit,
            )
        else:
            result = tx.run(
                """
                MATCH (s:Skill {environment: $environment, status: 'active'})
                RETURN properties(s) AS skill
                ORDER BY s.proficiency DESC
                LIMIT $limit
                """,
                environment=environment,
                limit=limit,
            )
        return [dict(r["skill"]) for r in result]

    try:
        with _session(driver) as session:
            return session.execute_read(read)
    except Exception:
        return []
```

---

## Part 6: `update_skill_status`

```python
def update_skill_status(
    driver,
    skill_id: str,
    environment: str,
    status: str,
) -> bool:
    """
    Update the status of a Skill node.

    Args:
        driver:      Active Neo4j driver.
        skill_id:    Target Skill node.
        environment: Graph environment scope.
        status:      One of VALID_SKILL_STATUSES.

    Returns:
        True if matched and updated; False if not found.

    Raises:
        ValueError: If status is not in VALID_SKILL_STATUSES.
    """
    if status not in VALID_SKILL_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(VALID_SKILL_STATUSES)!r}, got {status!r}"
        )

    def write(tx):
        result = tx.run(
            """
            MATCH (s:Skill {skill_id: $skill_id, environment: $environment})
            SET s.status = $status
            RETURN count(s) AS matched
            """,
            skill_id=skill_id,
            environment=environment,
            status=status,
        )
        record = result.single()
        return bool(record and record["matched"] > 0)

    with _session(driver) as session:
        return session.execute_write(write)
```

---

## Part 7: Tests — `tests/test_skill_layer.py` (new file)

All pure Python. Test `_skill_properties` and validators directly — no Neo4j required.

**Valid-value validation:**
- `test_domain_valid` — each value in `VALID_SKILL_DOMAINS` → no error
- `test_domain_invalid` → `ValueError`
- `test_status_valid` — each value in `VALID_SKILL_STATUSES` → no error
- `test_status_invalid` → `ValueError`
- `test_update_skill_status_invalid` — call `update_skill_status` with bad status on a
  mock driver → `ValueError` raised before any driver call (driver not invoked)

**`_skill_properties` contents:**
- `test_properties_required_keys` — call with valid args; assert "coordinator", "skill_name",
  "domain", "environment", "proficiency", "status", "practice_count", "success_count",
  "created_at", "last_practiced_at" all in props
- `test_properties_practice_count_zero` → `props["practice_count"] == 0`
- `test_properties_success_count_zero` → `props["success_count"] == 0`
- `test_properties_last_practiced_none` → `props["last_practiced_at"] is None`
- `test_properties_proficiency_clamped_high` — `initial_proficiency=2.0` →
  `props["proficiency"] == 1.0`
- `test_properties_proficiency_clamped_low` — `initial_proficiency=-0.5` →
  `props["proficiency"] == 0.0`
- `test_properties_default_status_active` — no status arg → `props["status"] == "active"`
- `test_properties_domain_stored` — `domain="prediction"` → `props["domain"] == "prediction"`
- `test_properties_coordinator_stripped` — `coordinator="  mirror_self  "` →
  `props["coordinator"] == "mirror_self"`

**`SKILL_EMA_ALPHA` value:**
- `test_skill_ema_alpha_range` — `0.0 < SKILL_EMA_ALPHA < 1.0`

---

## Verification

```
pytest tests/test_skill_layer.py --basetemp .tmp/pytest_codex_task51 -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_codex_task51 -v
```

Confirm `world_models/config.py` is NOT staged:
```
git status
```

Commit:
```
git commit -m "feat: SkillNode graph schema — coordinator capability accumulation layer (Task 51)"
```

---

## Summary of changes

| File | Change |
|---|---|
| `world_models/graph.py` | `SKILL_EMA_ALPHA`, `VALID_SKILL_STATUSES`, `VALID_SKILL_DOMAINS`; `_skill_properties`; `create_skill`; `record_skill_practice`; `get_skills_for_coordinator`; `get_top_skills`; `update_skill_status` |
| `tests/test_skill_layer.py` | New — ~15 pure-Python tests |

**Node label added:** `Skill`
