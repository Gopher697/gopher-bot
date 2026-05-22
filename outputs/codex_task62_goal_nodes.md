# Codex Task 62 — Goal Node Graph Substrate

## Context

You are building the Goal node system for Gopher-bot's neurosymbolic knowledge graph. This is **graph substrate only** — no salience scoring, no Orientation intelligence, no coordinator wiring. Those come in Task 63.

**Gopher-bot is a persistent AI companion**, not a session-bounded chatbot. Goals exist on a condition-scoped horizon (thread/project/standing/exploratory), not time-scoped. A "thread" is a coherent conversational focus; a "standing" goal persists indefinitely.

The AI determines its own goals autonomously. User input can raise confidence in a goal candidate (evidence), but does NOT gate promotion from candidate→active. The three-score gate (confidence + salience + permissibility) is the AI's own evaluation — Task 63 will implement it. Task 62 provides the graph storage layer only.

**Files to modify:**
- `world_models/graph.py` — append all new constants and functions (do not modify existing code)

**Files to create:**
- `tests/test_goal_schema.py` — non-graph validation tests only (no Neo4j required)

**Do not modify:** any other file. Do not create additional files.

---

## Graph.py additions

### 1. Constants — append after the existing constants block (after `MIN_CONSOLIDATION_VARIANCE`)

```python
# ---------------------------------------------------------------------------
# Goal node constants
# ---------------------------------------------------------------------------

VALID_GOAL_STATUSES = {
    "candidate",    # not yet promoted — AI is evaluating
    "active",       # promoted — AI is pursuing this
    "completed",    # success_condition met
    "abandoned",    # no longer worth pursuing (AI decision)
    "deferred",     # temporarily suspended, review_after set
    "dormant",      # low salience, standing goal not currently active
    "rejected",     # failed permissibility or confidence gate at promotion
}

VALID_GOAL_HORIZONS = {
    "thread",         # scoped to the current conversational focus
    "project",        # spans multiple threads / a discrete work arc
    "standing",       # persistent indefinitely (maintenance, identity, values)
    "exploratory",    # open-ended, no fixed success condition required
}

VALID_GOAL_AUTHORITY_SCOPES = {
    "internal_self_maintenance",      # memory hygiene, self-monitoring, upkeep
    "curiosity_exploration",          # learning, research, question-forming
    "memory_hygiene",                 # graph consolidation, pruning, dedup
    "user_project_support",           # helping Gopher with his explicit goals
    "user_affecting_recommendation",  # advice that changes what Gopher does
    "external_action",                # anything Hands executes in the world
}

VALID_GOAL_VISIBILITIES = {
    "private_internal",           # never shown to user; shapes internal behavior
    "surfaced_when_relevant",     # mentioned if it affects a response
    "user_visible",               # in dashboard / readable on request
    "requires_disclosure",        # MUST be disclosed (see disclosure_trigger)
}

VALID_GOAL_DISCLOSURE_TRIGGERS = {
    "on_reasoning_influence",  # disclose when goal shapes a reasoning path
    "on_recommendation",       # disclose when goal underlies a recommendation
    "on_conflict",             # disclose when goal conflicts with user preference
    "on_action_request",       # disclose before requesting Hands permission
}

VALID_GOAL_ACTION_BOUNDARIES = {
    "observe_only",    # can notice but not act
    "reason_only",     # can reason but not output or act
    "suggest",         # can surface suggestions to user
    "ask_permission",  # can request explicit Hands escalation
    "act",             # can direct Hands to act (high trust required)
}

VALID_GOAL_RISK_LEVELS = {"low", "medium", "high"}

VALID_GOAL_CHARTER_ALIGNMENTS = {"true", "false", "uncertain"}

VALID_GOAL_LIFECYCLE_ANCHORS = {
    "thread_closure",          # resolve when the current thread ends
    "success_condition",       # resolve when success_condition is met
    "standing_maintenance",    # never auto-closes; standing goal
    "salience_opportunity",    # resolve when a relevant moment appears
}

VALID_GOAL_SOURCES = {
    "self_generated",          # AI originated the goal autonomously
    "inferred_from_context",   # AI inferred from conversation context
    "user_stated",             # user explicitly stated this as a goal
    "user_confirmed",          # user confirmed a goal the AI surfaced
}

# Legal status transition graph — only these moves are permitted
_GOAL_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "candidate":  {"active", "rejected", "abandoned"},
    "active":     {"completed", "abandoned", "deferred", "dormant"},
    "deferred":   {"active", "abandoned"},
    "dormant":    {"active", "abandoned"},
    "completed":  set(),   # terminal
    "abandoned":  set(),   # terminal
    "rejected":   set(),   # terminal
}

DEFAULT_MAX_CANDIDATE_AGE_SECONDS: float = 7 * 24 * 3600  # 7 days
```

