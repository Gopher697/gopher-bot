from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable

from coordinators.base import Coordinator
from coordinators.embedder import Embedder


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_models import config, graph, vector_index  # noqa: E402


MAX_CONTEXT_ITEMS = 12


class Memory(Coordinator):
    name = "memory"

    def __init__(self, embedder: Embedder | None = None):
        self.embedder = embedder or Embedder()

    def process(self, packet: dict) -> dict:
        keywords = packet.get("keywords") or []
        packet["memory_context"] = self.retrieve(keywords)
        return packet

    def retrieve(self, keywords: Iterable[str], environment: str = "global") -> str:
        terms = _normalize_keywords(keywords)
        if not terms:
            return ""

        embedding = self.embedder.embed(" ".join(terms))
        if embedding is not None:
            vector_context = self._retrieve_vector_context(embedding, environment)
            if vector_context:
                return vector_context

        return self._retrieve_keyword_context(terms, environment)

    def _retrieve_vector_context(
        self,
        embedding: list[float],
        environment: str = "global",
    ) -> str:
        driver = None
        try:
            driver = graph.connect()
            with driver.session(database=config.NEO4J_DATABASE) as session:
                records = session.run(
                    """
                    CALL db.index.vector.queryNodes('observation_embedding', 12, $embedding)
                    YIELD node AS observation, score
                    WHERE score > 0.65
                      AND coalesce(observation.environment, $environment) = $environment
                      AND coalesce(observation.status, 'active') = 'active'
                    RETURN properties(observation) AS observation, score
                    ORDER BY score DESC
                    """,
                    embedding=embedding,
                    environment=environment,
                )
                return _format_vector_context(records)
        except Exception:
            return ""
        finally:
            if driver is not None:
                graph.close(driver)

    def _retrieve_keyword_context(
        self,
        terms: Iterable[str],
        environment: str = "global",
    ) -> str:
        driver = None
        try:
            driver = graph.connect()
            with driver.session(database=config.NEO4J_DATABASE) as session:
                entity_records = session.run(
                    """
                    MATCH (entity:Entity {environment: $environment})
                    WHERE any(term IN $terms WHERE
                        toLower(coalesce(entity.name, "")) CONTAINS term OR
                        toLower(coalesce(entity.entity_type, "")) CONTAINS term
                    )
                    OPTIONAL MATCH (observation:Observation {environment: $environment})
                        -[:OBSERVED]->(entity)
                    WHERE coalesce(observation.status, 'active') = 'active'
                    WITH entity, collect(observation)[0..3] AS observations
                    RETURN properties(entity) AS entity,
                           [item IN observations WHERE item IS NOT NULL | properties(item)] AS observations
                    ORDER BY entity.name
                    LIMIT $limit
                    """,
                    environment=environment,
                    terms=terms,
                    limit=MAX_CONTEXT_ITEMS,
                )
                observation_records = session.run(
                    """
                    MATCH (observation:Observation {environment: $environment})
                    WHERE coalesce(observation.status, 'active') = 'active'
                      AND any(term IN $terms WHERE
                        toLower(coalesce(observation.content, "")) CONTAINS term OR
                        toLower(coalesce(observation.coordinator, "")) CONTAINS term
                    )
                    OPTIONAL MATCH (observation)-[:OBSERVED]->(entity:Entity)
                    RETURN properties(observation) AS observation,
                           collect(entity.name)[0..5] AS entity_names
                    ORDER BY observation.created_at DESC
                    LIMIT $limit
                    """,
                    environment=environment,
                    terms=terms,
                    limit=MAX_CONTEXT_ITEMS,
                )

                return _format_context(entity_records, observation_records)
        except Exception:
            return ""
        finally:
            if driver is not None:
                graph.close(driver)

    def store(
        self,
        observation: str,
        environment: str = "global",
        confidence: float = 0.7,
        source_type: str = "observed",
    ) -> None:
        content = observation.strip()
        if not content:
            return

        driver = None
        try:
            driver = graph.connect()
            graph.add_observation(
                driver,
                content,
                environment,
                "Gopher-bot",
                confidence=confidence,
                source_type=source_type,
            )
            embedding = self.embedder.embed(content)
            if embedding is not None:
                vector_index.store_embedding(
                    driver,
                    config.NEO4J_DATABASE,
                    content,
                    embedding,
                )
        except Exception:
            return
        finally:
            if driver is not None:
                graph.close(driver)

    def forget(
        self,
        content: str,
        environment: str = "global",
    ) -> bool:
        """
        Hard-delete an Observation node and its vector embedding from the graph.

        Because the embedding is stored as a property on the Observation node,
        Neo4j's vector index cascade removes the vector entry automatically
        when the node is deleted. No separate sync step is needed.

        Args:
            content:     Exact content string of the observation to remove.
            environment: Graph environment scope (default "global").

        Returns:
            True if the observation was found and deleted, False if not found.
        """
        driver = None
        try:
            driver = graph.connect()
            return graph.delete_observation(driver, content, environment)
        except Exception:
            return False
        finally:
            if driver is not None:
                graph.close(driver)

    def record_utterance(
        self,
        content: str,
        session_id: str,
        environment: str = "global",
        tts_generated: bool = False,
        predicted_topic: str | None = None,
        actual_topic: str | None = None,
        prediction_accuracy: float | None = None,
        curation_label: str | None = None,
        turn_id: str | None = None,
    ) -> str:
        """
        Record what Voice actually said to Gopher as an immutable Utterance node.

        This is ground truth — it cannot be revised after writing. Call this
        immediately after Voice emits its response.

        Args:
            content:       The exact text Voice output.
            session_id:    Current BrainLoop session UUID hex.
            environment:   Graph environment scope.
            tts_generated: Whether TTS audio was generated.

        Returns:
            The episode_id of the new node.
        """
        driver = graph.connect()
        try:
            return graph.add_utterance(
                driver=driver,
                content=content,
                session_id=session_id,
                environment=environment,
                tts_generated=tts_generated,
                predicted_topic=predicted_topic,
                actual_topic=actual_topic,
                prediction_accuracy=prediction_accuracy,
                curation_label=curation_label,
                turn_id=turn_id,
            )
        finally:
            graph.close(driver)

    def record_reasoning(
        self,
        content: str,
        session_id: str,
        coordinator: str,
        environment: str = "global",
        accepted: bool = False,
        source_type: str = "observed",
        turn_id: str | None = None,
    ) -> str:
        """
        Record a coordinator's internal reasoning trace as a Reasoning episode.

        These are deliberations that Gopher never heard. They are mutable and
        can be scored later for training corpus curation.

        Args:
            content:     The reasoning trace text.
            session_id:  Current BrainLoop session UUID hex.
            coordinator: Name of the coordinator that produced this.
            environment: Graph environment scope.
            accepted:    Whether the bid was accepted by Awareness.
            source_type: One of VALID_SOURCE_TYPES (default "observed").

        Returns:
            The episode_id of the new node.
        """
        driver = graph.connect()
        try:
            return graph.add_episode(
                driver=driver,
                episode_type="reasoning",
                content=content,
                session_id=session_id,
                environment=environment,
                coordinator=coordinator,
                source_type=source_type,
                accepted=accepted,
                turn_id=turn_id,
            )
        finally:
            graph.close(driver)


