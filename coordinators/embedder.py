from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib import request


EMBEDDING_BASE_URL = "http://localhost:1234/v1"
EMBEDDING_MODEL = "text-embedding-nomic-embed-text-v1.5@q8_0"
PostJson = Callable[[str, dict[str, Any]], Any]


class Embedder:
    def __init__(self, post_json: PostJson | None = None):
        self._post_json = post_json or _post_json

    def embed(self, input_data: str | list[str]) -> list[float] | None:
        try:
            if isinstance(input_data, str):
                input_data = [input_data]
            response = self._post_json(
                _embeddings_url(),
                {
                    "model": EMBEDDING_MODEL,
                    "input": input_data,
                },
            )
            embedding = _extract_embedding(response)
            if embedding is None:
                return None
            return [float(value) for value in embedding]
        except Exception:
            return None


def _embeddings_url() -> str:
    return f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings"


def _post_json(url: str, payload: dict[str, Any]) -> Any:
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


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
