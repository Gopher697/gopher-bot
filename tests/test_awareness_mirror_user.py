from __future__ import annotations

from coordinators.base import Coordinator


class _NoopCoordinator(Coordinator):
    name = "noop"

    def process(self, packet: dict) -> dict:
        return packet


def _make_awareness(monkeypatch, *, mirror_user, mirror_self):
    import coordinators.awareness as awareness_module
    from coordinators.awareness import Awareness

    monkeypatch.setattr(awareness_module, "_write_turn_log", lambda packet: None)

    return Awareness(
        sensory=_NoopCoordinator(),
        memory=_NoopCoordinator(),
        reason=_NoopCoordinator(),
        voice=_NoopCoordinator(),
        orientation=_NoopCoordinator(),
        keeper=_NoopCoordinator(),
        mirror_user=mirror_user,
        mirror_self=mirror_self,
        ethos=_NoopCoordinator(),
        drive=_NoopCoordinator(),
    )


def test_awareness_calls_mirror_user_in_foreground(monkeypatch):
    class FakeMirrorUser(Coordinator):
        name = "mirror_user"

        def process(self, packet: dict) -> dict:
            packet["mirror_user_affect"] = "engaged"
            return packet

    awareness = _make_awareness(
        monkeypatch,
        mirror_user=FakeMirrorUser(),
        mirror_self=_NoopCoordinator(),
    )

    result = awareness.run("hello")

    assert result["mirror_user_affect"] == "engaged"


def test_awareness_mirror_user_runs_before_mirror_self(monkeypatch):
    class FakeMirrorUser(Coordinator):
        name = "mirror_user"

        def process(self, packet: dict) -> dict:
            packet["mu_ran"] = True
            return packet

    class FakeMirrorSelf(Coordinator):
        name = "mirror_self"

        def process(self, packet: dict) -> dict:
            assert packet["mu_ran"] is True
            packet["ms_ran"] = True
            return packet

    awareness = _make_awareness(
        monkeypatch,
        mirror_user=FakeMirrorUser(),
        mirror_self=FakeMirrorSelf(),
    )

    result = awareness.run("hello")

    assert result["mu_ran"] is True
    assert result["ms_ran"] is True
