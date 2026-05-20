from uuid import uuid4

import pytest

from world_models import config, graph


def unique_environment() -> str:
    return f"test_{uuid4().hex}"


def cleanup_environment(environment: str) -> None:
    driver = graph.connect()
    try:
        with driver.session(database=config.NEO4J_DATABASE) as session:
            session.run(
                """
                MATCH (node)
                WHERE node.environment = $environment
                DETACH DELETE node
                """,
                environment=environment,
            ).consume()
    finally:
        graph.close(driver)


def new_driver():
    driver = graph.connect()
    driver.verify_connectivity()
    return driver


@pytest.fixture
def environment():
    env = unique_environment()
    try:
        yield env
    finally:
        cleanup_environment(env)


def test_connect():
    driver = new_driver()
    graph.close(driver)


def test_add_entity(environment):
    driver = new_driver()
    try:
        graph.add_entity(driver, "Test Entity", "test_type", environment)
        entities = graph.query_environment(driver, environment)
        assert [entity["name"] for entity in entities] == ["Test Entity"]
    finally:
        graph.close(driver)


def test_add_observation(environment):
    driver = new_driver()
    try:
        graph.add_entity(driver, "Observed Entity", "test_type", environment)
        graph.add_observation(
            driver,
            "Observed entity appeared in test.",
            environment,
            "pytest",
            entity_names=["Observed Entity"],
        )
        with driver.session(database=config.NEO4J_DATABASE) as session:
            record = session.run(
                """
                MATCH (observation:Observation {environment: $environment})
                      -[:OBSERVED]->
                      (entity:Entity {name: $name, environment: $environment})
                RETURN observation.content AS content
                """,
                environment=environment,
                name="Observed Entity",
            ).single()
        assert record is not None
        assert record["content"] == "Observed entity appeared in test."
    finally:
        graph.close(driver)


def test_observation_properties_include_training_candidate_default():
    props = graph._observation_properties(
        "Observed entity appeared in test.",
        "test",
        "pytest",
        0.7,
    )

    assert props["training_candidate"] is None


def test_add_media(environment):
    driver = new_driver()
    try:
        graph.add_entity(driver, "Media Entity", "test_type", environment)
        graph.add_media(
            driver,
            r"D:\gopher-brain-media\test.png",
            "image",
            environment,
            "pytest",
            description="Test media",
            entity_names=["Media Entity"],
        )
        with driver.session(database=config.NEO4J_DATABASE) as session:
            record = session.run(
                """
                MATCH (media:Media {environment: $environment})
                      -[:DEPICTS]->
                      (entity:Entity {name: $name, environment: $environment})
                RETURN media.file_path AS file_path
                """,
                environment=environment,
                name="Media Entity",
            ).single()
        assert record is not None
        assert record["file_path"] == r"D:\gopher-brain-media\test.png"
    finally:
        graph.close(driver)


def test_relate(environment):
    driver = new_driver()
    try:
        graph.add_entity(driver, "Alpha", "test_type", environment)
        graph.add_entity(driver, "Beta", "test_type", environment)
        assert graph.relate(driver, "Alpha", "RELATES_TO", "Beta", environment)
        with driver.session(database=config.NEO4J_DATABASE) as session:
            record = session.run(
                """
                MATCH (:Entity {name: $from_name, environment: $environment})
                      -[relationship:RELATES_TO]->
                      (:Entity {name: $to_name, environment: $environment})
                RETURN count(relationship) AS relationship_count
                """,
                from_name="Alpha",
                to_name="Beta",
                environment=environment,
            ).single()
        assert record["relationship_count"] == 1
    finally:
        graph.close(driver)


def test_query_environment(environment):
    driver = new_driver()
    try:
        graph.add_entity(driver, "First", "test_type", environment)
        graph.add_entity(driver, "Second", "test_type", environment)
        entities = graph.query_environment(driver, environment)
        assert {entity["name"] for entity in entities} == {"First", "Second"}
    finally:
        graph.close(driver)


def test_data_survives(environment):
    driver = new_driver()
    try:
        graph.add_entity(driver, "Persistent Entity", "test_type", environment)
    finally:
        graph.close(driver)

    reopened = new_driver()
    try:
        entities = graph.query_environment(reopened, environment)
        assert any(entity["name"] == "Persistent Entity" for entity in entities)
    finally:
        graph.close(reopened)
