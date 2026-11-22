"""Answer a question about one run with openjiuwen's real model runtime.

This worker runs in agent-core's Python, so Works does not inherit the runtime's dependency tree.
It reads a JSON request on stdin and writes JSON lines on stdout:

    {"type": "delta", "text": "..."}
    {"type": "done", "text": "...", "model": "...", "tokens": 0, "usd": 0.0}
    {"type": "error", "error": "..."}

The answer is advisory. It cannot approve, release, retry or change a task.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

SYSTEM = """You are Mira, the worklog assistant inside openJiuwen Works.
Answer only from the run context below. If the context does not contain the answer, say
"Not recorded in this run." Do not invent a commit, a test, a gate, a release or a delivery.
You are advisory: you cannot approve, release, retry or change anything. Be concise: 1-5 sentences.
When useful, name the evidence you used (for example "verdict", "release blockers", "confirmation").
"""

COMMENTARY_SYSTEM = """You are Mira's advisory commentary layer inside openJiuwen Works.
Write exactly three short messages about the recorded run: builder, inspector, reporter.
Use only the run context. Never invent a commit, test, gate, release or delivery. Each message is
1-2 sentences, plain text, no markdown. Commentary is not evidence and cannot change a verdict.
Return JSON only in this shape:
{"messages": [
  {"role": "builder", "text": "..."},
  {"role": "inspector", "text": "..."},
  {"role": "reporter", "text": "..."}
]}
"""

# openjiuwen logs to stdout; keep stdout as protocol and send library output to stderr.
PROTOCOL = sys.stdout
sys.stdout = sys.stderr


def _emit(payload: dict[str, Any]) -> None:
    PROTOCOL.write(json.dumps(payload) + "\n")
    PROTOCOL.flush()


def _config() -> tuple[str, str, str]:
    key = os.environ.get("WORKS_MODEL_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("no model key: set ANTHROPIC_API_KEY or WORKS_MODEL_KEY")
    base = os.environ.get("WORKS_MODEL_BASE") or "https://api.deepseek.com/anthropic"
    model = os.environ.get("WORKS_AGENT_MODEL") or "deepseek-chat"
    return key, base, model


def _messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    context = str(payload.get("context") or "")
    kind = str(payload.get("kind") or "ask")
    if kind == "commentary":
        messages = [{"role": "system", "content": COMMENTARY_SYSTEM}]
        messages.append(
            {
                "role": "user",
                "content": "RUN CONTEXT\n\n" + context[:12000] + "\n\nWrite the three messages.",
            }
        )
        return messages
    question = str(payload.get("question") or "").strip()
    history = payload.get("history") or []
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM}]
    if context:
        messages.append(
            {
                "role": "user",
                "content": "RUN CONTEXT\n\n" + context[:12000],
            }
        )
    for item in history[-6:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:4000]})
    messages.append({"role": "user", "content": question})
    return messages


def _json_object(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.startswith("json"):
            clean = clean[4:]
    start = clean.find("{")
    end = clean.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("model returned no JSON object")
    parsed = json.loads(clean[start : end + 1])
    if not isinstance(parsed, dict):
        raise RuntimeError("model returned a non-object")
    return parsed


async def _run(payload: dict[str, Any]) -> None:
    from openjiuwen.core.foundation.llm import (
        Model,
        ModelClientConfig,
        ModelRequestConfig,
        ProviderType,
    )

    key, base, model_name = _config()
    client = ModelClientConfig(
        client_provider=ProviderType.Anthropic,
        api_key=key,
        api_base=base,
        timeout=120.0,
    )
    model = Model(
        client,
        ModelRequestConfig(model=model_name, temperature=0.2, max_tokens=700),
    )
    messages = _messages(payload)
    kind = str(payload.get("kind") or "ask")
    stream = bool(payload.get("stream"))
    _emit({"type": "start", "model": model_name})
    if kind == "commentary":
        result = await model.invoke(messages, max_tokens=900)
        text = str(getattr(result, "content", result) or "")
        usage = getattr(result, "usage_metadata", None)
        parsed = _json_object(text)
        _emit(
            {
                "type": "done",
                "messages": parsed.get("messages") or [],
                "model": model_name,
                "tokens": int(getattr(usage, "total_tokens", 0) or 0),
                "usd": float(getattr(usage, "total_cost", 0.0) or 0.0),
            }
        )
        return
    if not stream:
        result = await model.invoke(messages, max_tokens=700)
        text = str(getattr(result, "content", result) or "")
        usage = getattr(result, "usage_metadata", None)
        _emit(
            {
                "type": "done",
                "text": text,
                "model": model_name,
                "tokens": int(getattr(usage, "total_tokens", 0) or 0),
                "usd": float(getattr(usage, "total_cost", 0.0) or 0.0),
            }
        )
        return
    parts: list[str] = []
    tokens = 0
    usd = 0.0
    async for chunk in model.stream(messages, max_tokens=700):
        text = str(getattr(chunk, "content", "") or "")
        if text:
            parts.append(text)
            _emit({"type": "delta", "text": text})
        usage = getattr(chunk, "usage_metadata", None)
        if usage is not None:
            tokens = int(getattr(usage, "total_tokens", tokens) or tokens)
            usd = float(getattr(usage, "total_cost", usd) or usd)
    _emit(
        {
            "type": "done",
            "text": "".join(parts),
            "model": model_name,
            "tokens": tokens,
            "usd": usd,
        }
    )


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise RuntimeError("request must be an object")
        asyncio.run(_run(payload))
    except Exception as exc:  # a worker failure is a typed line, not a trace on stdout
        _emit({"type": "error", "error": str(exc)})
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