---

### 2. `_validate_goal_fields()` — private helper, append after the constants block

```python
def _validate_goal_fields(fields: dict) -> None:
    """
    Validate all Goal node fields before create or update.

    Raises ValueError with a descriptive message on any violation.
    """
    def _check(value, valid_set, field_name):
        if value not in valid_set:
            raise ValueError(
                f"{field_name} must be one of {sorted(valid_set)!r}, "
                f"got {value!r}"
            )

    _check(fields.get("status"), VALID_GOAL_STATUSES, "status")
    _check(fields.get("horizon"), VALID_GOAL_HORIZONS, "horizon")
    _check(fields.get("authority_scope"), VALID_GOAL_AUTHORITY_SCOPES, "authority_scope")
    _check(fields.get("visibility"), VALID_GOAL_VISIBILITIES, "visibility")
    _check(fields.get("action_boundary"), VALID_GOAL_ACTION_BOUNDARIES, "action_boundary")
    _check(fields.get("risk_level"), VALID_GOAL_RISK_LEVELS, "risk_level")
    _check(
        fields.get("charter_alignment"),
        VALID_GOAL_CHARTER_ALIGNMENTS,
        "charter_alignment",
    )
    _check(fields.get("lifecycle_anchor"), VALID_GOAL_LIFECYCLE_ANCHORS, "lifecycle_anchor")
    _check(fields.get("source"), VALID_GOAL_SOURCES, "source")

    # Disclosure trigger: required iff visibility == requires_disclosure
    visibility = fields.get("visibility")
    disclosure_trigger = fields.get("disclosure_trigger")
    if visibility == "requires_disclosure":
        if disclosure_trigger not in VALID_GOAL_DISCLOSURE_TRIGGERS:
            raise ValueError(
                "disclosure_trigger is required when visibility='requires_disclosure'; "
                f"must be one of {sorted(VALID_GOAL_DISCLOSURE_TRIGGERS)!r}, "
                f"got {disclosure_trigger!r}"
            )
    else:
        if disclosure_trigger is not None:
            raise ValueError(
                "disclosure_trigger must be None unless visibility='requires_disclosure'"
            )

    # success_condition: required and non-empty for non-exploratory goals
    success_condition = fields.get("success_condition", "")
    horizon = fields.get("horizon")
    if horizon != "exploratory" and not (
        isinstance(success_condition, str) and success_condition.strip()
    ):
        raise ValueError(
            "success_condition is required and must be non-empty for "
            f"horizon={horizon!r}"
        )

    # Numeric range checks
    for float_field in ("confidence", "priority"):
        val = fields.get(float_field)
        if val is not None:
            try:
                fval = float(val)
            except (TypeError, ValueError):
                raise ValueError(f"{float_field} must be a float, got {val!r}")
            if not (0.0 <= fval <= 1.0):
                raise ValueError(
                    f"{float_field} must be in [0.0, 1.0], got {fval!r}"
                )
```

---

### 3. `create_goal()` — public API

