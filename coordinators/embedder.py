from __future__ import annotations

from typing import Any

from openai import OpenAI


EMBEDDING_BASE_URL = "http://localhost:1234/v1"
EMBEDDING_MODEL = "text-embedding-nomic-embed-text-v1.5@q8_0"


class Embedder:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = OpenAI(base_url=EMBEDDING_BASE_URL, api_key="local")
        return self._client

    def embed(self, text: str) -> list[float] | None:
        try:
            response = self.client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
            )
            embedding = _extract_embedding(response)
            if embedding is None:
                return None
            return [float(value) for value in embedding]
        except Exception:
            return None


def _extract_embedding(response: Any) -> list[Any] | None:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    if not data:
        return None

    first = data[0]
    if isinstance(first, dict):
        embedding = first.get("embedding")
    else:
        embedding = getattr(first, "embedding", None)

    return embedding if isinstance(embedding, list) else None
