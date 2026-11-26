"""OSV-style advisories, expanded to one record per affected package.

The loader is deliberately tolerant: a file may hold a single record, a list, or a `{"vulns": []}`
wrapper, which is what the OSV API returns. Nothing here calls the network unless `fetch_osv` is
used explicitly.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from works.domain.errors import ConfigError

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
SEVERITIES = ("low", "moderate", "medium", "high", "critical")


@dataclass(frozen=True)
class Advisory:
    id: str
    summary: str
    severity: str
    package: str
    ecosystem: str
    versions: tuple[str, ...] = ()
    ranges: tuple[tuple[str, str | None, str | None], ...] = ()
    cvss: float | None = None
    links: tuple[str, ...] = field(default_factory=tuple)


def _severity(vuln: dict[str, object]) -> tuple[str, float | None]:
    for key in ("database_specific", "ecosystem_specific"):
        block = vuln.get(key)
        if isinstance(block, dict):
            label = str(block.get("severity") or "").strip().lower()
            if label in SEVERITIES:
                cvss = block.get("cvss")
                return label, float(cvss) if isinstance(cvss, (int, float)) else None
    entries = vuln.get("severity")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            score = entry.get("score")
            if isinstance(score, (int, float)):
                value = float(score)
                label = (
                    "critical"
                    if value >= 9
                    else "high"
                    if value >= 7
                    else "moderate"
                    if value >= 4
                    else "low"
                )
                return label, value
    return "unknown", None


def _links(vuln: dict[str, object]) -> tuple[str, ...]:
    urls: list[str] = []
    references = vuln.get("references")
    for item in references if isinstance(references, list) else []:
        if isinstance(item, dict) and item.get("url"):
            urls.append(str(item["url"]))
    return tuple(dict.fromkeys(urls))


def _expand(vuln: dict[str, object]) -> list[Advisory]:
    identifier = str(vuln.get("id") or "").strip()
    raw_aliases = vuln.get("aliases")
    aliases = [str(item) for item in raw_aliases] if isinstance(raw_aliases, list) else []
    cve = next((item for item in aliases if item.startswith("CVE-")), "")
    advisory_id = cve or identifier
    if not advisory_id:
        return []
    summary = str(vuln.get("summary") or vuln.get("details") or "").strip()
    severity, cvss = _severity(vuln)
    links = _links(vuln)
    expanded: list[Advisory] = []
    raw_affected = vuln.get("affected")
    for affected in raw_affected if isinstance(raw_affected, list) else []:
        if not isinstance(affected, dict):
            continue
        package = affected.get("package")
        if not isinstance(package, dict):
            continue
        name = str(package.get("name") or "").strip()
        ecosystem = str(package.get("ecosystem") or "").strip()
        if not name:
            continue
        ranges: list[tuple[str, str | None, str | None]] = []
        for entry in affected.get("ranges") or []:
            if not isinstance(entry, dict):
                continue
            introduced: str | None = None
            for event in entry.get("events") or []:
                if not isinstance(event, dict):
                    continue
                if "introduced" in event:
                    if introduced is not None:
                        ranges.append((introduced, None, None))
                    introduced = str(event["introduced"])
                elif "fixed" in event and introduced is not None:
                    ranges.append((introduced, str(event["fixed"]), None))
                    introduced = None
                elif "last_affected" in event and introduced is not None:
                    ranges.append((introduced, None, str(event["last_affected"])))
                    introduced = None
            if introduced is not None:
                ranges.append((introduced, None, None))
        raw_versions = affected.get("versions")
        versions = (
            tuple(str(item) for item in raw_versions) if isinstance(raw_versions, list) else ()
        )
        expanded.append(
            Advisory(
                id=advisory_id,
                summary=summary,
                severity=severity,
                package=name,
                ecosystem=ecosystem,
                versions=versions,
                ranges=tuple(ranges),
                cvss=cvss,
                links=links,
            )
        )
    return expanded


def parse_feed(payload: object) -> list[Advisory]:
    if isinstance(payload, dict) and isinstance(payload.get("vulns"), list):
        records = payload["vulns"]
    elif isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = [payload]
    else:
        raise ConfigError("an advisory feed must be a record, a list or a {vulns: []} object")
    advisories: list[Advisory] = []
    for record in records:
        if isinstance(record, dict):
            advisories.extend(_expand(record))
    return advisories


def load_feed(path: Path) -> list[Advisory]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read the advisory feed {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"the advisory feed {path} is not JSON: {exc}") from exc
    return parse_feed(payload)


def fetch_osv(packages: list[tuple[str, str, str]], *, timeout: float = 15.0) -> list[Advisory]:
    """Query the OSV batch API. `packages` is (name, version, ecosystem)."""
    if not packages:
        return []
    body = json.dumps(
        {
            "queries": [
                {"package": {"name": name, "ecosystem": ecosystem}, "version": version}
                for name, version, ecosystem in packages
            ]
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OSV_BATCH,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConfigError(f"OSV is unreachable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"OSV returned invalid JSON: {exc}") from exc
    advisories: list[Advisory] = []
    for result in payload.get("results") or []:
        if not isinstance(result, dict):
            continue
        for vuln in result.get("vulns") or []:
            if isinstance(vuln, dict):
                advisories.extend(_expand(vuln))
    return advisories
