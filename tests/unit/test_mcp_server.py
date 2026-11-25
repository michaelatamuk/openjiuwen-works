from __future__ import annotations

from works.adapters.queue.store import Queue
from works.mcp_server import handle


def _call(paths, name: str, arguments: dict, request_id: int = 1) -> dict:
    return handle(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        paths,
    )


def test_the_tool_list_has_no_gate_tools(paths) -> None:
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, paths)
    names = {tool["name"] for tool in response["result"]["tools"]}

    assert "submit_signal" in names
    assert names.isdisjoint({"approve_plan", "release", "approve_release", "merge_task"})


def test_submit_signal_creates_a_task_and_lists_it(paths, repo) -> None:
    created = _call(
        paths,
        "submit_signal",
        {"ref": "MCP-1", "title": "from an MCP client", "repo": str(repo.path)},
    )
    assert created["result"]["isError"] is False
    task_id = Queue(paths).list_tasks()[0].id

    listed = _call(paths, "list_tasks", {"limit": 10})
    text = listed["result"]["content"][0]["text"]

    assert task_id in text
    assert "from an MCP client" in text


def test_an_unknown_tool_is_an_error(paths) -> None:
    response = _call(paths, "approve_plan", {})

    assert response["error"]["code"] == -32601


def test_an_unknown_method_is_an_error(paths) -> None:
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "nope"}, paths)

    assert response["error"]["code"] == -32601
