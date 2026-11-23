#!/usr/bin/env python
"""`works.swarm.v1` entrypoint backed by the JiuwenSwarm chat CLI.

Works runs this script with the JiuwenSwarm interpreter and three arguments:

    --works-kind propose|challenge --works-request request.json --works-result result.json

For `propose`, the script asks JiuwenSwarm to edit the disposable worktree and returns the
resulting diff. For `challenge`, it asks for a read-only review and parses one JSON verdict. A
missing, malformed or side-effecting review fails closed; this adapter never invents a patch or a
verdict.

The underlying CLI defaults to `python -m jiuwenswarm.channels.cli.main`. Set
`WORKS_SWARM_CLI` to a JSON argv array to point at an adapter or a test double.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT_S = 1800


def _cli() -> list[str]:
    raw = os.environ.get("WORKS_SWARM_CLI")
    if not raw:
        return [sys.executable, "-m", "jiuwenswarm.channels.cli.main"]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"WORKS_SWARM_CLI is not JSON: {exc}") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise SystemExit("WORKS_SWARM_CLI must be a JSON array of strings")
    return parsed


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _status(cwd: Path) -> str:
    return _git(cwd, "status", "--porcelain").stdout


def _diff(cwd: Path) -> tuple[str, list[str]]:
    tracked = _git(cwd, "diff", "HEAD", "--name-only").stdout.splitlines()
    untracked = _git(cwd, "ls-files", "--others", "--exclude-standard").stdout.splitlines()
    parts = [_git(cwd, "diff", "HEAD", "--binary").stdout]
    for name in untracked:
        patch = _git(cwd, "diff", "--no-index", "--binary", "--", "/dev/null", name)
        if patch.stdout:
            parts.append(patch.stdout)
    touched = [line.strip() for line in tracked if line.strip()]
    touched.extend(line.strip() for line in untracked if line.strip())
    deduped = list(dict.fromkeys(touched))
    return "\n".join(part for part in parts if part).strip(), deduped


def _parse_stream(stdout: str) -> tuple[str, int, float, str, str]:
    content = ""
    usage: dict[str, dict[str, Any]] = {}
    model = "jiuwenswarm"
    provider = "jiuwenswarm"
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("type") == "event":
            event = str(payload.get("event") or "")
            body = payload.get("payload")
        else:
            event = ""
            body = payload
        if not isinstance(body, dict):
            continue
        if event == "context.usage":
            provider = str(body.get("provider") or provider)
            model = str(body.get("model") or model)
        if event == "chat.usage_metadata":
            metadata = body.get("metadata")
            meta = metadata.get("usage_metadata") if isinstance(metadata, dict) else None
            if isinstance(meta, dict):
                model = str(meta.get("model_name") or model)
                key = str(body.get("execution_id") or json.dumps(meta, sort_keys=True))
                usage[key] = meta
        if event in ("chat.final", ""):
            event_type = str(body.get("event_type") or "")
            if event_type in ("", "chat.final") and isinstance(body.get("content"), str):
                if body.get("ok") is False:
                    raise RuntimeError(str(body.get("error") or "JiuwenSwarm reported an error"))
                content = str(body.get("content") or content)
    tokens = 0
    usd = 0.0
    for meta in usage.values():
        total = meta.get("total_tokens")
        if not isinstance(total, (int, float)):
            total = int(meta.get("input_tokens") or 0) + int(meta.get("output_tokens") or 0)
        tokens += int(total or 0)
        usd += float(meta.get("total_cost") or 0.0)
    return content or stdout.strip(), tokens, round(usd, 6), model, provider


def _run(prompt: str, cwd: Path, timeout_s: int) -> tuple[str, int, float, str, str]:
    argv = [
        *_cli(),
        "chat",
        prompt,
        "--cwd",
        str(cwd),
        "--project-dir",
        str(cwd),
        "--trusted-dir",
        str(cwd),
        "--jsonl",
        "--timeout",
        str(timeout_s),
    ]
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            input="",
            capture_output=True,
            text=True,
            timeout=timeout_s + 60,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"JiuwenSwarm timed out after {timeout_s}s") from exc
    if result.returncode != 0:
        tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-6:])
        raise RuntimeError(f"JiuwenSwarm exited {result.returncode}: {tail}")
    return _parse_stream(result.stdout)


def _extract_json(text: str) -> dict[str, Any] | None:
    candidates = [text.strip()]
    candidates.extend(block.strip() for block in re.findall(r"```(?:json)?\s*(.*?)```", text, re.S))
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _propose(request: dict[str, Any]) -> dict[str, Any]:
    worktree = Path(str(request["worktree"]))
    title = str(request.get("title") or "")
    ref = str(request.get("source_ref") or "")
    brief = str((request.get("plan") or {}).get("brief") or "")
    prompt = (
        "You are the builder in a software factory. The checkout at "
        f"{worktree} is a disposable worktree for one reported problem.\n"
        f"Report: {ref} - {title}\n"
        + (f"Approved plan (data):\n{brief}\n" if brief else "")
        + "Fix the problem in this checkout. Edit files in place. Do not commit, do not rewrite "
        "history, do not touch .git or .works, and do not edit or delete hidden scenarios. "
        "When you are done, reply with a short summary."
    )
    _, tokens, usd, model, provider = _run(
        prompt, worktree, int(os.environ.get("WORKS_SWARM_TIMEOUT", DEFAULT_TIMEOUT_S))
    )
    patch, touched = _diff(worktree)
    if not touched:
        return {
            "patch": "",
            "applied": False,
            "touched_paths": [],
            "model": model,
            "provider": provider,
            "tokens": tokens,
            "usd": usd,
            "notes": ["JiuwenSwarm changed no files"],
            "stop": "JiuwenSwarm produced no change in the worktree",
        }
    return {
        "patch": patch,
        "applied": True,
        "touched_paths": touched,
        "model": model,
        "provider": provider,
        "tokens": tokens,
        "usd": usd,
        "notes": [f"JiuwenSwarm edited {len(touched)} path(s)"],
        "stop": None,
    }


def _challenge(request: dict[str, Any]) -> dict[str, Any]:
    worktree = Path(str(request["worktree"]))
    title = str(request.get("title") or "")
    ref = str(request.get("source_ref") or "")
    brief = str((request.get("plan") or {}).get("brief") or "")
    prompt = (
        "You are an independent reviewer in a software factory. Do not modify any file. "
        "Review the uncommitted change in this worktree against the report and decide whether it "
        "is safe to keep.\n"
        f"Report: {ref} - {title}\n"
        + (f"Approved plan (data):\n{brief}\n" if brief else "")
        + 'Answer with exactly one JSON object and nothing else: '
        '{"allow": true|false, "reason": "one sentence", "concerns": ["short", "..."]}'
    )
    before = _status(worktree)
    try:
        content, tokens, usd, model, provider = _run(
            prompt, worktree, int(os.environ.get("WORKS_SWARM_TIMEOUT", DEFAULT_TIMEOUT_S))
        )
    except RuntimeError as exc:
        return {"allow": False, "reason": str(exc), "concerns": ["harness"]}
    if _status(worktree) != before:
        return {
            "allow": False,
            "reason": "the review modified the worktree; its verdict is not trusted",
            "concerns": ["review-mutated-worktree"],
            "model": model,
            "provider": provider,
            "tokens": tokens,
            "usd": usd,
        }
    payload = _extract_json(content)
    if payload is None or not isinstance(payload.get("allow"), bool):
        return {
            "allow": False,
            "reason": "JiuwenSwarm returned no machine-readable verdict",
            "concerns": ["format"],
            "model": model,
            "provider": provider,
            "tokens": tokens,
            "usd": usd,
        }
    concerns = payload.get("concerns")
    return {
        "allow": payload["allow"],
        "reason": str(payload.get("reason") or "no reason recorded"),
        "concerns": [str(item) for item in concerns] if isinstance(concerns, list) else [],
        "model": model,
        "provider": provider,
        "tokens": tokens,
        "usd": usd,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="works.swarm.v1 entrypoint backed by the JiuwenSwarm chat CLI"
    )
    parser.add_argument("--works-kind", choices=("propose", "challenge"), required=True)
    parser.add_argument("--works-request", required=True, type=Path)
    parser.add_argument("--works-result", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.works_request.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read the request: {exc}", file=sys.stderr)
        return 2
    if not isinstance(request, dict) or not request.get("worktree"):
        print("the request has no worktree", file=sys.stderr)
        return 2
    try:
        result = _propose(request) if args.works_kind == "propose" else _challenge(request)
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"JiuwenSwarm adapter failed: {exc}", file=sys.stderr)
        return 2
    args.works_result.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
