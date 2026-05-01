from __future__ import annotations

from pathlib import Path
from uuid import uuid4


def make_workspace(name: str) -> Path:
    """Create a unique workspace-local directory without pytest's tmp_path fixture."""

    root = Path("test_workspaces") / f"{name}-{uuid4().hex}"
    root.mkdir(parents=True)
    return root.resolve()