```python
def create_goal(
    driver,
    content: str,
    environment: str,
    horizon: str,
    authority_scope: str,
    visibility: str,
    action_boundary: str,
    risk_level: str,
    charter_alignment: str,
    charter_basis: str,
    lifecycle_anchor: str,
    source: str,
    success_condition: str = "",
    status: str = "candidate",
    priority: float = 0.5,
    confidence: float = 0.5,
    disclosure_trigger: Optional[str] = None,
    expires_at: Optional[str] = None,
    review_after: Optional[str] = None,
    current_next_action: Optional[str] = None,
    thread_id: Optional[str] = None,
    project_id: Optional[str] = None,
    max_candidate_age_seconds: float = DEFAULT_MAX_CANDIDATE_AGE_SECONDS,
) -> str:
    """
    Create a Goal node in the graph and return its goal_id.

    All enum fields are validated before writing. Raises ValueError on
    invalid input.

    Args:
        driver:                   Active Neo4j driver.
        content:                  Natural-language description of the goal.
        environment:              Graph environment scope.
        horizon:                  Condition-scoped horizon — one of VALID_GOAL_HORIZONS.
        authority_scope:          What the AI is permitted to do in pursuit of this goal.
        visibility:               How visible this goal is to the user.
        action_boundary:          Maximum action the AI may take for this goal.
        risk_level:               Assessed risk level.
        charter_alignment:        Whether this goal is charter-aligned.
        charter_basis:            Auditable text basis for charter_alignment.
        lifecycle_anchor:         What event closes this goal.
        source:                   How this goal originated.
        success_condition:        When is this goal met? Required for non-exploratory goals.
        status:                   Initial status (default 'candidate').
        priority:                 Intent weight 0–1 (stored; not salience).
        confidence:               Epistemic confidence this is a real goal, 0–1.
        disclosure_trigger:       Required iff visibility='requires_disclosure'.
        expires_at:               Optional ISO-8601 hard expiry timestamp.
        review_after:             Optional ISO-8601 earliest review timestamp.
        current_next_action:      Optional text of the next concrete step.
        thread_id:                Optional FK to a conversational thread.
        project_id:               Optional FK to a project arc.
        max_candidate_age_seconds: Seconds before a candidate may be decayed.

    Returns:
        The goal_id (UUID hex string) of the new Goal node.
    """
    import uuid

    fields = {
        "status": status,
        "horizon": horizon,
        "authority_scope": authority_scope,
        "visibility": visibility,
        "action_boundary": action_boundary,
        "risk_level": risk_level,
        "charter_alignment": charter_alignment,
        "lifecycle_anchor": lifecycle_anchor,
        "source": source,
        "success_condition": success_condition,
        "disclosure_trigger": disclosure_trigger,
        "confidence": confidence,
        "priority": priority,
    }
    _validate_goal_fields(fields)

    goal_id = uuid.uuid4().hex
    now = _now_iso()

    props: Dict[str, Any] = {
        "goal_id": goal_id,
        "content": content,
        "environment": environment,
        "status": status,
        "horizon": horizon,
        "authority_scope": authority_scope,
        "visibility": visibility,
        "action_boundary": action_boundary,
        "risk_level": risk_level,
        "charter_alignment": charter_alignment,
        "charter_basis": charter_basis,
        "lifecycle_anchor": lifecycle_anchor,
        "source": source,
        "success_condition": success_condition,
        "priority": float(priority),
        "confidence": float(confidence),
        "staleness_state": "fresh",
        "disclosure_trigger": disclosure_trigger,
        "expires_at": expires_at,
        "review_after": review_after,
        "current_next_action": current_next_action,
        "thread_id": thread_id,
        "project_id": project_id,
        "max_candidate_age_seconds": float(max_candidate_age_seconds),
        "created_at": now,
        "updated_at": now,
        "last_checked_at": now,
        "last_advanced_at": None,
        "candidate_since": now if status == "candidate" else None,
        # Promotion audit trail (null until promoted)
        "promotion_summary": None,
        "promotion_evidence": None,
        "promoted_by": None,
        "promoted_at": None,
        "promotion_rule_version": None,
    }

    def write(tx):
        tx.run(
            "CREATE (g:Goal $props)",
            props=props,
        )

    with _session(driver) as session:
        session.execute_write(write)

    return goal_id
```

---

### 4. `get_active_goals()` — returns active and dormant goals

```python
def get_active_goals(
    driver,
    environment: str,
    limit: int = 20,
) -> list[dict]:
    """
    Return Goal nodes with status 'active' or 'dormant', ordered by priority desc.

    Salience scoring (Task 63) will re-rank these at query time. This function
    returns stored priority only.

    Args:
        driver:      Active Neo4j driver.
        environment: Graph environment scope.
        limit:       Maximum number of results (default 20).

    Returns:
        List of property dicts for matching Goal nodes.
    """
    def read(tx):
        result = tx.run(
            """
            MATCH (g:Goal {environment: $environment})
            WHERE g.status IN ['active', 'dormant']
            RETURN properties(g) AS props
            ORDER BY g.priority DESC
            LIMIT $limit
            """,
            environment=environment,
            limit=limit,
        )
        return [record["props"] for record in result]

    with _session(driver) as session:
        return session.execute_read(read)
```

---

### 5. `get_candidate_goals()` — returns goals awaiting promotion

