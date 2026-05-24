from __future__ import annotations

from coordinators.awareness import Awareness
from coordinators.base import Coordinator
from coordinators.ethos import (
    ETHOS_MAX_DOCTRINES,
    Ethos,
    _format_doctrine_context,
)
from tests.conftest import isolated_awareness


class _NoopCoordinator(Coordinator):
    name = "noop"

    def process(self, packet: dict) -> dict:
        return packet


class _RecordingEthos(Coordinator):
    name = "ethos"

    def __init__(self) -> None:
        self.called = False

    def process(self, packet: dict) -> dict:
        self.called = True
        packet["doctrine_context"] = "recorded doctrine context"
        packet["active_doctrine_count"] = 1
        return packet


def _doctrine(content: str, version: int = 1, scope: str = "") -> dict:
    doctrine = {
        "content": content,
        "version": version,
    }
    if scope:
        doctrine["scope"] = scope
    return doctrine


def _make_awareness(ethos: Coordinator | None = None) -> Awareness:
    return isolated_awareness(
        sensory=_NoopCoordinator(),
        memory=_NoopCoordinator(),
        reason=_NoopCoordinator(),
        voice=_NoopCoordinator(),
        orientation=_NoopCoordinator(),
        keeper=_NoopCoordinator(),
        mirror_self=_NoopCoordinator(),
        ethos=ethos or Ethos(doctrine_reader=lambda _env: []),
    )


def test_format_empty_list():
    assert _format_doctrine_context([]) == ""


def test_format_single_doctrine():
    result = _format_doctrine_context([_doctrine("Prefer grounded uncertainty.")])
    assert "Prefer grounded uncertainty." in result


def test_format_includes_version_tag():
    result = _format_doctrine_context([_doctrine("State uncertainty plainly.", version=2)])
    assert "[v2]" in result


def test_format_skips_empty_content():
    assert _format_doctrine_context([_doctrine("")]) == ""


def test_format_multiple_doctrines():
    doctrines = [
        _doctrine("Doctrine one."),
        _doctrine("Doctrine two."),
        _doctrine("Doctrine three."),
    ]
    result = _format_doctrine_context(doctrines)
    for doctrine in doctrines:
        assert doctrine["content"] in result


def test_ethos_no_doctrines_adds_empty_context():
    ethos = Ethos(doctrine_reader=lambda _env: [])
    packet = ethos.process({})
    assert packet["doctrine_context"] == ""
    assert packet["active_doctrine_count"] == 0


def test_ethos_doctrines_appended_to_memory_context():
    ethos = Ethos(doctrine_reader=lambda _env: [_doctrine("Doctrine content.")])
    packet = ethos.process({"memory_context": "prior context"})
    memory_context = packet["memory_context"]
    assert "prior context" in memory_context
    assert "Doctrine content." in memory_context


def test_ethos_no_doctrines_does_not_clobber_memory_context():
    ethos = Ethos(doctrine_reader=lambda _env: [])
    packet = ethos.process({"memory_context": "prior context"})
    assert packet["memory_context"] == "prior context"


def test_ethos_active_doctrine_count():
    doctrines = [_doctrine("one"), _doctrine("two"), _doctrine("three")]
    ethos = Ethos(doctrine_reader=lambda _env: doctrines)
    packet = ethos.process({})
    assert packet["active_doctrine_count"] == 3


def test_ethos_reader_exception_graceful():
    def _raise(_environment: str) -> list[dict]:
        raise RuntimeError("graph unavailable")

    ethos = Ethos(doctrine_reader=_raise)
    packet = ethos.process({})
    assert packet["active_doctrine_count"] == 0
    assert packet["doctrine_context"] == ""


def test_ethos_caps_at_max_doctrines():
    doctrines = [_doctrine(f"doctrine {i}") for i in range(15)]
    ethos = Ethos(doctrine_reader=lambda _env: doctrines)
    packet = ethos.process({})
    assert packet["active_doctrine_count"] == ETHOS_MAX_DOCTRINES


def test_ethos_returns_packet():
    ethos = Ethos(doctrine_reader=lambda _env: [])
    packet = {}
    assert ethos.process(packet) is packet


def test_awareness_has_ethos_attribute():
    awareness = isolated_awareness()
    assert hasattr(awareness, "ethos")


def test_awareness_ethos_injectable(monkeypatch):
    monkeypatch.setattr("coordinators.awareness._write_turn_log", lambda _packet: None)
    ethos = _RecordingEthos()
    awareness = _make_awareness(ethos=ethos)
    awareness.synchronous_run("hello")
    assert ethos.called is True
