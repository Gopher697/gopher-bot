from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from neo4j import GraphDatabase

from world_models import config


MEDIA_TYPES = {"image", "screenshot", "document", "audio"}
VALID_SOURCE_TYPES = {"observed", "inferred", "proposed", "external_content"}
VALID_EPISODE_TYPES = {"utterance", "reasoning", "action", "observation_group"}
VALID_CURATION_LABELS = {"keep", "skip", "review"}
DEFAULT_EDGE_WEIGHT: float = 1.0
DEFAULT_CONSOLIDATION_VARIANCE: float = 1.0   # σ²_ij; decreases as evidence accumulates
MIN_CONSOLIDATION_VARIANCE: float = 0.01      # floor to avoid division by zero

# ---------------------------------------------------------------------------
# Goal node constants
#
# Manual Neo4j indexes for Goal nodes:
#   CREATE INDEX goal_id_idx IF NOT EXISTS FOR (g:Goal) ON (g.goal_id);
#   CREATE INDEX goal_env_status_idx IF NOT EXISTS FOR (g:Goal) ON (g.environment, g.status);
#   CREATE INDEX goal_env_horizon_idx IF NOT EXISTS FOR (g:Goal) ON (g.environment, g.horizon);
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

REL_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _session(driver):
    return driver.session(database=config.NEO4J_DATABASE)


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


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


