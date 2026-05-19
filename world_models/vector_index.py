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


def _consume(result) -> None:
    consume = getattr(result, "consume", None)
    if callable(consume):
        consume()
