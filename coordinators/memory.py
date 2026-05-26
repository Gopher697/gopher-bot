from __future__ import annotations

import logging
import re as _re
import sys
from pathlib import Path
from typing import Any, Iterable

from coordinators.base import Coordinator
from coordinators.embedder import Embedder
from world_models.config_utils import BOT_NAME

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_models import config, graph, vector_index  # noqa: E402


MAX_CONTEXT_ITEMS = 12
RECENT_EPISODIC_ITEMS = 6   # always pull this many recent observed exchanges
RELEVANT_CONTEXT_ITEMS = 8  # keyword/vector lane budget (was MAX_CONTEXT_ITEMS=12)
INGEST_CHUNK_SIZE = 1500   # characters per chunk
INGEST_MAX_CHUNKS = 20     # max chunks per document (~30KB)


def _char_chunk(text: str, chunk_size: int) -> list[str]:
    """
    Split text into chunks of at most chunk_size characters, preferring
    to break at newline boundaries. Used as a fallback when a structural
    section is too large to store as a single chunk.
    """
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start:
                end = newline
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


# Patterns that mark the start of a new structural section
_SECTION_BOUNDARY = _re.compile(
    r"^(?:"
    r"#{1,6}\s"           # Markdown headers: # H1 through ###### H6
    r"|§\s*[\d.]+"        # Section symbols: §8.2, § 13
    r"|\d+(?:\.\d+)+\s"   # Numbered sections: 8.2 Heading, 13.8.1 Sub
    r")",
    _re.MULTILINE,
)


def _semantic_chunk_text(
    text: str,
    chunk_size: int,
    max_chunks: int,
) -> list[str]:
    """
    Split text into semantically coherent chunks by respecting document structure.

    Strategy:
    1. Find all structural section boundaries (markdown headers, numbered sections,
       section symbols like §8.2).
    2. Each section from one boundary to the next becomes a chunk candidate.
    3. If a section candidate exceeds chunk_size characters, split it further
       using paragraph breaks (double newline), then fall back to _char_chunk().
    4. If no structural boundaries are found, fall back to paragraph splitting,
       then to _char_chunk().

    The section header is always included at the top of each sub-chunk produced
    by splitting an oversized section, so retrieval context is preserved.

    Args:
        text:       Input text to chunk.
        chunk_size: Maximum characters per chunk.
        max_chunks: Maximum number of chunks to produce.

    Returns:
        List of non-empty chunk strings, at most max_chunks long.
    """
    text = text.strip()
    if not text:
        return []

    boundaries = [match.start() for match in _SECTION_BOUNDARY.finditer(text)]

    if boundaries:
        raw_sections: list[tuple[str, bool]] = []
        for index, start in enumerate(boundaries):
            end = boundaries[index + 1] if index + 1 < len(boundaries) else len(text)
            section = text[start:end].strip()
            if section:
                raw_sections.append((section, True))
        if boundaries[0] > 0:
            preamble = text[:boundaries[0]].strip()
            if preamble:
                raw_sections.insert(0, (preamble, False))
    else:
        raw_sections = [(text, False)]

    chunks: list[str] = []
    for section, has_header in raw_sections:
        if len(chunks) >= max_chunks:
            break
        if len(section) <= chunk_size:
            chunks.append(section)
        else:
            lines = section.split("\n", 1)
            header = lines[0].strip() if has_header and len(lines) > 1 else ""
            body = lines[1] if header else section

            paragraphs = [paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()]
            current: list[str] = [header] if header else []
            current_len = len(header)

            for paragraph in paragraphs:
                if len(chunks) >= max_chunks:
                    break
                if current_len + len(paragraph) + 2 <= chunk_size:
                    current.append(paragraph)
                    current_len += len(paragraph) + 2
                else:
                    if current:
                        flushed = "\n\n".join(current).strip()
                        if flushed and flushed != header:
                            chunks.append(flushed)
                    if len(chunks) >= max_chunks:
                        break
                    if len(paragraph) <= chunk_size and (
                        not header or len(header) + len(paragraph) + 2 <= chunk_size
                    ):
                        current = [header, paragraph] if header else [paragraph]
                        current_len = len(header) + len(paragraph) + 2
                    else:
                        prefix = f"{header}\n\n" if header else ""
                        sub_chunk_size = max(chunk_size - len(prefix), 1)
                        for sub_chunk in _char_chunk(paragraph, sub_chunk_size):
                            if len(chunks) >= max_chunks:
                                break
                            chunks.append((prefix + sub_chunk).strip())
                        current = [header] if header else []
                        current_len = len(header)

            if current and len(chunks) < max_chunks:
                flushed = "\n\n".join(current).strip()
                if flushed and flushed != header:
                    chunks.append(flushed)

    return [chunk for chunk in chunks if chunk][:max_chunks]


def _format_recent_episodic(items: list[dict]) -> str:
    """Format recent observed observations into a readable context string."""
    if not items:
        return ""
    lines = []
    for item in reversed(items):  # oldest first so conversation reads chronologically
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(content)
    return "\n---\n".join(lines)