def _entity_properties(
    name: str,
    entity_type: str,
    environment: str,
    properties: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    base = {
        "name": name,
        "entity_type": entity_type,
        "environment": environment,
        "created_at": _now_iso(),
        "status": "active",
    }
    if properties:
        base.update(properties)
    return base


def _merge_names(entity_names: Optional[Iterable[str]]) -> List[str]:
    if not entity_names:
        return []
    return list(dict.fromkeys(entity_names))


def _observation_properties(
    content: str,
    environment: str,
    coordinator: str,
    confidence: float = 1.0,
    source_type: str = "observed",
) -> Dict[str, Any]:
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(
            f"source_type must be one of {sorted(VALID_SOURCE_TYPES)!r}, "
            f"got {source_type!r}"
        )
    return {
        "content": content,
        "environment": environment,
        "coordinator": coordinator,
        "confidence": float(confidence),
        "source_type": source_type,
        "created_at": _now_iso(),
        "status": "active",
        "training_candidate": None,
    }


def _episode_properties(
    episode_type: str,
    content: str,
    session_id: str,
    environment: str,
    coordinator: str,
    source_type: str = "observed",
    *,
    # Utterance-specific
    tts_generated: bool = False,
    # Reasoning-specific
    accepted: bool = False,
    score: float | None = None,
    # Training corpus fields (T54/T55)
    predicted_topic: str | None = None,
    actual_topic: str | None = None,
    prediction_accuracy: float | None = None,
    curation_label: str | None = None,
    turn_id: str | None = None,
) -> Dict[str, Any]:
    """
    Build the property dict for an Episode node.

    Utterance episodes are immutable ground truth — what Voice said to Gopher.
    Reasoning episodes record coordinator deliberation that was never expressed.

    Args:
        episode_type:  One of VALID_EPISODE_TYPES.
        content:       The text content of the episode.
        session_id:    UUID hex of the current BrainLoop session.
        environment:   Graph environment scope.
        coordinator:   Name of the coordinator that produced this episode.
                       Must be "voice" for utterance episodes.
        source_type:   One of VALID_SOURCE_TYPES (default "observed").
        tts_generated: Utterance only — was TTS audio actually generated?
        accepted:      Reasoning only — was this bid accepted by Awareness?
        score:         Optional training-corpus score (None until curated).

    Returns:
        Property dict suitable for writing to Neo4j.

    Raises:
        ValueError: If episode_type or source_type is invalid, or if
                    coordinator != "voice" for an utterance episode.
    """
    if episode_type not in VALID_EPISODE_TYPES:
        raise ValueError(
            f"episode_type must be one of {sorted(VALID_EPISODE_TYPES)!r}, "
            f"got {episode_type!r}"
        )
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(
            f"source_type must be one of {sorted(VALID_SOURCE_TYPES)!r}, "
            f"got {source_type!r}"
        )
    if episode_type == "utterance" and coordinator != "voice":
        raise ValueError(
            f"Utterance episodes must have coordinator='voice', "
            f"got {coordinator!r}"
        )
    if curation_label is not None and curation_label not in VALID_CURATION_LABELS:
        raise ValueError(
            f"curation_label must be one of {sorted(VALID_CURATION_LABELS)!r} "
            f"or None, got {curation_label!r}"
        )

    immutable = episode_type == "utterance"

    props: Dict[str, Any] = {
        "episode_type": episode_type,
        "content": content,
        "session_id": session_id,
        "environment": environment,
        "coordinator": coordinator,
        "source_type": source_type,
        "immutable": immutable,
        "created_at": _now_iso(),
        "status": "active",
        # Utterance fields
        "tts_generated": tts_generated if episode_type == "utterance" else False,
        # Reasoning fields
        "accepted": accepted if episode_type == "reasoning" else False,
        "score": score,
        # Training corpus fields
        "predicted_topic": predicted_topic,
        "actual_topic": actual_topic,
        "prediction_accuracy": prediction_accuracy,
        "curation_label": curation_label,
        "turn_id": str(turn_id) if turn_id is not None else None,
    }
    return props


def connect():
    return GraphDatabase.driver(
        config.NEO4J_URI,
        auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
    )


def add_entity(driver, name, entity_type, environment, properties=None):
    props = _entity_properties(name, entity_type, environment, properties)

    def write(tx):
        result = tx.run(
            """
            CREATE (entity:Entity)
            SET entity = $props
            RETURN elementId(entity) AS element_id
            """,
            props=props,
        )
        record = result.single()
        return record["element_id"]

    with _session(driver) as session:
        return session.execute_write(write)


def add_observation(
    driver,
    content,
    environment,
    coordinator,
    confidence=1.0,
    entity_names=None,
    source_type="observed",
):
    props = _observation_properties(
        content, environment, coordinator, confidence, source_type
    )
    names = _merge_names(entity_names)

    def write(tx):
        result = tx.run(
            """
            CREATE (observation:Observation)
            SET observation = $props
            RETURN elementId(observation) AS element_id
            """,
            props=props,
        )
        record = result.single()
        element_id = record["element_id"]
        if names:
            tx.run(
                """
                MATCH (observation:Observation)
                WHERE elementId(observation) = $element_id
                WITH observation
                UNWIND $entity_names AS entity_name
                MATCH (entity:Entity {name: entity_name, environment: $environment})
                MERGE (observation)-[:OBSERVED]->(entity)
                """,
                element_id=element_id,
                environment=environment,
                entity_names=names,
            )
        return element_id

    with _session(driver) as session:
        return session.execute_write(write)


def add_episode(
    driver,
    episode_type: str,
    content: str,
    session_id: str,
    environment: str,
    coordinator: str,
    source_type: str = "observed",
    tts_generated: bool = False,
    accepted: bool = False,
    score: float | None = None,
    predicted_topic: str | None = None,
    actual_topic: str | None = None,
    prediction_accuracy: float | None = None,
    curation_label: str | None = None,
    turn_id: str | None = None,
) -> str:
    """
    Add an Episode node to the graph and return its episode_id.

    Episode nodes record events that occurred within a session. Two types:

    - **utterance**: what Voice said to Gopher (immutable ground truth).
      coordinator must be "voice". Carries tts_generated flag.
    - **reasoning**: coordinator deliberation not expressed to Gopher.
      Carries accepted flag (was the bid accepted by Awareness?).

    Args:
        driver:        Active Neo4j driver.
        episode_type:  One of VALID_EPISODE_TYPES.
        content:       Text content of the episode.
        session_id:    UUID hex of the current BrainLoop session.
        environment:   Graph environment scope.
        coordinator:   Name of the producing coordinator.
        source_type:   One of VALID_SOURCE_TYPES (default "observed").
        tts_generated: Utterance only — was audio generated?
        accepted:      Reasoning only — was the bid accepted?
        score:         Optional float for training curation (None by default).

    Returns:
        The episode_id (UUID hex string) of the new node.
    """
    import uuid
    episode_id = uuid.uuid4().hex

    props = _episode_properties(
        episode_type=episode_type,
        content=content,
        session_id=session_id,
        environment=environment,
        coordinator=coordinator,
        source_type=source_type,
        tts_generated=tts_generated,
        accepted=accepted,
        score=score,
        predicted_topic=predicted_topic,
        actual_topic=actual_topic,
        prediction_accuracy=prediction_accuracy,
        curation_label=curation_label,
        turn_id=turn_id,
    )
    props["episode_id"] = episode_id

    def write(tx):
        tx.run(
            """
            CREATE (e:Episode $props)
            """,
            props=props,
        )

    with _session(driver) as session:
        session.execute_write(write)

    return episode_id


def add_utterance(
    driver,
    content: str,
    session_id: str,
    environment: str,
    tts_generated: bool = False,
    predicted_topic: str | None = None,
    actual_topic: str | None = None,
    prediction_accuracy: float | None = None,
    curation_label: str | None = None,
    turn_id: str | None = None,
) -> str:
    """
    Convenience wrapper: add an immutable Utterance episode node.

    Utterance episodes are what Voice actually said to Gopher. They are
    ground truth — coordinator is always "voice", immutable is always True.

    Args:
        driver:        Active Neo4j driver.
        content:       The exact text Voice output to Gopher.
        session_id:    UUID hex of the current BrainLoop session.
        environment:   Graph environment scope.
        tts_generated: Was TTS audio actually generated for this output?

    Returns:
        The episode_id of the new Utterance node.
    """
    return add_episode(
        driver=driver,
        episode_type="utterance",
        content=content,
        session_id=session_id,
        environment=environment,
        coordinator="voice",
        source_type="observed",
        tts_generated=tts_generated,
        predicted_topic=predicted_topic,
        actual_topic=actual_topic,
        prediction_accuracy=prediction_accuracy,
        curation_label=curation_label,
        turn_id=turn_id,
    )


def curate_episode(
    driver,
    episode_id: str,
    environment: str,
    *,
    score: float | None = None,
    curation_label: str | None = None,
) -> bool:
    """
    Update the training curation fields on an existing Episode node.

    Called post-hoc when a human or automated process labels an episode
    for inclusion in or exclusion from the training corpus.

    Args:
        driver:         Active Neo4j driver.
        episode_id:     The episode_id of the target node.
        environment:    Graph environment scope (used to scope the match).
        score:          Optional float (0.0-1.0) quality score.
        curation_label: One of VALID_CURATION_LABELS or None (leave unchanged).

    Returns:
        True if a node was matched and updated, False if not found.
    """
    if curation_label is not None and curation_label not in VALID_CURATION_LABELS:
        raise ValueError(
            f"curation_label must be one of {sorted(VALID_CURATION_LABELS)!r} "
            "or None"
        )

    updates: dict[str, Any] = {}
    if score is not None:
        updates["score"] = float(score)
    if curation_label is not None:
        updates["curation_label"] = curation_label

    if not updates:
        return False

    def write(tx):
        result = tx.run(
            """
            MATCH (e:Episode {episode_id: $episode_id, environment: $environment})
            SET e += $updates
            RETURN count(e) AS matched
            """,
            episode_id=episode_id,
            environment=environment,
            updates=updates,
        )
        record = result.single()
        return bool(record and record["matched"] > 0)

    with _session(driver) as session:
        return session.execute_write(write)


def delete_observation(
    driver,
    content: str,
    environment: str,
) -> bool:
    """
    Hard-delete an Observation node and its embedding from the graph.

    Because the embedding is stored as a property on the node itself,
    Neo4j's vector index cascade removes the embedding entry automatically
    when the node is deleted. No separate vector-index sync is required.

    Args:
        driver:      Active Neo4j driver.
        content:     Exact content string of the observation to delete.
        environment: Graph environment scope.

    Returns:
        True if a node was found and deleted, False if not found.
    """
    def write(tx):
        result = tx.run(
            """
            MATCH (observation:Observation {
                content: $content,
                environment: $environment
            })
            WITH observation, elementId(observation) AS eid
            DETACH DELETE observation
            RETURN eid
            """,
            content=content,
            environment=environment,
        )
        return result.single() is not None

    with _session(driver) as session:
        return session.execute_write(write)


def get_recent_observations(
    driver,
    environment: str,
    hours: float = 24.0,
) -> list[dict]:
    """
    Return Observation nodes created within the last `hours` hours.

    Used by Dream NREM to identify recent observations for consolidation.
    Returns nodes in ascending created_at order (oldest first).

    ISO-8601 strings sort lexicographically in the same order as the
    timestamps they represent, so string comparison is safe here.

    Args:
        driver:      Active Neo4j driver.
        environment: Graph environment scope.
        hours:       Look-back window in hours (default 24.0).

    Returns:
        List of property dicts for matching Observation nodes.
    """
    from datetime import datetime, timezone, timedelta

    since = (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).isoformat()

    def read(tx):
        result = tx.run(
            """
            MATCH (observation:Observation {environment: $environment})
            WHERE coalesce(observation.status, 'active') = 'active'
              AND observation.created_at >= $since
            RETURN properties(observation) AS observation
            ORDER BY observation.created_at ASC
            """,
            environment=environment,
            since=since,
        )
        return [record["observation"] for record in result]

    with _session(driver) as session:
        return session.execute_read(read)


def record_system_event(
    driver,
    event_type: str,
    environment: str,
    details: str = "",
) -> None:
    """
    Record a SystemEvent node in the graph.

    SystemEvent nodes are Dream's persistent memory of its own operational
    history — startup, shutdown, NREM completion, NREM skips. They survive
    process restarts and allow Dream to reason about how long it was offline.

    Args:
        driver:      Active Neo4j driver.
        event_type:  Short identifier: "startup", "shutdown", "nrem_complete",
                     "nrem_skipped".
        environment: Graph environment scope.
        details:     Optional free-text detail string (e.g. counts summary).
    """
    def write(tx):
        tx.run(
            """
            CREATE (e:SystemEvent {
                event_type: $event_type,
                environment: $environment,
                timestamp:   $timestamp,
                details:     $details
            })
            """,
            event_type=event_type,
            environment=environment,
            timestamp=_now_iso(),
            details=details,
        )

    with _session(driver) as session:
        session.execute_write(write)


def get_last_system_event(
    driver,
    event_type: str,
    environment: str,
) -> dict | None:
    """
    Return the most recent SystemEvent of the given type, or None.

    Used by Dream on startup to determine how long it was offline and
    whether NREM is overdue.

    Args:
        driver:      Active Neo4j driver.
        event_type:  Event type to query (e.g. "nrem_complete").
        environment: Graph environment scope.

    Returns:
        Property dict of the most recent matching event, or None.
    """
    def read(tx):
        result = tx.run(
            """
            MATCH (e:SystemEvent {
                event_type: $event_type,
                environment: $environment
            })
            RETURN properties(e) AS event
            ORDER BY e.timestamp DESC
            LIMIT 1
            """,
            event_type=event_type,
            environment=environment,
        )
        record = result.single()
        return record["event"] if record else None

    with _session(driver) as session:
        return session.execute_read(read)


def add_media(
    driver,
    file_path,
    media_type,
    environment,
    coordinator,
    description="",
    entity_names=None,
):
    if media_type not in MEDIA_TYPES:
        raise ValueError(
            'media_type must be one of: "image", "screenshot", "document", "audio"'
        )

    props = {
        "file_path": file_path,
        "media_type": media_type,
        "environment": environment,
        "coordinator": coordinator,
        "description": description,
        "created_at": _now_iso(),
        "status": "active",
    }
    names = _merge_names(entity_names)

    def write(tx):
        result = tx.run(
            """
            CREATE (media:Media)
            SET media = $props
            RETURN elementId(media) AS element_id
            """,
            props=props,
        )
        record = result.single()
        element_id = record["element_id"]
        if names:
            tx.run(
                """
                MATCH (media:Media)
                WHERE elementId(media) = $element_id
                WITH media
                UNWIND $entity_names AS entity_name
                MATCH (entity:Entity {name: entity_name, environment: $environment})
                MERGE (media)-[:DEPICTS]->(entity)
                """,
                element_id=element_id,
                environment=environment,
                entity_names=names,
            )
        return element_id

    with _session(driver) as session:
        return session.execute_write(write)


def relate(
    driver,
    from_name,
    rel_type,
    to_name,
    environment,
    weight=None,
    consolidation_variance=None,
    properties=None,
):
    if not REL_TYPE_PATTERN.match(rel_type):
        raise ValueError("rel_type must be uppercase letters, numbers, and underscores")

    props = {
        "environment": environment,
        "weight": float(weight if weight is not None else DEFAULT_EDGE_WEIGHT),
        "consolidation_variance": float(
            consolidation_variance
            if consolidation_variance is not None
            else DEFAULT_CONSOLIDATION_VARIANCE
        ),
        "created_at": _now_iso(),
    }
    if properties:
        props.update(properties)

    def write(tx):
        result = tx.run(
            f"""
            MATCH (source:Entity {{name: $from_name, environment: $environment}})
            MATCH (target:Entity {{name: $to_name, environment: $environment}})
            CREATE (source)-[relationship:{rel_type}]->(target)
            SET relationship = $props
            RETURN elementId(relationship) AS element_id
            """,
            from_name=from_name,
            to_name=to_name,
            environment=environment,
            props=props,
        )
        return result.single() is not None

    with _session(driver) as session:
        return session.execute_write(write)


def fisher_information(consolidation_variance: float) -> float:
    """
    I_ij = 1 / σ²_ij

    Returns the Fisher Information for a KG edge given its consolidation
    variance. Higher Fisher Information = lower uncertainty = more resistance
    to overwriting by new evidence.

    Args:
        consolidation_variance: The edge's σ²_ij. Must be > 0.

    Returns:
        Fisher Information value (>= 1/MIN_CONSOLIDATION_VARIANCE at floor).

    Raises:
        ValueError: If consolidation_variance <= 0.
    """
    if consolidation_variance <= 0.0:
        raise ValueError(
            f"consolidation_variance must be > 0, got {consolidation_variance!r}"
        )
    clamped = max(consolidation_variance, MIN_CONSOLIDATION_VARIANCE)
    return 1.0 / clamped


def stability_threshold(
    consolidation_variance: float,
    rigidity: float = 1.0,
) -> float:
    """
    Return the minimum prediction error (PE) required to update this edge.

    Formula: 0.5 + 0.3 × lock_score × rigidity
    where lock_score = min(1.0, I_ij) = min(1.0, 1/σ²_ij)

    A freshly-created edge (variance=1.0, I=1.0) has threshold ~0.8.
    A fully-consolidated edge (variance→0, I→∞, capped at 1.0) has
    threshold ~0.8 as well — the cap keeps it bounded.
    An uncertain edge (variance>1.0, I<1.0) has threshold < 0.8, meaning
    weaker evidence can still shift it.

    Args:
        consolidation_variance: The edge's current σ²_ij.
        rigidity: Global rigidity factor ρ (default 1.0). Increase to make
                  the whole graph more conservative; decrease to allow more
                  rapid updating.

    Returns:
        PE threshold in range [0.5, 0.8] for rigidity=1.0.
    """
    lock_score = min(1.0, fisher_information(consolidation_variance))
    return 0.5 + 0.3 * lock_score * float(rigidity)


def update_edge_synaptic_weights(
    driver,
    from_name: str,
    rel_type: str,
    to_name: str,
    environment: str,
    new_weight: float,
    new_variance: float,
) -> bool:
    """
    Update the synaptic weight and consolidation_variance on an existing edge.

    Called by Dream's NREM consolidation pass. Does not create a new edge —
    only updates an existing one. Returns True if the edge was found and
    updated, False otherwise.

    Args:
        driver:       Active Neo4j driver.
        from_name:    Source entity name.
        rel_type:     Relationship type (uppercase, e.g. "KNOWS").
        to_name:      Target entity name.
        environment:  Graph environment scope.
        new_weight:   Updated weight value (clamped to [0.0, 1.0]).
        new_variance: Updated consolidation_variance (clamped to
                      [MIN_CONSOLIDATION_VARIANCE, inf)).

    Returns:
        True if the edge existed and was updated, False if not found.
    """
    if not REL_TYPE_PATTERN.match(rel_type):
        raise ValueError(
            "rel_type must be uppercase letters, numbers, and underscores"
        )

    clamped_weight = max(0.0, min(1.0, float(new_weight)))
    clamped_variance = max(MIN_CONSOLIDATION_VARIANCE, float(new_variance))

    def write(tx):
        result = tx.run(
            f"""
            MATCH (source:Entity {{name: $from_name, environment: $environment}})
            -[relationship:{rel_type}]->
            (target:Entity {{name: $to_name, environment: $environment}})
            SET relationship.weight = $weight,
                relationship.consolidation_variance = $variance
            RETURN elementId(relationship) AS element_id
            """,
            from_name=from_name,
            to_name=to_name,
            environment=environment,
            weight=clamped_weight,
            variance=clamped_variance,
        )
        return result.single() is not None

    with _session(driver) as session:
        return session.execute_write(write)


def get_edge_synaptic_weights(
    driver,
    from_name: str,
    rel_type: str,
    to_name: str,
    environment: str,
) -> dict | None:
    """
    Return the current weight and consolidation_variance for an edge.

    Used by Dream CONSOLIDATE to read current values before applying
    Hebbian strengthening. Returns None if the edge does not exist.

    Args:
        driver:      Active Neo4j driver.
        from_name:   Source entity name.
        rel_type:    Relationship type (uppercase, e.g. "KNOWS").
        to_name:     Target entity name.
        environment: Graph environment scope.

    Returns:
        Dict with keys "weight" and "consolidation_variance", or None.

    Raises:
        ValueError: If rel_type is not a valid relationship type pattern.
    """
    if not REL_TYPE_PATTERN.match(rel_type):
        raise ValueError(
            "rel_type must be uppercase letters, numbers, and underscores"
        )

    def read(tx):
        result = tx.run(
            f"""
            MATCH (source:Entity {{name: $from_name, environment: $environment}})
            -[relationship:{rel_type}]->
            (target:Entity {{name: $to_name, environment: $environment}})
            RETURN relationship.weight AS weight,
                   relationship.consolidation_variance AS consolidation_variance
            """,
            from_name=from_name,
            to_name=to_name,
            environment=environment,
        )
        record = result.single()
        if record is None:
            return None
        return {
            "weight": record["weight"],
            "consolidation_variance": record["consolidation_variance"],
        }

    with _session(driver) as session:
        return session.execute_read(read)


def query_environment(driver, environment):
    with _session(driver) as session:
        result = session.run(
            """
            MATCH (entity:Entity {environment: $environment})
            RETURN
                elementId(entity) AS element_id,
                entity.name AS name,
                entity.entity_type AS entity_type,
                entity.environment AS environment,
                entity.created_at AS created_at,
                entity.status AS status
            ORDER BY entity.name
            """,
            environment=environment,
        )
        return [dict(record) for record in result]


def get_patterns(driver, environment=None):
    if environment is None:
        cypher = """
        MATCH (pattern:Pattern)
        RETURN elementId(pattern) AS element_id, properties(pattern) AS properties
        ORDER BY pattern.environment, pattern.name
        """
        params = {}
    else:
        cypher = """
        MATCH (pattern:Pattern {environment: $environment})
        RETURN elementId(pattern) AS element_id, properties(pattern) AS properties
        ORDER BY pattern.name
        """
        params = {"environment": environment}

    with _session(driver) as session:
        result = session.run(cypher, **params)
        patterns = []
        for record in result:
            pattern = dict(record["properties"])
            pattern["element_id"] = record["element_id"]
            patterns.append(pattern)
        return patterns


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


def get_deferred_goals(
    driver,
    environment: str,
    limit: int = 20,
) -> list[dict]:
    """
    Return Goal nodes with status 'deferred', ordered by priority desc.

    Deferred goals are temporarily suspended; Orientation surfaces them
    as 'unresolved_items' and 'do_not_forget' in the orientation digest.

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
            MATCH (g:Goal {environment: $environment, status: 'deferred'})
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


# ---------------------------------------------------------------------------
# Epistemic memory chain substrate
# ---------------------------------------------------------------------------

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
            f"status must be one of {sorted(VALID_CLAIM_STATUSES)!r}, "
            f"got {status!r}"
        )
    now = _now_iso()
    return {
        "content": str(content).strip(),
        "source_id": str(source_id),
        "environment": environment,
        "coordinator": str(coordinator),
        "confidence": _clamp_unit(float(confidence)),
        "status": status,
        "evidence_count": 0,
        "created_at": now,
        "updated_at": now,
    }


def _belief_properties(
    content: str,
    environment: str,
    *,
    confidence: float = 0.5,
    status: str = "forming",
) -> Dict[str, Any]:
    if status not in VALID_BELIEF_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(VALID_BELIEF_STATUSES)!r}, "
            f"got {status!r}"
        )
    now = _now_iso()
    return {
        "content": str(content).strip(),
        "environment": environment,
        "confidence": _clamp_unit(float(confidence)),
        "status": status,
        "claim_count": 0,
        "created_at": now,
        "updated_at": now,
    }


def _principle_properties(
    content: str,
    environment: str,
    scope: str,
    *,
    status: str = "proposed",
) -> Dict[str, Any]:
    if scope not in VALID_PRINCIPLE_SCOPES:
        raise ValueError(
            f"scope must be one of {sorted(VALID_PRINCIPLE_SCOPES)!r}, "
            f"got {scope!r}"
        )
    if status not in VALID_PRINCIPLE_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(VALID_PRINCIPLE_STATUSES)!r}, "
            f"got {status!r}"
        )
    now = _now_iso()
    return {
        "content": str(content).strip(),
        "environment": environment,
        "scope": scope,
        "status": status,
        "belief_count": 0,
        "created_at": now,
        "updated_at": now,
    }


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
            f"status must be one of {sorted(VALID_DOCTRINE_STATUSES)!r}, "
            f"got {status!r}"
        )
    return {
        "content": str(content).strip(),
        "environment": environment,
        "status": status,
        "version": max(1, int(version)),
        "parent_doctrine_id": parent_doctrine_id,
        "immutable": False,
        "adopted_at": None,
        "created_at": _now_iso(),
    }


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
    props = _source_properties(
        title,
        source_type,
        environment,
        url=url,
        author=author,
        summary=summary,
    )
    props["source_id"] = source_id

    def write(tx):
        tx.run("CREATE (s:Source $props)", props=props)

    with _session(driver) as session:
        session.execute_write(write)
    return source_id


def create_claim(
    driver,
    content: str,
    source_id: str,
    environment: str,
    coordinator: str,
    *,
    confidence: float = 0.5,
    status: str = "candidate",
) -> str:
    import uuid

    claim_id = uuid.uuid4().hex
    props = _claim_properties(
        content,
        source_id,
        environment,
        coordinator,
        confidence=confidence,
        status=status,
    )
    props["claim_id"] = claim_id

    def write(tx):
        tx.run("CREATE (c:Claim $props)", props=props)

    with _session(driver) as session:
        session.execute_write(write)
    return claim_id


def create_belief(
    driver,
    content: str,
    environment: str,
    *,
    confidence: float = 0.5,
    status: str = "forming",
) -> str:
    import uuid

    belief_id = uuid.uuid4().hex
    props = _belief_properties(
        content,
        environment,
        confidence=confidence,
        status=status,
    )
    props["belief_id"] = belief_id

    def write(tx):
        tx.run("CREATE (b:Belief $props)", props=props)

    with _session(driver) as session:
        session.execute_write(write)
    return belief_id


def create_principle(
    driver,
    content: str,
    environment: str,
    scope: str,
    *,
    status: str = "proposed",
) -> str:
    import uuid

    principle_id = uuid.uuid4().hex
    props = _principle_properties(
        content,
        environment,
        scope,
        status=status,
    )
    props["principle_id"] = principle_id

    def write(tx):
        tx.run("CREATE (p:Principle $props)", props=props)

    with _session(driver) as session:
        session.execute_write(write)
    return principle_id


def create_doctrine(
    driver,
    content: str,
    environment: str,
    *,
    version: int = 1,
    parent_doctrine_id: str | None = None,
    status: str = "active",
) -> str:
    import uuid

    doctrine_id = uuid.uuid4().hex
    props = _doctrine_properties(
        content,
        environment,
        version=version,
        parent_doctrine_id=parent_doctrine_id,
        status=status,
    )
    props["doctrine_id"] = doctrine_id

    def write(tx):
        tx.run("CREATE (d:Doctrine $props)", props=props)

    with _session(driver) as session:
        session.execute_write(write)
    return doctrine_id


def create_learning_episode(
    driver,
    session_id: str,
    environment: str,
    coordinator: str,
    learning_type: str,
    *,
    source_id: str | None = None,
    turn_id: str | None = None,
    summary: str = "",
) -> str:
    import uuid

    learning_id = uuid.uuid4().hex
    props = _learning_episode_properties(
        session_id,
        environment,
        coordinator,
        learning_type,
        source_id=source_id,
        turn_id=turn_id,
        summary=summary,
    )
    props["learning_id"] = learning_id

    def write(tx):
        tx.run("CREATE (l:LearningEpisode $props)", props=props)

    with _session(driver) as session:
        session.execute_write(write)
    return learning_id


def link_learning_episode_to_source(
    driver,
    learning_id: str,
    source_id: str,
    environment: str,
) -> bool:
    """Create (LearningEpisode)-[:PROCESSED]->(Source)."""
    def write(tx):
        result = tx.run(
            """
            MATCH (l:LearningEpisode {learning_id: $learning_id, environment: $environment})
            MATCH (s:Source {source_id: $source_id, environment: $environment})
            MERGE (l)-[:PROCESSED]->(s)
            RETURN count(l) AS matched
            """,
            learning_id=learning_id,
            source_id=source_id,
            environment=environment,
        )
        record = result.single()
        return bool(record and record["matched"] > 0)

    with _session(driver) as session:
        return session.execute_write(write)


def link_source_to_claim(
    driver,
    source_id: str,
    claim_id: str,
    environment: str,
) -> bool:
    """Create (Source)-[:YIELDS]->(Claim)."""
    def write(tx):
        result = tx.run(
            """
            MATCH (s:Source {source_id: $source_id, environment: $environment})
            MATCH (c:Claim {claim_id: $claim_id, environment: $environment})
            MERGE (s)-[:YIELDS]->(c)
            RETURN count(s) AS matched
            """,
            source_id=source_id,
            claim_id=claim_id,
            environment=environment,
        )
        record = result.single()
        return bool(record and record["matched"] > 0)

    with _session(driver) as session:
        return session.execute_write(write)


def link_learning_episode_to_claim(
    driver,
    learning_id: str,
    claim_id: str,
    environment: str,
) -> bool:
    """Create (LearningEpisode)-[:YIELDED]->(Claim)."""
    def write(tx):
        result = tx.run(
            """
            MATCH (l:LearningEpisode {learning_id: $learning_id, environment: $environment})
            MATCH (c:Claim {claim_id: $claim_id, environment: $environment})
            MERGE (l)-[:YIELDED]->(c)
            RETURN count(l) AS matched
            """,
            learning_id=learning_id,
            claim_id=claim_id,
            environment=environment,
        )
        record = result.single()
        return bool(record and record["matched"] > 0)

    with _session(driver) as session:
        return session.execute_write(write)


def link_claim_to_belief(
    driver,
    claim_id: str,
    belief_id: str,
    environment: str,
) -> bool:
    """Create (Claim)-[:SUPPORTS]->(Belief) and increment claim_count once."""
    now = _now_iso()

    def write(tx):
        result = tx.run(
            """
            MATCH (c:Claim {claim_id: $claim_id, environment: $environment})
            MATCH (b:Belief {belief_id: $belief_id, environment: $environment})
            MERGE (c)-[r:SUPPORTS]->(b)
            ON CREATE SET b.claim_count = coalesce(b.claim_count, 0) + 1,
                          b.updated_at = $now
            RETURN count(r) AS matched
            """,
            claim_id=claim_id,
            belief_id=belief_id,
            environment=environment,
            now=now,
        )
        record = result.single()
        return bool(record and record["matched"] > 0)

    with _session(driver) as session:
        return session.execute_write(write)


def link_belief_to_principle(
    driver,
    belief_id: str,
    principle_id: str,
    environment: str,
) -> bool:
    """Create (Belief)-[:GROUNDS]->(Principle) and increment belief_count once."""
    now = _now_iso()

    def write(tx):
        result = tx.run(
            """
            MATCH (b:Belief {belief_id: $belief_id, environment: $environment})
            MATCH (p:Principle {principle_id: $principle_id, environment: $environment})
            MERGE (b)-[r:GROUNDS]->(p)
            ON CREATE SET p.belief_count = coalesce(p.belief_count, 0) + 1,
                          p.updated_at = $now
            RETURN count(r) AS matched
            """,
            belief_id=belief_id,
            principle_id=principle_id,
            environment=environment,
            now=now,
        )
        record = result.single()
        return bool(record and record["matched"] > 0)

    with _session(driver) as session:
        return session.execute_write(write)


def link_principle_to_doctrine(
    driver,
    principle_id: str,
    doctrine_id: str,
    environment: str,
) -> bool:
    """Create (Principle)-[:INSTANTIATES]->(Doctrine)."""
    def write(tx):
        result = tx.run(
            """
            MATCH (p:Principle {principle_id: $principle_id, environment: $environment})
            MATCH (d:Doctrine {doctrine_id: $doctrine_id, environment: $environment})
            MERGE (p)-[:INSTANTIATES]->(d)
            RETURN count(p) AS matched
            """,
            principle_id=principle_id,
            doctrine_id=doctrine_id,
            environment=environment,
        )
        record = result.single()
        return bool(record and record["matched"] > 0)

    with _session(driver) as session:
        return session.execute_write(write)


def update_claim_status(
    driver,
    claim_id: str,
    environment: str,
    status: str,
    *,
    confidence: float | None = None,
) -> bool:
    if status not in VALID_CLAIM_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(VALID_CLAIM_STATUSES)!r}, "
            f"got {status!r}"
        )
    updates: dict[str, Any] = {"status": status, "updated_at": _now_iso()}
    if confidence is not None:
        updates["confidence"] = _clamp_unit(float(confidence))

    def write(tx):
        result = tx.run(
            """
            MATCH (c:Claim {claim_id: $claim_id, environment: $environment})
            SET c += $updates
            RETURN c.claim_id AS claim_id
            """,
            claim_id=claim_id,
            environment=environment,
            updates=updates,
        )
        return result.single() is not None

    with _session(driver) as session:
        return session.execute_write(write)


def update_belief_status(
    driver,
    belief_id: str,
    environment: str,
    status: str,
    *,
    confidence: float | None = None,
) -> bool:
    if status not in VALID_BELIEF_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(VALID_BELIEF_STATUSES)!r}, "
            f"got {status!r}"
        )
    updates: dict[str, Any] = {"status": status, "updated_at": _now_iso()}
    if confidence is not None:
        updates["confidence"] = _clamp_unit(float(confidence))

    def write(tx):
        result = tx.run(
            """
            MATCH (b:Belief {belief_id: $belief_id, environment: $environment})
            SET b += $updates
            RETURN b.belief_id AS belief_id
            """,
            belief_id=belief_id,
            environment=environment,
            updates=updates,
        )
        return result.single() is not None

    with _session(driver) as session:
        return session.execute_write(write)


def update_principle_status(
    driver,
    principle_id: str,
    environment: str,
    status: str,
) -> bool:
    if status not in VALID_PRINCIPLE_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(VALID_PRINCIPLE_STATUSES)!r}, "
            f"got {status!r}"
        )
    updates: dict[str, Any] = {"status": status, "updated_at": _now_iso()}

    def write(tx):
        result = tx.run(
            """
            MATCH (p:Principle {principle_id: $principle_id, environment: $environment})
            SET p += $updates
            RETURN p.principle_id AS principle_id
            """,
            principle_id=principle_id,
            environment=environment,
            updates=updates,
        )
        return result.single() is not None

    with _session(driver) as session:
        return session.execute_write(write)


def adopt_doctrine(driver, doctrine_id: str, environment: str) -> bool:
    """
    Adopt a Doctrine node, making it immutable.

    Raises ValueError if the Doctrine was already adopted and immutable.
    """
    def write(tx):
        result = tx.run(
            """
            MATCH (d:Doctrine {doctrine_id: $doctrine_id, environment: $environment})
            RETURN d.immutable AS immutable
            """,
            doctrine_id=doctrine_id,
            environment=environment,
        )
        record = result.single()
        if record is None:
            return False
        if record["immutable"] is True:
            raise ValueError("Doctrine is already adopted and immutable")

        tx.run(
            """
            MATCH (d:Doctrine {doctrine_id: $doctrine_id, environment: $environment})
            SET d.status = 'active',
                d.immutable = true,
                d.adopted_at = $now
            RETURN d.doctrine_id AS doctrine_id
            """,
            doctrine_id=doctrine_id,
            environment=environment,
            now=_now_iso(),
        )
        return True

    with _session(driver) as session:
        return session.execute_write(write)


def deprecate_doctrine(driver, doctrine_id: str, environment: str) -> bool:
    """Deprecate a Doctrine node without mutating content or immutability."""
    def write(tx):
        result = tx.run(
            """
            MATCH (d:Doctrine {doctrine_id: $doctrine_id, environment: $environment})
            SET d.status = 'deprecated'
            RETURN d.doctrine_id AS doctrine_id
            """,
            doctrine_id=doctrine_id,
            environment=environment,
        )
        return result.single() is not None

    with _session(driver) as session:
        return session.execute_write(write)


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


def get_claims_for_source(
    driver,
    source_id: str,
    environment: str,
) -> list[dict]:
    def read(tx):
        result = tx.run(
            """
            MATCH (c:Claim {source_id: $source_id, environment: $environment})
            RETURN properties(c) AS claim
            ORDER BY c.created_at DESC
            """,
            source_id=source_id,
            environment=environment,
        )
        return [dict(r["claim"]) for r in result]

    with _session(driver) as session:
        return session.execute_read(read)


def get_beliefs_for_claim(
    driver,
    claim_id: str,
    environment: str,
) -> list[dict]:
    def read(tx):
        result = tx.run(
            """
            MATCH (c:Claim {claim_id: $claim_id, environment: $environment})
                  -[:SUPPORTS]->(b:Belief {environment: $environment})
            RETURN properties(b) AS belief
            ORDER BY b.created_at DESC
            """,
            claim_id=claim_id,
            environment=environment,
        )
        return [dict(r["belief"]) for r in result]

    with _session(driver) as session:
        return session.execute_read(read)


def close(driver):
    driver.close()