```python
def get_candidate_goals(
    driver,
    environment: str,
    limit: int = 20,
) -> list[dict]:
    """
    Return Goal nodes with status 'candidate', ordered by confidence desc.

    Used by Orientation (Task 63) to evaluate the promotion gate.

    Args:
        driver:      Active Neo4j driver.
        environment: Graph environment scope.
        limit:       Maximum number of results (default 20).

    Returns:
        List of property dicts for matching Goal nodes.
    """
    def read(tx):
        result = tx.run(
            """
            MATCH (g:Goal {environment: $environment, status: 'candidate'})
            RETURN properties(g) AS props
            ORDER BY g.confidence DESC
            LIMIT $limit
            """,
            environment=environment,
            limit=limit,
        )
        return [record["props"] for record in result]

    with _session(driver) as session:
        return session.execute_read(read)
```

---

### 6. `transition_goal_status()` — enforces legal state machine

```python
def transition_goal_status(
    driver,
    goal_id: str,
    environment: str,
    new_status: str,
    promoted_by: Optional[str] = None,
    promotion_summary: Optional[str] = None,
    promotion_evidence: Optional[str] = None,
    promotion_rule_version: Optional[str] = None,
) -> bool:
    """
    Transition a Goal node to a new status, enforcing the legal state machine.

    Raises ValueError if:
    - new_status is not a valid status
    - the current→new transition is not permitted

    Args:
        driver:                  Active Neo4j driver.
        goal_id:                 UUID hex of the goal to transition.
        environment:             Graph environment scope.
        new_status:              Target status.
        promoted_by:             If transitioning to 'active', name of the promoting coordinator.
        promotion_summary:       If transitioning to 'active', brief rationale.
        promotion_evidence:      If transitioning to 'active', evidence string.
        promotion_rule_version:  If transitioning to 'active', rule version used.

    Returns:
        True if the goal was found and transitioned; False if not found.

    Raises:
        ValueError: if new_status is invalid or the transition is illegal.
    """
    if new_status not in VALID_GOAL_STATUSES:
        raise ValueError(
            f"new_status must be one of {sorted(VALID_GOAL_STATUSES)!r}, "
            f"got {new_status!r}"
        )

    def write(tx):
        # Fetch current status first
        result = tx.run(
            """
            MATCH (g:Goal {goal_id: $goal_id, environment: $environment})
            RETURN g.status AS current_status
            """,
            goal_id=goal_id,
            environment=environment,
        )
        record = result.single()
        if record is None:
            return None

        current_status = record["current_status"]
        allowed = _GOAL_STATUS_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition Goal from {current_status!r} to {new_status!r}. "
                f"Allowed transitions from {current_status!r}: {sorted(allowed)!r}"
            )

        now = _now_iso()
        set_clauses = "g.status = $new_status, g.updated_at = $now"
        params: dict = {
            "goal_id": goal_id,
            "environment": environment,
            "new_status": new_status,
            "now": now,
        }

        if new_status == "active":
            set_clauses += (
                ", g.promoted_at = $now"
                ", g.promoted_by = $promoted_by"
                ", g.promotion_summary = $promotion_summary"
                ", g.promotion_evidence = $promotion_evidence"
                ", g.promotion_rule_version = $promotion_rule_version"
            )
            params["promoted_by"] = promoted_by
            params["promotion_summary"] = promotion_summary
            params["promotion_evidence"] = promotion_evidence
            params["promotion_rule_version"] = promotion_rule_version

        tx.run(
            f"MATCH (g:Goal {{goal_id: $goal_id, environment: $environment}}) "
            f"SET {set_clauses} "
            f"RETURN g.goal_id",
            **params,
        )
        return True

    with _session(driver) as session:
        result = session.execute_write(write)
        return result is True
```

---

### 7. `update_goal()` — mutate allowed fields only

