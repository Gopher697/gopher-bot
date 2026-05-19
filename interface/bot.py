from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coordinators.awareness import Awareness  # noqa: E402


awareness = Awareness()


def respond(message: str) -> str:
    packet = awareness.run(message)
    return packet.get(
        "final_response",
        packet.get("reason_output", "No response generated"),
    )
