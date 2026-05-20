from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from neo4j import GraphDatabase

from world_models import config


MEDIA_TYPES = {"image", "screenshot", "document", "audio"}
VALID_SOURCE_TYPES = {"observed", "inferred", "proposed", "external_content"}
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
    confidence=1.0,
    properties=None,
):
    if not REL_TYPE_PATTERN.match(rel_type):
        raise ValueError("rel_type must be uppercase letters, numbers, and underscores")

    props = {
        "environment": environment,
        "confidence": float(confidence),
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
