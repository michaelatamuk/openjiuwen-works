"""A small MCP server over stdio: submit a signal, read tasks and evidence.

Deliberately narrow: there is no tool that approves a plan, opens a release gate or edits evidence.
An MCP client can add work and read proofs; a person still owns both gates. Results are plain text
built from the local home, and the server treats task titles and evidence as data.

    python -m works.mcp_server [--home PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from works.adapters.queue.store import Queue
from works.application.delivery.release import latest_run_dir, release_packet
from works.config.paths import WorksPaths, load_paths
from works.domain.errors import WorksError
from works.domain.records import Source, SourceKind

PROTOCOL = "2024-11-05"
TOOLS = [
    {
        "name": "submit_signal",
        "description": "Queue a new signal as a task. Never opens a gate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "title": {"type": "string"},
                "kind": {"type": "string", "enum": ["manual", "tracker", "detector"]},
                "product": {"type": "string"},
                "repo": {"type": "string"},
                "severity": {"type": "string", "enum": ["S1", "S2", "S3", "S4"]},
                "labels": {"type": "array", "items": {"type": "string"}},
                "links": {"type": "array", "items": {"type": "string"}},
                "author": {"type": "string"},
                "reproduction_hint": {"type": "string"},
                "dedupe_key": {"type": "string"},
            },
            "required": ["ref", "title"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List tasks with state, source and title.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 200}},
        },
    },
    {
        "name": "get_task",
        "description": "Read one task and its latest run summary.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "get_evidence",
        "description": "Read the evidence page for a task's latest run.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "get_release_packet",
        "description": "Read the release packet for a task.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
]


def _tool_submit(paths: WorksPaths, arguments: dict[str, Any]) -> dict[str, Any]:
    from works.application.intake.products import resolve_repo

    product = str(arguments.get("product") or "openjiuwen").strip()
    repo_raw = str(arguments.get("repo") or "").strip()
    from pathlib import Path

    repo = Path(repo_raw).expanduser().resolve() if repo_raw else resolve_repo(paths, product)
    source = Source(
        kind=SourceKind(str(arguments.get("kind") or "manual")),
        ref=str(arguments["ref"]),
        title=str(arguments["title"]),
        severity=arguments.get("severity"),
        labels=[str(item) for item in arguments.get("labels") or []],
        links=[str(item) for item in arguments.get("links") or []],
        author=arguments.get("author"),
        channel="mcp",
        reproduction_hint=arguments.get("reproduction_hint"),
        dedupe_key=arguments.get("dedupe_key"),
    )
    task, created = Queue(paths).submit(
        source=source, flow="fix-issue", product=product, repo=str(repo)
    )
    return {"task": task.id, "created": created, "state": task.state.value}


def _tool_list(paths: WorksPaths, arguments: dict[str, Any]) -> dict[str, Any]:
    limit = max(1, min(200, int(arguments.get("limit") or 50)))
    tasks = Queue(paths).list_tasks()[:limit]
    return {
        "tasks": [
            {
                "id": task.id,
                "state": task.state.value,
                "title": task.source.title or task.source.ref,
                "source": f"{task.source.kind.value}:{task.source.ref}",
            }
            for task in tasks
        ]
    }


def _tool_task(paths: WorksPaths, arguments: dict[str, Any]) -> dict[str, Any]:
    task = Queue(paths).load(str(arguments["task_id"]))
    return task.model_dump(mode="json")


def _tool_evidence(paths: WorksPaths, arguments: dict[str, Any]) -> dict[str, Any]:
    task_id = str(arguments["task_id"])
    run_dir = latest_run_dir(paths, task_id)
    if run_dir is None:
        return {"task": task_id, "evidence": None, "reason": "no finished run"}
    path = run_dir / "evidence.json"
    if not path.exists():
        return {"task": task_id, "evidence": None, "reason": "run has no evidence.json"}
    return {"task": task_id, "run": run_dir.name, "evidence": json.loads(path.read_text("utf-8"))}


def _tool_release(paths: WorksPaths, arguments: dict[str, Any]) -> dict[str, Any]:
    packet = release_packet(paths, str(arguments["task_id"]))
    return packet.as_dict()


HANDLERS = {
    "submit_signal": _tool_submit,
    "list_tasks": _tool_list,
    "get_task": _tool_task,
    "get_evidence": _tool_evidence,
    "get_release_packet": _tool_release,
}


def handle(request: dict[str, Any], paths: WorksPaths) -> dict[str, Any]:
    request_id = request.get("id")
    method = str(request.get("method") or "")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "openjiuwen-works", "version": "0.0.1"},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params") or {}
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"unknown tool {name!r}"},
            }
        try:
            result = handler(paths, arguments)
        except (WorksError, ValueError, KeyError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": f"error: {exc}"}],
                    "isError": True,
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                "isError": False,
            },
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"unknown method {method!r}"},
    }


def serve(paths: WorksPaths, stdin: Any = None, stdout: Any = None) -> None:
    source = stdin or sys.stdin
    sink = stdout or sys.stdout
    for line in source:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "invalid JSON"},
            }
        else:
            response = (
                handle(request, paths)
                if isinstance(request, dict)
                else {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "invalid request"},
                }
            )
        sink.write(json.dumps(response) + "\n")
        sink.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", default=None)
    args = parser.parse_args()
    serve(load_paths(args.home))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