class Memory(Coordinator):
    name = "memory"

    def __init__(self, embedder: Embedder | None = None):
        self.embedder = embedder or Embedder()

    def process(self, packet: dict) -> dict:
        keywords = list(packet.get("keywords") or [])
        _act = packet.get("current_activity")
        if isinstance(_act, dict):
            import json as _j

            skill_domains = _act.get("skill_domains") or []
            if isinstance(skill_domains, str):
                try:
                    skill_domains = _j.loads(skill_domains)
                except (TypeError, ValueError):
                    skill_domains = []
            for domain in skill_domains:
                domain = str(domain).strip()
                if domain and domain not in keywords:
                    keywords.append(domain)

        packet["memory_context"] = self.retrieve(keywords)

        # Ingest user-provided content into the graph for future retrieval.
        text_attachments = packet.get("text_attachments") or []
        visual_percept = packet.get("visual_percept") or {}
        visual_description = ""
        visual_filename = ""
        if visual_percept.get("scene_type") == "user_attachment":
            visual_description = str(visual_percept.get("description") or "").strip()
            desc = visual_description
            if desc.startswith("[") and "]:" in desc:
                visual_filename = desc[1:desc.index("]")]

        if text_attachments or visual_description:
            self.ingest_attachments(
                text_attachments=text_attachments,
                visual_description=visual_description,
                visual_filename=visual_filename,
                session_id=str(packet.get("session_id") or ""),
            )
        return packet

    def retrieve(self, keywords: Iterable[str], environment: str = "global") -> str:
        terms = _normalize_keywords(keywords)

        # Lane 1: topic-relevant content (keyword or vector)
        relevant_text = ""
        if terms:
            embedding = self.embedder.embed(" ".join(terms))
            if embedding is not None:
                relevant_text = self._retrieve_vector_context(embedding, environment)
            if not relevant_text:
                relevant_text = self._retrieve_keyword_context(
                    terms, environment, limit=RELEVANT_CONTEXT_ITEMS
                )

        # Lane 2: recent episodic exchanges (always, regardless of keywords)
        recent_items = self._retrieve_recent_episodic(environment)
        # Deduplicate: drop recent items whose content already appears in relevant_text
        unique_recent = [
            item for item in recent_items
            if not relevant_text or str(item.get("content", "")) not in relevant_text
        ]
        recent_text = _format_recent_episodic(unique_recent)

        # Combine: recent context first (highest signal for coherence), then broader context
        parts = []
        if recent_text:
            parts.append(f"[Recent exchanges]\n{recent_text}")
        if relevant_text:
            parts.append(f"[Relevant context]\n{relevant_text}")
        return "\n\n".join(parts)

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
        limit: int = MAX_CONTEXT_ITEMS,
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
                    limit=limit,
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
                    limit=limit,
                )

                return _format_context(entity_records, observation_records)
        except Exception:
            return ""
        finally:
            if driver is not None:
                graph.close(driver)

    def _retrieve_recent_episodic(
        self,
        environment: str = "global",
        limit: int = RECENT_EPISODIC_ITEMS,
    ) -> list[dict]:
        """
        Return the most recent observed conversation exchanges from the graph,
        ordered newest-first. These are source_type='observed' Observation nodes
        written by Reason after each turn.

        Returns a list of observation property dicts, or [] on failure.
        """
        driver = None
        try:
            driver = graph.connect()
            with driver.session(database=config.NEO4J_DATABASE) as session:
                records = session.run(
                    """
                    MATCH (observation:Observation {environment: $environment})
                    WHERE coalesce(observation.status, 'active') = 'active'
                      AND coalesce(observation.source_type, 'observed') = 'observed'
                    RETURN properties(observation) AS observation
                    ORDER BY observation.created_at DESC
                    LIMIT $limit
                    """,
                    environment=environment,
                    limit=limit,
                )
                return [record["observation"] for record in records]
        except Exception:
            return []
        finally:
            if driver is not None:
                graph.close(driver)

    def ingest_attachments(
        self,
        text_attachments: list[dict],
        visual_description: str = "",
        visual_filename: str = "",
        session_id: str = "",
    ) -> None:
        """
        Write user-provided content to the graph as retrievable Observations.

        Text attachments are chunked and stored as Observations so Memory can
        retrieve them on future turns via vector or keyword search.
        """
        for attachment in text_attachments:
            filename = attachment.get("filename") or "untitled"
            content = str(attachment.get("content") or "").strip()
            if not content:
                continue
            try:
                chunks = _semantic_chunk_text(content, INGEST_CHUNK_SIZE, INGEST_MAX_CHUNKS)
                for index, chunk in enumerate(chunks):
                    if len(chunks) > 1:
                        label = f"[{filename} chunk {index + 1}/{len(chunks)}]"
                    else:
                        label = f"[{filename}]"
                    self.store(
                        f"{label}\n{chunk}",
                        source_type="external_content",
                    )
            except Exception as exc:
                logger.warning("Failed to ingest text attachment %s: %s", filename, exc)

        if visual_description:
            try:
                label = f"[image: {visual_filename}]" if visual_filename else "[image]"
                self.store(
                    f"{label}\n{visual_description}",
                    source_type="external_content",
                )
            except Exception as exc:
                logger.warning("Failed to ingest image description: %s", exc)

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
                BOT_NAME,
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

    def store_visual_observation(
        self,
        percept: "VisualPercept",
        environment: str = "global",
    ) -> bool:
        """
        Store a VisionSensor percept snapshot as a graph Observation.

        Uses source_type="perceived" to distinguish desktop snapshots from
        conversation exchanges ("observed") and document chunks
        ("external_content"). The percept description is used as Observation
        content and must be non-empty.
        """
        content = str(getattr(percept, "description", "") or "").strip()
        if not content:
            return False
        try:
            self.store(
                content,
                environment=environment,
                source_type="perceived",
            )
            return True
        except Exception:
            return False

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