```python
# Fields that may be updated after creation
_GOAL_MUTABLE_FIELDS = {
    "content",
    "priority",
    "confidence",
    "staleness_state",
    "current_next_action",
    "success_condition",
    "expires_at",
    "review_after",
    "charter_basis",
    "thread_id",
    "project_id",
    "last_advanced_at",
    "last_checked_at",
}

def update_goal(
    driver,
    goal_id: str,
    environment: str,
    updates: Dict[str, Any],
) -> bool:
    """
    Update mutable fields on an existing Goal node.

    Only fields in _GOAL_MUTABLE_FIELDS may be updated. Enum fields that are
    being updated are re-validated. `updated_at` is always refreshed.

    Args:
        driver:      Active Neo4j driver.
        goal_id:     UUID hex of the goal to update.
        environment: Graph environment scope.
        updates:     Dict of field→value to write.

    Returns:
        True if the goal was found and updated; False if not found.

    Raises:
        ValueError: if any key in updates is not a mutable field, or if
                    confidence/priority are out of range.
    """
    if not updates:
        return False

    immutable_keys = set(updates.keys()) - _GOAL_MUTABLE_FIELDS
    if immutable_keys:
        raise ValueError(
            f"Cannot update immutable fields: {sorted(immutable_keys)!r}. "
            f"Mutable fields: {sorted(_GOAL_MUTABLE_FIELDS)!r}"
        )

    # Validate numeric ranges if being updated
    for float_field in ("confidence", "priority"):
        if float_field in updates:
            val = updates[float_field]
            try:
                fval = float(val)
            except (TypeError, ValueError):
                raise ValueError(f"{float_field} must be a float, got {val!r}")
            if not (0.0 <= fval <= 1.0):
                raise ValueError(
                    f"{float_field} must be in [0.0, 1.0], got {fval!r}"
                )
            updates[float_field] = fval

    updates["updated_at"] = _now_iso()

    def write(tx):
        result = tx.run(
            """
            MATCH (g:Goal {goal_id: $goal_id, environment: $environment})
            SET g += $updates
            RETURN g.goal_id AS goal_id
            """,
            goal_id=goal_id,
            environment=environment,
            updates=updates,
        )
        return result.single() is not None

    with _session(driver) as session:
        return session.execute_write(write)
```

---

### 8. `decay_stale_candidates()` — condition-aware staleness check (Python-side, not Cypher duration)

```python
def decay_stale_candidates(
    driver,
    environment: str,
) -> list[str]:
    """
    Mark stale/expired candidate goals and transition expired ones to 'rejected'.

    Staleness logic (all computed in Python, not Cypher duration arithmetic):
    - A candidate becomes 'stale' if age >= max_candidate_age_seconds / 2.
    - A candidate becomes 'expired' (→ 'rejected') if:
      - age >= max_candidate_age_seconds, OR
      - expires_at is set and has passed.

    Does NOT touch active/deferred/dormant goals — they have their own
    lifecycle anchors and are managed by Orientation (Task 63).

    Args:
        driver:      Active Neo4j driver.
        environment: Graph environment scope.

    Returns:
        List of goal_ids that were transitioned to 'rejected' this run.
    """
    from datetime import datetime, timezone

    def write(tx):
        result = tx.run(
            """
            MATCH (g:Goal {environment: $environment, status: 'candidate'})
            RETURN g.goal_id AS goal_id,
                   g.candidate_since AS candidate_since,
                   g.expires_at AS expires_at,
                   g.max_candidate_age_seconds AS max_age,
                   g.staleness_state AS staleness_state
            """,
            environment=environment,
        )
        rows = result.data()

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat(timespec="seconds")
        rejected: list[str] = []

        for row in rows:
            goal_id = row["goal_id"]
            candidate_since_str = row.get("candidate_since")
            expires_at_str = row.get("expires_at")
            max_age = float(row.get("max_age") or DEFAULT_MAX_CANDIDATE_AGE_SECONDS)
            current_staleness = row.get("staleness_state", "fresh")

            # Parse candidate_since
            age_seconds = None
            if candidate_since_str:
                try:
                    cs = datetime.fromisoformat(candidate_since_str)
                    if cs.tzinfo is None:
                        cs = cs.replace(tzinfo=timezone.utc)
                    age_seconds = (now - cs).total_seconds()
                except (ValueError, TypeError):
                    age_seconds = None

            # Check hard expiry
            hard_expired = False
            if expires_at_str:
                try:
                    exp = datetime.fromisoformat(expires_at_str)
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=timezone.utc)
                    hard_expired = now >= exp
                except (ValueError, TypeError):
                    pass

            # Determine new state
            age_expired = age_seconds is not None and age_seconds >= max_age
            age_stale = age_seconds is not None and age_seconds >= max_age / 2.0

            if hard_expired or age_expired:
                # Transition to rejected
                tx.run(
                    """
                    MATCH (g:Goal {goal_id: $goal_id, environment: $environment})
                    SET g.status = 'rejected',
                        g.staleness_state = 'expired',
                        g.updated_at = $now
                    """,
                    goal_id=goal_id,
                    environment=environment,
                    now=now_iso,
                )
                rejected.append(goal_id)
            elif age_stale and current_staleness == "fresh":
                tx.run(
                    """
                    MATCH (g:Goal {goal_id: $goal_id, environment: $environment})
                    SET g.staleness_state = 'stale',
                        g.updated_at = $now
                    """,
                    goal_id=goal_id,
                    environment=environment,
                    now=now_iso,
                )

        return rejected

    with _session(driver) as session:
        return session.execute_write(write)
```

