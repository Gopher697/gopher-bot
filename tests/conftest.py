"""Shared test helpers - loaded automatically by pytest."""
from __future__ import annotations

from coordinators.awareness import Awareness
from coordinators.base import Coordinator


class _Noop(Coordinator):
    """Noop coordinator for test isolation."""
    name = "noop"

    def process(self, packet: dict) -> dict:
        return packet


# All optional coordinator kwargs wired to noops.
# Use this dict in every Awareness(...) construction that doesn't need real coordinators.
_NOOP_EXTRAS = {
    "orientation": None,
    "keeper": None,       # replaced at call time - see isolated_awareness()
    "mirror_user": None,
    "mirror_self": None,
    "ethos": None,
    "drive": None,
}


def isolated_awareness(**overrides) -> Awareness:
    """
    Return an Awareness with all optional coordinators set to noops.
    Pass keyword overrides to substitute specific coordinators under test.

    Example:
        aw = isolated_awareness(keeper=real_keeper)
    """
    kwargs = dict(
        orientation=_Noop(),
        keeper=_Noop(),
        mirror_user=_Noop(),
        mirror_self=_Noop(),
        ethos=_Noop(),
        drive=_Noop(),
    )
    kwargs.update(overrides)
    return Awareness(**kwargs)
