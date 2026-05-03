import pytest

from gopher_workbench_mcp.server import list_sop_names, list_sops_payload, read_sop_content
from gopher_workbench_mcp.workbench import WorkbenchError


def test_list_sops_returns_expected_names() -> None:
    assert list_sop_names() == [
        "ai-coding-loop",
        "modding-workflow",
        "troubleshooting",
        "assistant-style",
        "workbench-orientation",
    ]


def test_list_sops_tool_shape() -> None:
    assert list_sops_payload() == {
        "sops": [
            "ai-coding-loop",
            "modding-workflow",
            "troubleshooting",
            "assistant-style",
            "workbench-orientation",
        ]
    }


def test_read_sop_returns_bundled_markdown() -> None:
    content = read_sop_content("ai-coding-loop")

    assert content.startswith("# AI Coding Loop")
    assert "Run targeted tests" in content


@pytest.mark.parametrize("name", ["../ai-coding-loop", "sops/ai-coding-loop.md", "D:/gopher-workbench-mcp/sops/ai-coding-loop.md"])
def test_read_sop_rejects_path_like_input(name: str) -> None:
    with pytest.raises(WorkbenchError, match="Unknown SOP"):
        read_sop_content(name)


def test_read_sop_rejects_unknown_name() -> None:
    with pytest.raises(WorkbenchError, match="Unknown SOP"):
        read_sop_content("not-a-real-sop")
