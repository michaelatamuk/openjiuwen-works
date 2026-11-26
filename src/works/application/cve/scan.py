"""Match pinned packages to advisories and turn each hit into a task."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from works.adapters.queue.store import Queue
from works.application.cve.feed import Advisory
from works.application.cve.lockfiles import LockedPackage, normalize, read_lockfiles
from works.application.cve.match import fixed_version, is_affected
from works.config.paths import WorksPaths
from works.domain.advisory import AdvisoryRef
from works.domain.enums import SourceKind
from works.domain.task import Severity, Source

SEVERITY_MAP: dict[str, Severity] = {
    "critical": "S1",
    "high": "S2",
    "moderate": "S3",
    "medium": "S3",
    "low": "S4",
    "unknown": "S3",
}


@dataclass(frozen=True)
class Hit:
    advisory: Advisory
    package: LockedPackage
    fixed: str | None


@dataclass(frozen=True)
class ScanResult:
    files: list[str] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)


def source_severity(severity: str) -> Severity:
    return SEVERITY_MAP.get(severity.strip().lower(), "S3")


def find_hits(packages: list[LockedPackage], advisories: list[Advisory]) -> list[Hit]:
    hits: list[Hit] = []
    seen: set[tuple[str, str, str]] = set()
    for advisory in advisories:
        ecosystem = advisory.ecosystem or "PyPI"
        if ecosystem.lower() in {"pypi", "python"}:
            ecosystem = "PyPI"
        for package in packages:
            if normalize(package.name) != normalize(advisory.package):
                continue
            if package.ecosystem.lower() != ecosystem.lower():
                continue
            if not is_affected(package.version, advisory, package.ecosystem):
                continue
            key = (advisory.id, normalize(package.name), package.version)
            if key in seen:
                continue
            seen.add(key)
            hits.append(Hit(advisory=advisory, package=package, fixed=fixed_version(advisory)))
    return hits


def _source(hit: Hit) -> Source:
    advisory = hit.advisory
    fixed = hit.fixed
    hint = (
        f"Upgrade {hit.package.name} from {hit.package.version} to "
        f"{fixed or 'a fixed release'} and run the repository checks."
    )
    return Source(
        kind=SourceKind.DETECTOR,
        ref=advisory.id,
        title=f"{advisory.id}: {hit.package.name} {hit.package.version}",
        severity=source_severity(advisory.severity),
        labels=["security", "cve", f"ecosystem:{hit.package.ecosystem.lower()}"],
        links=list(advisory.links),
        author="osv",
        channel="cve",
        reproduction_hint=hint,
        dedupe_key=f"cve:{advisory.id}:{normalize(hit.package.name)}@{hit.package.version}",
        advisory=AdvisoryRef(
            id=advisory.id,
            package=hit.package.name,
            version=hit.package.version,
            severity=advisory.severity,
            fixed=fixed,
            cvss=advisory.cvss,
            links=list(advisory.links),
        ),
    )


def scan_repository(
    paths: WorksPaths,
    repo: Path,
    advisories: list[Advisory],
    *,
    product: str = "openjiuwen",
    flow: str = "fix-issue",
    queue: Queue | None = None,
) -> ScanResult:
    packages, files = read_lockfiles(repo)
    hits = find_hits(packages, advisories)
    queue = queue or Queue(paths)
    created: list[str] = []
    existing: list[str] = []
    for hit in hits:
        task, is_new = queue.submit(
            source=_source(hit),
            flow=flow,
            product=product,
            repo=str(repo),
        )
        (created if is_new else existing).append(task.id)
    return ScanResult(files=files, hits=hits, created=created, existing=existing)