def _normalize_keywords(keywords: Iterable[str]) -> list[str]:
    normalized = []
    for keyword in keywords:
        value = str(keyword).strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    return normalized[:10]


def _format_context(entity_records: Iterable[Any], observation_records: Iterable[Any]) -> str:
    lines = []
    seen_observations = set()

    entities = []
    observations = []

    for record in entity_records:
        entity = dict(record["entity"])
        entities.append(entity)
        for observation in record["observations"]:
            content = observation.get("content")
            if content and content not in seen_observations:
                seen_observations.add(content)
                observations.append((dict(observation), None))

    for record in observation_records:
        observation = dict(record["observation"])
        content = observation.get("content")
        if content and content not in seen_observations:
            seen_observations.add(content)
            observations.append((observation, list(record["entity_names"] or [])))

    if entities:
        lines.append("Relevant entities:")
        lines.extend(_format_entity(entity) for entity in entities[:MAX_CONTEXT_ITEMS])
    if observations:
        if lines:
            lines.append("")
        lines.append("Relevant observations:")
        for observation, entity_names in observations[:MAX_CONTEXT_ITEMS]:
            formatted = _format_observation(observation, entity_names)
            if formatted:
                lines.append(formatted)

    return "\n".join(lines).strip()


def _format_vector_context(records: Iterable[Any]) -> str:
    lines = []
    for record in records:
        observation = dict(record["observation"])
        formatted = _format_observation(observation, None)
        if not formatted:
            continue
        score = record["score"]
        lines.append(f"{formatted} (semantic score {float(score):.3f})")

    if not lines:
        return ""

    return "\n".join(["Relevant semantic observations:", *lines]).strip()


def _format_entity(entity: dict[str, Any]) -> str:
    name = _trim(entity.get("name"), 80) or "Unnamed entity"
    entity_type = _trim(entity.get("entity_type"), 40)
    details = f" ({entity_type})" if entity_type else ""
    return f"- {name}{details}"


def _format_observation(observation: dict[str, Any], entity_names: list[str] | None) -> str:
    content = _trim(observation.get("content"))
    if not content:
        return ""

    details = []
    confidence = observation.get("confidence")
    if confidence is not None:
        details.append(f"confidence {confidence}")
    if entity_names:
        details.append("entities: " + ", ".join(_trim(name, 40) for name in entity_names))

    suffix = f" ({'; '.join(details)})" if details else ""
    return f"- {content}{suffix}"


def _trim(value: Any, limit: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
