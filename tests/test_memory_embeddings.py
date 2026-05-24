from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def test_embedder_embed_returns_float_list_and_sends_minimal_payload():
    from coordinators.embedder import Embedder

    calls = []

    def fake_post_json(url, payload):
        calls.append((url, payload))
        return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    embedder = Embedder(post_json=fake_post_json)

    assert embedder.embed("memory text") == [0.1, 0.2, 0.3]
    assert embedder.embed("more memory text") == [0.1, 0.2, 0.3]
    assert calls == [
        (
            "http://localhost:1234/v1/embeddings",
            {
                "model": "text-embedding-nomic-embed-text-v1.5@q8_0",
                "input": ["memory text"],
            },
        ),
        (
            "http://localhost:1234/v1/embeddings",
            {
                "model": "text-embedding-nomic-embed-text-v1.5@q8_0",
                "input": ["more memory text"],
            },
        ),
    ]
    assert "encoding_format" not in calls[0][1]


def test_embedder_preserves_list_input_payload():
    from coordinators.embedder import Embedder

    calls = []

    def fake_post_json(url, payload):
        calls.append((url, payload))
        return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    assert Embedder(post_json=fake_post_json).embed(["first", "second"]) == [
        0.1,
        0.2,
        0.3,
    ]
    assert calls[0][1]["input"] == ["first", "second"]
    assert "encoding_format" not in calls[0][1]


def test_embedder_http_request_omits_encoding_format(monkeypatch):
    import coordinators.embedder as embedder_module
    from coordinators.embedder import Embedder

    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            captured.append({"path": self.path, "body": body})
            response = json.dumps({"data": [{"embedding": [0.1, 0.2, 0.3]}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setattr(
            embedder_module,
            "EMBEDDING_BASE_URL",
            f"http://127.0.0.1:{server.server_port}/v1",
        )

        assert Embedder().embed("memory text") == [0.1, 0.2, 0.3]
        assert captured[0]["path"] == "/v1/embeddings"
        assert captured[0]["body"]["model"] == "text-embedding-nomic-embed-text-v1.5@q8_0"
        assert captured[0]["body"]["input"] == ["memory text"]
        assert "encoding_format" not in captured[0]["body"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_embedder_embed_returns_none_on_failure():
    from coordinators.embedder import Embedder

    def fake_post_json(_url, _payload):
        raise RuntimeError("embedding service unavailable")

    assert Embedder(post_json=fake_post_json).embed("memory text") is None


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
