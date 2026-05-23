from __future__ import annotations

import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from world_models import graph
from world_models.config_utils import BOT_NAME


ENVIRONMENT = "global"


def main() -> int:
    driver = graph.connect()
    try:
        project_id = graph.add_entity(
            driver,
            name=BOT_NAME,
            entity_type="project",
            environment=ENVIRONMENT,
        )
        print(f"Added entity {BOT_NAME}: {project_id}")

        charter_id = graph.add_entity(
            driver,
            name="AGENT_CHARTER.md",
            entity_type="governance_document",
            environment=ENVIRONMENT,
        )
        print(f"Added entity AGENT_CHARTER.md: {charter_id}")

        person_id = graph.add_entity(
            driver,
            name="Chad Crouse",
            entity_type="person",
            environment=ENVIRONMENT,
        )
        print(f"Added entity Chad Crouse: {person_id}")

        governed_by = graph.relate(
            driver,
            from_name=BOT_NAME,
            rel_type="GOVERNED_BY",
            to_name="AGENT_CHARTER.md",
            environment=ENVIRONMENT,
        )
        print(
            f"Added relationship {BOT_NAME} -[:GOVERNED_BY]-> "
            f"AGENT_CHARTER.md: {governed_by}"
        )

        authored_by = graph.relate(
            driver,
            from_name="AGENT_CHARTER.md",
            rel_type="AUTHORED_BY",
            to_name="Chad Crouse",
            environment=ENVIRONMENT,
        )
        print(
            "Added relationship AGENT_CHARTER.md -[:AUTHORED_BY]-> "
            f"Chad Crouse: {authored_by}"
        )

        observation_id = graph.add_observation(
            driver,
            content="Persistent Agent Charter v0.6 ratified on 2026-05-18",
            environment=ENVIRONMENT,
            coordinator="seed.py",
            confidence=1.0,
            entity_names=[BOT_NAME, "AGENT_CHARTER.md"],
        )
        print(f"Added observation: {observation_id}")

        entities = graph.query_environment(driver, ENVIRONMENT)
        print(f"Total global entity count: {len(entities)}")
    finally:
        graph.close(driver)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
