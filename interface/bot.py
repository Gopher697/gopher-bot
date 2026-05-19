from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_models import config, graph  # noqa: E402


MODEL = "claude-sonnet-4-6"
MAX_CONTEXT_ITEMS = 12
STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "because",
    "but",
    "can",
    "could",
    "for",
    "from",
    "have",
    "how",
    "into",
    "just",
    "like",
    "that",
    "the",
    "this",
    "what",
    "when",
    "where",
    "with",
    "would",
    "you",
    "your",
}


def _terms(message: str) -> list[str]:
    terms = []
    for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", message.lower()):
        if len(token) < 3 or token in STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
    return terms[:10]


def _trim(value: Any, limit: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _format_entity(entity: dict[str, Any]) -> str:
    name = _trim(entity.get("name"), 80) or "Unnamed entity"
    entity_type = _trim(entity.get("entity_type"), 40)
    environment = _trim(entity.get("environment"), 40)
    details = ", ".join(item for item in (entity_type, environment) if item)
    return f"- {name}" + (f" ({details})" if details else "")


def _format_observation(observation: dict[str, Any], entity_names: list[str] | None = None) -> str:
    content = _trim(observation.get("content"))
    if not content:
        return ""

    environment = _trim(observation.get("environment"), 40)
    confidence = observation.get("confidence")
    details = []
    if environment:
        details.append(environment)
    if confidence is not None:
        details.append(f"confidence {confidence}")
    if entity_names:
        details.append("entities: " + ", ".join(_trim(name, 40) for name in entity_names))

    suffix = f" ({'; '.join(details)})" if details else ""
    return f"- {content}{suffix}"


def query_context(message: str) -> str:
    terms = _terms(message)
    if not terms:
        return ""

    driver = None
    try:
        driver = graph.connect()
        with driver.session(database=config.NEO4J_DATABASE) as session:
            entity_records = session.run(
                """
                MATCH (entity:Entity)
                WHERE any(term IN $terms WHERE
                    toLower(coalesce(entity.name, "")) CONTAINS term OR
                    toLower(coalesce(entity.entity_type, "")) CONTAINS term OR
                    toLower(coalesce(entity.environment, "")) CONTAINS term
                )
                OPTIONAL MATCH (observation:Observation)-[:OBSERVED]->(entity)
                WITH entity, collect(observation)[0..3] AS observations
                RETURN properties(entity) AS entity,
                       [item IN observations WHERE item IS NOT NULL | properties(item)] AS observations
                ORDER BY entity.name
                LIMIT $limit
                """,
                terms=terms,
                limit=MAX_CONTEXT_ITEMS,
            )
            observation_records = session.run(
                """
                MATCH (observation:Observation)
                WHERE any(term IN $terms WHERE
                    toLower(coalesce(observation.content, "")) CONTAINS term OR
                    toLower(coalesce(observation.environment, "")) CONTAINS term OR
                    toLower(coalesce(observation.coordinator, "")) CONTAINS term
                )
                OPTIONAL MATCH (observation)-[:OBSERVED]->(entity:Entity)
                RETURN properties(observation) AS observation,
                       collect(entity.name)[0..5] AS entity_names
                ORDER BY observation.created_at DESC
                LIMIT $limit
                """,
                terms=terms,
                limit=MAX_CONTEXT_ITEMS,
            )

            entities = []
            observations = []
            seen_observations = set()

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
    except Exception:
        return ""
    finally:
        if driver is not None:
            graph.close(driver)

    lines = []
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


def _extract_text(response: Any) -> str:
    parts = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            parts.append(str(text))
    return "\n".join(parts).strip()


def respond(message: str) -> str:
    from anthropic import Anthropic

    context = query_context(message)
    system_prompt = (
        "You are Gopher-bot, a persistent AI companion.\n"
        "You are grounded in a knowledge graph that holds your long-term memory.\n"
        f"Graph context for this message: {context}\n"
        "Speak naturally. If the graph has nothing relevant, say so honestly."
    )

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": message}],
    )
    return _extract_text(response)
