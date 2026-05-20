from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from neo4j import GraphDatabase

from world_models import config


MEDIA_TYPES = {"image", "screenshot", "document", "audio"}
VALID_SOURCE_TYPES = {"observed", "inferred", "proposed", "external_content"}
VALID_EPISODE_TYPES = {"utterance", "reasoning", "action", "observation_group"}
DEFAULT_EDGE_WEIGHT: float = 1.0
DEFAULT_CONSOLIDATION_VARIANCE: float = 1.0   # σ²_ij; decreases as evidence accumulates
MIN_CONSOLIDATION_VARIANCE: float = 0.01      # floor to avoid division by zero
REL_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _session(driver):
    return driver.session(database=config.NEO4J_DATABASE)


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
    )


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


def close(driver):
    driver.close()