---

### 9. `link_goals()` — DEPENDS_ON / BLOCKED_BY relationships

```python
VALID_GOAL_REL_TYPES = {"DEPENDS_ON", "BLOCKED_BY"}


def link_goals(
    driver,
    from_goal_id: str,
    to_goal_id: str,
    environment: str,
    rel_type: str,
) -> None:
    """
    Create a directional relationship between two Goal nodes.

    Supported rel_types:
    - DEPENDS_ON: from_goal logically depends on to_goal
    - BLOCKED_BY: from_goal cannot advance until to_goal resolves

    Uses MERGE so re-linking is idempotent.

    Args:
        driver:        Active Neo4j driver.
        from_goal_id:  goal_id of the source Goal.
        to_goal_id:    goal_id of the target Goal.
        environment:   Graph environment scope (both goals must share it).
        rel_type:      One of VALID_GOAL_REL_TYPES.

    Raises:
        ValueError: if rel_type is not in VALID_GOAL_REL_TYPES.
    """
    if rel_type not in VALID_GOAL_REL_TYPES:
        raise ValueError(
            f"rel_type must be one of {sorted(VALID_GOAL_REL_TYPES)!r}, "
            f"got {rel_type!r}"
        )

    def write(tx):
        tx.run(
            f"""
            MATCH (a:Goal {{goal_id: $from_id, environment: $environment}})
            MATCH (b:Goal {{goal_id: $to_id, environment: $environment}})
            MERGE (a)-[:{rel_type}]->(b)
            """,
            from_id=from_goal_id,
            to_id=to_goal_id,
            environment=environment,
        )

    with _session(driver) as session:
        session.execute_write(write)
```

---

### 10. `link_episode_to_goal()` — SPAWNED / ADVANCES relationships

```python
VALID_EPISODE_GOAL_REL_TYPES = {"SPAWNED", "ADVANCES"}


def link_episode_to_goal(
    driver,
    episode_id: str,
    goal_id: str,
    environment: str,
    rel_type: str,
) -> None:
    """
    Create a directional relationship from an Episode node to a Goal node.

    Supported rel_types:
    - SPAWNED:  the Episode caused this Goal to be created
    - ADVANCES: the Episode made progress toward this Goal

    Uses MERGE so re-linking is idempotent.

    Args:
        driver:      Active Neo4j driver.
        episode_id:  episode_id of the source Episode.
        goal_id:     goal_id of the target Goal.
        environment: Graph environment scope (both nodes must share it).
        rel_type:    One of VALID_EPISODE_GOAL_REL_TYPES.

    Raises:
        ValueError: if rel_type is not in VALID_EPISODE_GOAL_REL_TYPES.
    """
    if rel_type not in VALID_EPISODE_GOAL_REL_TYPES:
        raise ValueError(
            f"rel_type must be one of {sorted(VALID_EPISODE_GOAL_REL_TYPES)!r}, "
            f"got {rel_type!r}"
        )

    def write(tx):
        tx.run(
            f"""
            MATCH (e:Episode {{episode_id: $episode_id, environment: $environment}})
            MATCH (g:Goal {{goal_id: $goal_id, environment: $environment}})
            MERGE (e)-[:{rel_type}]->(g)
            """,
            episode_id=episode_id,
            goal_id=goal_id,
            environment=environment,
        )

    with _session(driver) as session:
        session.execute_write(write)
```

---

## Test file: `tests/test_goal_schema.py`

Create this file from scratch. These tests exercise **validation logic only** — no Neo4j connection required. All tests must pass with `pytest tests/test_goal_schema.py`.

