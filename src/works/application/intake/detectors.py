"""Detector intake: firing alerts become ordinary queued tasks.

A detector is a machine signal: a monitoring rule or a log matcher. Works does not need a new task
kind for it. It reads a JSON payload (Alertmanager, a generic list, or NDJSON), keeps only firing
alerts, and returns one task per stable fingerprint.

Named detectors live in `.works/detectors.yaml` so the GUI can list them without accepting an
arbitrary path from a browser request.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from works.adapters.queue.store import Queue
from works.application.intake.products import resolve_repo
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.domain.records import Source, SourceKind, Task

CONFIG_PATH = Path(".works") / "detectors.yaml"
Transport = Callable[[str, dict[str, str]], tuple[int, Any]]


@dataclass(frozen=True)
class Alert:
    ref: str
    title: str
    severity: str = ""
    status: str = "firing"


class DetectorSource(BaseModel):
    file: str | None = None
    url: str | None = None
    product: str = Field(min_length=1)
    repo: str | None = None
    token_env: str = "DETECTOR_TOKEN"  # noqa: S105

    @model_validator(mode="after")
    def _check(self) -> DetectorSource:
        if bool(self.file) == bool(self.url):
            raise ValueError("a detector needs exactly one of file or url")
        return self


class DetectorConfig(BaseModel):
    detectors: dict[str, DetectorSource] = Field(default_factory=dict)


def load_config(paths: WorksPaths) -> DetectorConfig:
    path = paths.root / CONFIG_PATH
    if not path.exists():
        return DetectorConfig()
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read {CONFIG_PATH.as_posix()}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{CONFIG_PATH.as_posix()} must be a mapping")
    try:
        return DetectorConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{CONFIG_PATH.as_posix()} is invalid: {exc}") from exc


def _fingerprint(item: dict[str, Any]) -> str:
    raw = json.dumps(item, sort_keys=True, default=str).encode("utf-8")
    return f"alert-{hashlib.sha256(raw).hexdigest()[:16]}"


def parse_alerts(payload: Any) -> list[Alert]:
    if isinstance(payload, dict) and isinstance(payload.get("alerts"), list):
        items: list[Any] = payload["alerts"]
    elif isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = [payload]
    else:
        raise ConfigError("a detector payload must be an object or a list")
    alerts: list[Alert] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "firing").strip().lower()
        if status not in ("", "firing", "active", "open"):
            continue
        raw_labels = item.get("labels")
        raw_annotations = item.get("annotations")
        labels: dict[str, Any] = raw_labels if isinstance(raw_labels, dict) else {}
        annotations: dict[str, Any] = raw_annotations if isinstance(raw_annotations, dict) else {}
        name = str(
            item.get("alertname") or labels.get("alertname") or item.get("name") or ""
        ).strip()
        summary = str(
            annotations.get("summary")
            or item.get("summary")
            or item.get("title")
            or item.get("message")
            or ""
        ).strip()
        title = ": ".join(part for part in (name, summary) if part) or "Detector alert"
        ref = str(item.get("fingerprint") or item.get("id") or "").strip() or _fingerprint(item)
        severity = str(item.get("severity") or labels.get("severity") or "").strip()
        alerts.append(Alert(ref=ref, title=title, severity=severity, status=status or "firing"))
    return alerts


def read_alert_file(path: Path) -> list[Alert]:
    if not path.exists():
        raise ConfigError(f"detector file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        return parse_alerts(json.loads(text))
    except json.JSONDecodeError:
        alerts: list[Alert] = []
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                alerts.extend(parse_alerts(json.loads(line)))
            except json.JSONDecodeError as exc:
                raise ConfigError(f"{path}:{number}: {exc}") from exc
        return alerts


def _urllib_get(url: str, headers: dict[str, str]) -> tuple[int, Any]:
    request = urllib.request.Request(url, headers=headers)  # noqa: S310  # nosec B310
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310  # nosec B310
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"message": raw.decode("utf-8", errors="replace")}


def fetch_alerts(
    url: str,
    *,
    token: str | None = None,
    token_env: str = "DETECTOR_TOKEN",  # noqa: S107
    transport: Transport = _urllib_get,
) -> list[Alert]:
    headers = {"Accept": "application/json", "User-Agent": "openjiuwen-works"}
    token = token or os.environ.get(token_env)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, payload = transport(url, headers)
    if status != 200:
        raise ConfigError(f"detector refused intake: {status} {payload}")
    return parse_alerts(payload)


def alerts_for(paths: WorksPaths, name: str) -> list[Alert]:
    config = load_config(paths)
    source = config.detectors.get(name)
    if source is None:
        raise ConfigError(f"unknown detector {name!r}")
    if source.file:
        path = Path(source.file).expanduser()
        if not path.is_absolute():
            path = paths.root / path
        return read_alert_file(path)
    if source.url is None:
        raise ConfigError(f"detector {name!r} has no url")
    return fetch_alerts(source.url, token_env=source.token_env)


def ingest_alerts(
    queue: Queue, *, product: str, repo: str, alerts: list[Alert]
) -> list[tuple[Task, bool]]:
    created: list[tuple[Task, bool]] = []
    for alert in alerts:
        task, was_created = queue.submit(
            source=Source(kind=SourceKind.DETECTOR, ref=alert.ref, title=alert.title),
            flow="fix-issue",
            product=product,
            repo=repo,
        )
        created.append((task, was_created))
    return created


def ingest_named(paths: WorksPaths, name: str) -> list[tuple[Task, bool]]:
    config = load_config(paths)
    source = config.detectors.get(name)
    if source is None:
        raise ConfigError(f"unknown detector {name!r}")
    repo = source.repo or str(resolve_repo(paths, source.product))
    return ingest_alerts(
        Queue(paths), product=source.product, repo=repo, alerts=alerts_for(paths, name)
    )
