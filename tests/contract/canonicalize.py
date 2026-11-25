"""Canonicalize API payloads so two responses can be compared without noise.

The rules are deliberately narrow: only fields that are expected to differ between a seeded home
and a live one are replaced. Everything else must match exactly.
"""

from __future__ import annotations

import contextlib
import re
import sys
from pathlib import Path
from typing import Any

TASK_ID = re.compile(r"t-[0-9a-f]{12}")
RUN_ID = re.compile(r"r-\d{8}T\d{6}-[0-9a-f]{6}")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")
HEX64 = re.compile(r"[0-9a-f]{64}")
SHORT_HEX = re.compile(r"\b[0-9a-f]{7,63}\b")
COMMIT_ARTIFACT = re.compile(r"commit [0-9a-f]{7,40}")
PROOF_ARTIFACT = re.compile(r"proof [0-9a-f]{7,40}")
WINDOWS_PATH = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/][^\s"\'<>]*')

TIMESTAMP_KEYS = frozenset(
    {
        "at",
        "ts",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
        "deadline",
        "wake_deadline",
        "expires_at",
        "date",
    }
)
SHA_KEYS = frozenset(
    {
        "sha256",
        "diff_sha256",
        "proof_sha256",
        "checks_sha",
        "output_sha256",
        "plan_hash",
    }
)
COMMIT_KEYS = frozenset({"commit", "base_commit", "evidence_commit"})
TASK_ID_KEYS = frozenset({"task_id", "previous_task_id"})
DURATION_KEYS = frozenset({"duration_ms", "median_duration_ms", "wall", "elapsed_ms", "waiting_ms"})
OUTPUT_KEYS = frozenset({"stdout_tail", "output_tail", "stdout", "stderr"})
TEXT_BLOB_KEYS = frozenset({"proof_md"})
RUN_ID_KEYS = frozenset({"run_id"})


def _path_variants(path: Path) -> set[str]:
    variants = {str(path)}
    with contextlib.suppress(OSError):
        variants.add(str(path.resolve()))
    expanded: set[str] = set()
    for raw in variants:
        expanded.add(raw)
        expanded.add(raw.replace("\\", "/"))
    return {raw for raw in expanded if raw}


def _replace_paths(text: str, home: Path | None, repo: Path | None) -> str:
    pairs: list[tuple[str, str]] = []
    if home is not None:
        pairs.extend((raw, "<home>") for raw in _path_variants(home))
    if repo is not None:
        pairs.extend((raw, "<repo>") for raw in _path_variants(repo))
    executable = Path(sys.executable)
    for raw in _path_variants(executable) | _path_variants(executable.parent):
        pairs.append((raw, "<python>"))
    for raw, placeholder in sorted(pairs, key=lambda pair: len(pair[0]), reverse=True):
        if raw:
            text = text.replace(raw, placeholder)
    return text


def _canon_string(text: str, home: Path | None, repo: Path | None) -> str:
    text = _replace_paths(text, home, repo)
    if any(marker in text for marker in ("<home>", "<repo>", "<python>")):
        text = text.replace("\\", "/")
    text = text.replace("/api/v1/", "/api/")
    text = WINDOWS_PATH.sub("<path>", text)
    text = TASK_ID.sub("<task-id>", text)
    text = RUN_ID.sub("<run-id>", text)
    text = TIMESTAMP.sub("<timestamp>", text)
    text = COMMIT_ARTIFACT.sub("commit <commit>", text)
    text = PROOF_ARTIFACT.sub("proof <sha256>", text)
    text = HEX64.sub("<sha256>", text)
    text = SHORT_HEX.sub("<sha>", text)
    return text


def _canon_field(key: str, value: Any, home: Path | None, repo: Path | None) -> Any:
    if key == "runtime" and isinstance(value, dict):
        return {str(name): "<runtime>" for name in value}
    if key == "reproduction_env" and isinstance(value, dict):
        masked = {}
        for name, item in value.items():
            if isinstance(item, str) and re.fullmatch(r"\d+\.\d+(?:\.\d+)?", item):
                masked[str(name)] = "<version>"
            else:
                masked[str(name)] = canonicalize(item, home=home, repo=repo)
        return masked
    if key in DURATION_KEYS and isinstance(value, (int, float)):
        return 0
    if key in OUTPUT_KEYS and isinstance(value, str):
        return "<output>"
    if key in TEXT_BLOB_KEYS and isinstance(value, str):
        return "<markdown>"
    if isinstance(value, str) and value:
        if key in TIMESTAMP_KEYS and TIMESTAMP.fullmatch(value):
            return "<timestamp>"
        if key in SHA_KEYS:
            return "<sha256>"
        if key in COMMIT_KEYS:
            return "<commit>"
        if key in TASK_ID_KEYS:
            return "<task-id>"
        if key in RUN_ID_KEYS:
            return "<run-id>"
    return canonicalize(value, home=home, repo=repo)


def canonicalize(value: Any, *, home: Path | None = None, repo: Path | None = None) -> Any:
    """Return a copy with ids, times, hashes, commits and absolute paths masked."""
    if isinstance(value, dict):
        return {key: _canon_field(str(key), item, home, repo) for key, item in value.items()}
    if isinstance(value, list):
        return [canonicalize(item, home=home, repo=repo) for item in value]
    if isinstance(value, str):
        return _canon_string(value, home, repo)
    return value