```python
"""
tests/test_goal_schema.py

Non-graph validation tests for the Goal node substrate (Task 62).
No Neo4j connection required — tests _validate_goal_fields() and
the transition state machine logic.
"""
from __future__ import annotations

import pytest

from world_models.graph import (
    _validate_goal_fields,
    _GOAL_STATUS_TRANSITIONS,
    VALID_GOAL_STATUSES,
    VALID_GOAL_HORIZONS,
    VALID_GOAL_AUTHORITY_SCOPES,
    VALID_GOAL_VISIBILITIES,
    VALID_GOAL_DISCLOSURE_TRIGGERS,
    VALID_GOAL_ACTION_BOUNDARIES,
    VALID_GOAL_RISK_LEVELS,
    VALID_GOAL_CHARTER_ALIGNMENTS,
    VALID_GOAL_LIFECYCLE_ANCHORS,
    VALID_GOAL_SOURCES,
    DEFAULT_MAX_CANDIDATE_AGE_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_fields(**overrides) -> dict:
    """Return a complete, valid fields dict, optionally overriding keys."""
    base = {
        "status": "candidate",
        "horizon": "thread",
        "authority_scope": "curiosity_exploration",
        "visibility": "private_internal",
        "action_boundary": "reason_only",
        "risk_level": "low",
        "charter_alignment": "true",
        "lifecycle_anchor": "success_condition",
        "source": "self_generated",
        "success_condition": "Understand the user's current project goal.",
        "disclosure_trigger": None,
        "confidence": 0.7,
        "priority": 0.5,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Test 1-9: enum validation — one bad value per field
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field,bad_value", [
    ("status",            "unknown"),
    ("horizon",           "session"),        # 'session' was deliberately removed
    ("authority_scope",   "do_anything"),
    ("visibility",        "hidden"),
    ("action_boundary",   "block"),
    ("risk_level",        "critical"),
    ("charter_alignment", "yes"),
    ("lifecycle_anchor",  "never"),
    ("source",            "magic"),
])
def test_invalid_enum_fields(field, bad_value):
    fields = _valid_fields(**{field: bad_value})
    with pytest.raises(ValueError, match=field):
        _validate_goal_fields(fields)


# ---------------------------------------------------------------------------
# Test 10: valid baseline passes without error
# ---------------------------------------------------------------------------

def test_valid_baseline_passes():
    _validate_goal_fields(_valid_fields())  # must not raise


# ---------------------------------------------------------------------------
# Test 11: requires_disclosure without trigger raises
# ---------------------------------------------------------------------------

def test_disclosure_trigger_required_when_requires_disclosure():
    fields = _valid_fields(
        visibility="requires_disclosure",
        disclosure_trigger=None,
    )
    with pytest.raises(ValueError, match="disclosure_trigger"):
        _validate_goal_fields(fields)


# ---------------------------------------------------------------------------
# Test 12: requires_disclosure with valid trigger passes
# ---------------------------------------------------------------------------

def test_disclosure_trigger_with_requires_disclosure_passes():
    fields = _valid_fields(
        visibility="requires_disclosure",
        disclosure_trigger="on_recommendation",
    )
    _validate_goal_fields(fields)  # must not raise


# ---------------------------------------------------------------------------
# Test 13: disclosure_trigger set without requires_disclosure raises
# ---------------------------------------------------------------------------

def test_disclosure_trigger_without_requires_disclosure_raises():
    fields = _valid_fields(
        visibility="user_visible",
        disclosure_trigger="on_recommendation",
    )
    with pytest.raises(ValueError, match="disclosure_trigger"):
        _validate_goal_fields(fields)


# ---------------------------------------------------------------------------
# Test 14: empty success_condition raises for non-exploratory horizon
# ---------------------------------------------------------------------------

def test_empty_success_condition_raises_for_non_exploratory():
    for horizon in ("thread", "project", "standing"):
        fields = _valid_fields(horizon=horizon, success_condition="")
        with pytest.raises(ValueError, match="success_condition"):
            _validate_goal_fields(fields)


# ---------------------------------------------------------------------------
# Test 15: exploratory horizon allows empty success_condition
# ---------------------------------------------------------------------------

def test_exploratory_allows_empty_success_condition():
    fields = _valid_fields(horizon="exploratory", success_condition="")
    _validate_goal_fields(fields)  # must not raise


# ---------------------------------------------------------------------------
# Test 16: confidence out of range raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("val", [-0.01, 1.01, 2.0, -1.0])
def test_confidence_out_of_range(val):
    fields = _valid_fields(confidence=val)
    with pytest.raises(ValueError, match="confidence"):
        _validate_goal_fields(fields)


# ---------------------------------------------------------------------------
# Test 17: priority out of range raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("val", [-0.01, 1.01])
def test_priority_out_of_range(val):
    fields = _valid_fields(priority=val)
    with pytest.raises(ValueError, match="priority"):
        _validate_goal_fields(fields)


# ---------------------------------------------------------------------------
# Test 18: terminal statuses have no outgoing transitions
# ---------------------------------------------------------------------------

def test_terminal_statuses_have_no_transitions():
    for terminal in ("completed", "abandoned", "rejected"):
        assert _GOAL_STATUS_TRANSITIONS[terminal] == set(), (
            f"Terminal status {terminal!r} should have no outgoing transitions"
        )


# ---------------------------------------------------------------------------
# Test 19: candidate may transition to active, rejected, or abandoned only
# ---------------------------------------------------------------------------

def test_candidate_transitions():
    allowed = _GOAL_STATUS_TRANSITIONS["candidate"]
    assert allowed == {"active", "rejected", "abandoned"}


# ---------------------------------------------------------------------------
# Test 20: active may transition to completed, abandoned, deferred, dormant
# ---------------------------------------------------------------------------

def test_active_transitions():
    allowed = _GOAL_STATUS_TRANSITIONS["active"]
    assert allowed == {"completed", "abandoned", "deferred", "dormant"}


# ---------------------------------------------------------------------------
# Test 21: DEFAULT_MAX_CANDIDATE_AGE_SECONDS is 7 days
# ---------------------------------------------------------------------------

def test_default_max_candidate_age_is_seven_days():
    assert DEFAULT_MAX_CANDIDATE_AGE_SECONDS == 7 * 24 * 3600


# ---------------------------------------------------------------------------
# Test 22: 'session' is not a valid horizon (persistent AI correction)
# ---------------------------------------------------------------------------

def test_session_not_a_valid_horizon():
    assert "session" not in VALID_GOAL_HORIZONS


# ---------------------------------------------------------------------------
# Test 23: all four horizons are present
# ---------------------------------------------------------------------------

def test_all_four_horizons_present():
    assert VALID_GOAL_HORIZONS == {
        "thread", "project", "standing", "exploratory"
    }
```

