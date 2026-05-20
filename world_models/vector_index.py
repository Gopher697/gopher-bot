from __future__ import annotations


def ensure_vector_index(driver, database) -> None:
    with driver.session(database=database) as session:
        result = session.run(
            """
            CREATE VECTOR INDEX observation_embedding IF NOT EXISTS
            FOR (o:Observation) ON (o.embedding)
            OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}}
            """
        )
        _consume(result)


def store_embedding(
    driver,
    database,
    observation_content: str,
    embedding: list[float],
) -> None:
    with driver.session(database=database) as session:
        result = session.run(
            """
            MATCH (observation:Observation {content: $observation_content})
            SET observation.embedding = $embedding
            """,
            observation_content=observation_content,
            embedding=embedding,
        )
        _consume(result)


def delete_embedding(
    driver,
    database,
    observation_content: str,
) -> bool:
    """
    Remove the embedding property from an Observation node without deleting
    the node itself.

    Useful when re-indexing (e.g. changing embedding model dimensions) or
    when you want to remove a node from vector search while retaining it
    in the graph for keyword search or audit purposes.

    Args:
        driver:              Active Neo4j driver.
        database:            Neo4j database name.
        observation_content: Exact content string of the Observation node.

    Returns:
        True if the node was found and the property removed, False otherwise.
    """
    with driver.session(database=database) as session:
        result = session.run(
            """
            MATCH (observation:Observation {content: $observation_content})
            WHERE observation.embedding IS NOT NULL
            REMOVE observation.embedding
            RETURN elementId(observation) AS eid
            """,
            observation_content=observation_content,
        )
        record = result.single()
        _consume(result)
        return record is not None


def _consume(result) -> None:
    consume = getattr(result, "consume", None)
    if callable(consume):
        consume()
