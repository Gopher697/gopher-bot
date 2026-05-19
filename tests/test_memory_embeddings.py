from __future__ import annotations


def test_embedder_embed_returns_float_list_and_reuses_client(monkeypatch):
    import coordinators.embedder as embedder_module
    from coordinators.embedder import Embedder

    client_inits = []
    calls = []

    class FakeEmbeddings:
        def create(self, **kwargs):
            calls.append(kwargs)
            item = type("EmbeddingItem", (), {"embedding": [0.1, 0.2, 0.3]})()
            return type("EmbeddingResponse", (), {"data": [item]})()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            client_inits.append(kwargs)
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr(embedder_module, "OpenAI", FakeOpenAI)

    embedder = Embedder()

    assert embedder.embed("memory text") == [0.1, 0.2, 0.3]
    assert embedder.embed("more memory text") == [0.1, 0.2, 0.3]
    assert client_inits == [
        {
            "base_url": "http://localhost:1234/v1",
            "api_key": "local",
        }
    ]
    assert calls[0]["model"] == "text-embedding-nomic-embed-text-v1.5@q8_0"
    assert calls[0]["input"] == "memory text"


def test_embedder_embed_returns_none_on_failure(monkeypatch):
    import coordinators.embedder as embedder_module
    from coordinators.embedder import Embedder

    class FakeEmbeddings:
        def create(self, **kwargs):
            raise RuntimeError("embedding service unavailable")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr(embedder_module, "OpenAI", FakeOpenAI)

    assert Embedder().embed("memory text") is None


def test_memory_retrieve_uses_vector_path_when_embedding_succeeds():
    from coordinators.memory import Memory

    calls = []

    class FakeEmbedder:
        def embed(self, text):
            calls.append(("embed", text))
            return [0.1, 0.2, 0.3]

    memory = Memory(embedder=FakeEmbedder())
    memory._retrieve_vector_context = lambda embedding, environment="global": "Vector context"
    memory._retrieve_keyword_context = lambda terms, environment="global": "Keyword context"

    assert memory.retrieve(["gopher", "memory"]) == "Vector context"
    assert calls == [("embed", "gopher memory")]


def test_memory_retrieve_falls_back_to_keyword_path_when_embedder_returns_none():
    from coordinators.memory import Memory

    class FakeEmbedder:
        def embed(self, text):
            return None

    memory = Memory(embedder=FakeEmbedder())
    memory._retrieve_vector_context = lambda embedding, environment="global": "Vector context"
    memory._retrieve_keyword_context = lambda terms, environment="global": "Keyword context"

    assert memory.retrieve(["gopher", "memory"]) == "Keyword context"


def test_memory_retrieve_falls_back_to_keyword_path_when_vector_has_no_results():
    from coordinators.memory import Memory

    class FakeEmbedder:
        def embed(self, text):
            return [0.1, 0.2, 0.3]

    memory = Memory(embedder=FakeEmbedder())
    memory._retrieve_vector_context = lambda embedding, environment="global": ""
    memory._retrieve_keyword_context = lambda terms, environment="global": "Keyword context"

    assert memory.retrieve(["gopher", "memory"]) == "Keyword context"