---

## Cypher index (add to `world_models/setup_graph.py` or equivalent)

If a `setup_graph.py` or `setup_indexes.py` file exists in `world_models/`, append these index creation statements. If no such file exists, create a comment block in graph.py above the Goal constants noting the indexes that should be created manually:

```cypher
CREATE INDEX goal_id_idx IF NOT EXISTS FOR (g:Goal) ON (g.goal_id);
CREATE INDEX goal_env_status_idx IF NOT EXISTS FOR (g:Goal) ON (g.environment, g.status);
CREATE INDEX goal_env_horizon_idx IF NOT EXISTS FOR (g:Goal) ON (g.environment, g.horizon);
```

If a setup file exists, add the indexes there as Cypher executed via the driver (follow the existing pattern). If it does not exist, only add the comment block in graph.py — do not create new setup files.

---

## Commit instructions

After all tests pass with:
```
pytest tests/test_goal_schema.py --basetemp .tmp/pytest_codex_task62 -v
```

Commit with:
```
git add world_models/graph.py tests/test_goal_schema.py
git commit -m "feat: Goal node graph substrate — create_goal, transitions, decay, link functions (Task 62)"
```

**Do not stage world_models/config.py.** Verify with `git status` before committing.

---

## Summary of what gets built

| Item | Location | Notes |
|---|---|---|
| 10 constant sets | `world_models/graph.py` | VALID_GOAL_*, _GOAL_STATUS_TRANSITIONS, DEFAULT_MAX_CANDIDATE_AGE_SECONDS |
| `_validate_goal_fields()` | `world_models/graph.py` | Private; raises ValueError |
| `create_goal()` | `world_models/graph.py` | Returns goal_id (UUID hex) |
| `get_active_goals()` | `world_models/graph.py` | Returns active + dormant, sorted by priority |
| `get_candidate_goals()` | `world_models/graph.py` | Returns candidates, sorted by confidence |
| `transition_goal_status()` | `world_models/graph.py` | Enforces _GOAL_STATUS_TRANSITIONS |
| `update_goal()` | `world_models/graph.py` | Mutable fields only; validates numeric ranges |
| `decay_stale_candidates()` | `world_models/graph.py` | Python-side age math; returns rejected goal_ids |
| `link_goals()` | `world_models/graph.py` | DEPENDS_ON / BLOCKED_BY; MERGE (idempotent) |
| `link_episode_to_goal()` | `world_models/graph.py` | SPAWNED / ADVANCES; MERGE (idempotent) |
| `tests/test_goal_schema.py` | `tests/` | 23 non-graph tests; no Neo4j required |

Task 63 (Orientation coordinator) is blocked until this task is committed and tests pass.
