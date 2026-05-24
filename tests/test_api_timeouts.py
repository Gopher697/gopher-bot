"""Tests confirming timeout values are set on API clients."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# -- reason.py timeout constants ---------------------------------------------


def test_reason_timeout_constant_exists():
    from coordinators.reason import REASON_TIMEOUT_SECONDS

    assert isinstance(REASON_TIMEOUT_SECONDS, (int, float))
    assert REASON_TIMEOUT_SECONDS == 90


def test_call_local_reasoner_passes_timeout():
    """OpenAI client for reason is constructed with timeout=REASON_TIMEOUT_SECONDS."""
    from coordinators.reason import REASON_TIMEOUT_SECONDS
    import coordinators.reason as reason_mod

    created_clients = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created_clients.append(kwargs)
            self.chat = MagicMock()
            self.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="ok"))]
            )

    with patch.object(reason_mod, "OpenAI", FakeOpenAI):
        reason_mod._call_local_reasoner(
            "hi",
            "sys",
            {"base_url": "http://localhost:1234/v1", "reason_model": "m"},
        )

    assert len(created_clients) == 1
    assert created_clients[0].get("timeout") == REASON_TIMEOUT_SECONDS


def test_call_anthropic_reasoner_passes_timeout():
    """Anthropic client for reason is constructed with timeout=REASON_TIMEOUT_SECONDS."""
    from coordinators.reason import REASON_TIMEOUT_SECONDS
    import coordinators.reason as reason_mod

    created_clients = []

    class FakeAnthropic:
        def __init__(self, **kwargs):
            created_clients.append(kwargs)
            self.messages = MagicMock()
            self.messages.create.return_value = MagicMock(content=[])

    with patch.object(reason_mod, "Anthropic", FakeAnthropic):
        reason_mod._call_anthropic_reasoner(
            "hi",
            "sys",
            {"reason_model": "claude-haiku-4-5-20251001"},
        )

    assert len(created_clients) == 1
    assert created_clients[0].get("timeout") == REASON_TIMEOUT_SECONDS


# -- sensory.py timeout constants --------------------------------------------


def test_sensory_timeout_constant_exists():
    from coordinators.sensory import SENSORY_TIMEOUT_SECONDS

    assert isinstance(SENSORY_TIMEOUT_SECONDS, (int, float))
    assert SENSORY_TIMEOUT_SECONDS == 30


def test_call_local_classifier_passes_timeout():
    """OpenAI client for Sensory classification uses SENSORY_TIMEOUT_SECONDS."""
    from coordinators.sensory import SENSORY_TIMEOUT_SECONDS
    import coordinators.sensory as sensory_mod

    created_clients = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created_clients.append(kwargs)
            self.chat = MagicMock()
            self.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content='{"intent":"x","keywords":[]}'))]
            )

    with patch.object(sensory_mod, "OpenAI", FakeOpenAI):
        sensory_mod._call_local_classifier(
            "hi",
            "sys",
            {"base_url": "http://localhost:1234/v1", "sensory_model": "m"},
        )

    assert len(created_clients) == 1
    assert created_clients[0].get("timeout") == SENSORY_TIMEOUT_SECONDS


def test_call_anthropic_classifier_passes_timeout():
    """Anthropic client for Sensory classification uses SENSORY_TIMEOUT_SECONDS."""
    from coordinators.sensory import SENSORY_TIMEOUT_SECONDS
    import coordinators.sensory as sensory_mod

    created_clients = []

    class FakeAnthropic:
        def __init__(self, **kwargs):
            created_clients.append(kwargs)
            self.messages = MagicMock()
            self.messages.create.return_value = MagicMock(content=[])

    with patch.object(sensory_mod, "Anthropic", FakeAnthropic):
        sensory_mod._call_anthropic_classifier(
            "hi",
            "sys",
            {"sensory_model": "claude-haiku-4-5-20251001"},
        )

    assert len(created_clients) == 1
    assert created_clients[0].get("timeout") == SENSORY_TIMEOUT_SECONDS


def test_describe_image_passes_timeout():
    """Anthropic client for image description uses SENSORY_TIMEOUT_SECONDS."""
    from coordinators.sensory import SENSORY_TIMEOUT_SECONDS
    import coordinators.sensory as sensory_mod

    created_clients = []

    class FakeAnthropic:
        def __init__(self, **kwargs):
            created_clients.append(kwargs)
            self.messages = MagicMock()
            response = MagicMock()
            response.choices = None
            response.content = [MagicMock(text="A test image.")]
            self.messages.create.return_value = response

    with patch.object(sensory_mod, "Anthropic", FakeAnthropic):
        result = sensory_mod._describe_image(
            b"fake",
            "photo.png",
            {"base_url": None, "sensory_model": "claude-haiku-4-5-20251001"},
        )

    assert result == "A test image."
    assert len(created_clients) == 1
    assert created_clients[0].get("timeout") == SENSORY_TIMEOUT_SECONDS


# -- archivist.py timeout constants ------------------------------------------


def test_archivist_timeout_constant_exists():
    from coordinators.archivist import ARCHIVIST_TIMEOUT_SECONDS

    assert isinstance(ARCHIVIST_TIMEOUT_SECONDS, (int, float))
    assert ARCHIVIST_TIMEOUT_SECONDS == 20


def test_extract_claims_passes_timeout():
    """OpenAI client for Archivist claim extraction uses ARCHIVIST_TIMEOUT_SECONDS."""
    from coordinators.archivist import ARCHIVIST_TIMEOUT_SECONDS
    import coordinators.archivist as archivist_mod

    created_clients = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created_clients.append(kwargs)
            self.chat = MagicMock()
            completion = MagicMock()
            completion.choices = [
                MagicMock(
                    message=MagicMock(
                        content='[{"text": "A durable claim.", "confidence": 0.8}]'
                    )
                )
            ]
            self.chat.completions.create.return_value = completion

    with patch("openai.OpenAI", FakeOpenAI):
        claims = archivist_mod._extract_claims("hello", "world")

    assert claims == [{"text": "A durable claim.", "confidence": 0.8}]
    assert len(created_clients) == 1
    assert created_clients[0].get("timeout") == ARCHIVIST_TIMEOUT_SECONDS


# -- Reason.process() survives a timeout exception ---------------------------


def test_reason_process_survives_timeout():
    """If generate_response raises, process() returns packet with error key."""
    from coordinators.reason import Reason

    reason = Reason()

    def explode(*args, **kwargs):
        raise TimeoutError("LM Studio did not respond in time")

    reason.generate_response = explode
    packet = {"message": "hello", "memory_context": "", "tier": 1}
    result = reason.process(packet)
    assert "error" in result
    assert "reason_output" not in result
