from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from coordinators.base import Coordinator


ETHOS_PRIORITY = 2
ETHOS_CADENCE_SECONDS = 300
ETHOS_MAX_DOCTRINES = 10


@dataclass(frozen=True)
class EthosBid:
    coordinator_name: str
    content: str
    priority: int
    timestamp: float
    source: str = "ethos"
    type: str = "doctrine_signal"


def _default_doctrine_reader(environment: str) -> list[dict]:
    try:
        from world_models import graph

        driver = graph.connect()
        try:
            return graph.get_active_doctrines(driver, environment)
        finally:
            graph.close(driver)
    except Exception:
        return []


def _format_doctrine_context(doctrines: list[dict]) -> str:
    """Format active Doctrine nodes as a memory-context block for Reason."""
    if not doctrines:
        return ""

    lines = ["Active behavioral doctrines (immutable; adopted):"]
    for doctrine in doctrines:
        content = str(doctrine.get("content") or "").strip()
        version = doctrine.get("version", 1)
        scope_hint = str(doctrine.get("scope") or "").strip()
        if not content:
            continue
        tag = f"[v{version}]" + (f" [{scope_hint}]" if scope_hint else "")
        lines.append(f"- {tag} {content}")

    if len(lines) == 1:
        return ""
    return "\n".join(lines).strip()


class Ethos(Coordinator):
    name = "ethos"

    def __init__(
        self,
        doctrine_reader: Callable[[str], list[dict]] | None = None,
    ) -> None:
        self.doctrine_reader = doctrine_reader or _default_doctrine_reader
        self.last_doctrine_count: int = 0

    def process(self, packet: dict) -> dict:
        """
        Read active Doctrine nodes and inject them as behavioral constraints.

        Adds packet["doctrine_context"] and packet["active_doctrine_count"], and
        appends the formatted doctrine context to packet["memory_context"].
        """
        environment = str(packet.get("environment") or "global")
        try:
            doctrines = self.doctrine_reader(environment)
        except Exception:
            doctrines = []

        doctrines = doctrines[:ETHOS_MAX_DOCTRINES]
        self.last_doctrine_count = len(doctrines)

        doctrine_context = _format_doctrine_context(doctrines)
        packet["doctrine_context"] = doctrine_context
        packet["active_doctrine_count"] = self.last_doctrine_count

        if doctrine_context:
            memory_context = str(packet.get("memory_context") or "").strip()
            packet["memory_context"] = (
                f"{memory_context}\n\n{doctrine_context}"
                if memory_context
                else doctrine_context
            )
        return packet

    async def background_tick(self, awareness_queue) -> None:
        """Reserved for future Archivist-triggered doctrine promotion signals."""
        return None
