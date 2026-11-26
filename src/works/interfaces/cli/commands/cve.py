"""`works cve` — find advisories for a repository's pinned dependencies."""

from __future__ import annotations

import argparse
from pathlib import Path

from works.application.cve.feed import fetch_osv, load_feed
from works.application.cve.lockfiles import read_lockfiles
from works.application.cve.scan import scan_repository
from works.domain.errors import ConfigError
from works.interfaces.cli.commands.common import _emit, _paths


def cmd_cve(args: argparse.Namespace) -> int:
    paths = _paths(args)
    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        raise ConfigError(f"not a repository: {repo}")
    if args.feed is not None:
        advisories = load_feed(Path(args.feed))
    elif args.osv:
        packages, _files = read_lockfiles(repo)
        advisories = fetch_osv([(item.name, item.version, item.ecosystem) for item in packages])
    else:
        raise ConfigError("pass --feed FILE for an offline scan, or --osv to query OSV")
    result = scan_repository(
        paths,
        repo,
        advisories,
        product=args.product,
    )
    if args.json:
        _emit(
            {
                "files": result.files,
                "hits": [
                    {
                        "id": hit.advisory.id,
                        "package": hit.package.name,
                        "version": hit.package.version,
                        "severity": hit.advisory.severity,
                        "fixed": hit.fixed,
                    }
                    for hit in result.hits
                ],
                "created": result.created,
                "existing": result.existing,
            }
        )
        return 0
    if not result.files:
        print("no lockfile found (uv.lock, poetry.lock, requirements.txt or package-lock.json)")
        return 0
    print(f"lockfiles: {', '.join(result.files)}")
    if not result.hits:
        print("no affected package")
        return 0
    for hit in result.hits:
        fixed = f" -> {hit.fixed}" if hit.fixed else ""
        print(
            f"{hit.advisory.id}  {hit.package.name} {hit.package.version}"
            f"  {hit.advisory.severity}{fixed}"
        )
    if result.created:
        print(f"created: {', '.join(result.created)}")
    if result.existing:
        print(f"already queued: {', '.join(result.existing)}")
    return 0
