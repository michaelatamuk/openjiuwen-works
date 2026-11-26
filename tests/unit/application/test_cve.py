from __future__ import annotations

import json
from pathlib import Path

from works.adapters.queue.store import Queue
from works.application.cve import feed
from works.application.cve.feed import Advisory, fetch_osv, load_feed, parse_feed
from works.application.cve.lockfiles import normalize, read_lockfiles
from works.application.cve.match import fixed_version, is_affected
from works.application.cve.scan import find_hits, scan_repository
from works.domain.advisory import AdvisoryRef
from works.domain.evidence import Evidence, render_summary, write_evidence
from works.domain.evidence.render import render_markdown

OSV = {
    "id": "GHSA-aaaa-bbbb-cccc",
    "aliases": ["CVE-2026-0001"],
    "summary": "The parser crashes on a truncated line",
    "database_specific": {"severity": "HIGH"},
    "affected": [
        {
            "package": {"name": "demo-pkg", "ecosystem": "PyPI"},
            "ranges": [
                {"type": "ECOSYSTEM", "events": [{"introduced": "1.0.0"}, {"fixed": "1.4.2"}]}
            ],
        }
    ],
    "references": [{"type": "ADVISORY", "url": "https://example.test/advisory"}],
}


def _repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    return repo


def _requirements(repo: Path) -> None:
    (repo / "requirements.txt").write_text(
        "demo_pkg[extra]==1.2.0  # pinned\n"
        "other==2.0.0; python_version > '3.8'\n"
        "unpinned>=1.0\n"
        "-r another.txt\n",
        encoding="utf-8",
    )


def test_an_osv_record_expands_to_its_cve_and_range() -> None:
    advisories = parse_feed(OSV)

    assert len(advisories) == 1
    advisory = advisories[0]
    assert advisory.id == "CVE-2026-0001"
    assert advisory.severity == "high"
    assert advisory.package == "demo-pkg"
    assert advisory.ranges == (("1.0.0", "1.4.2", None),)
    assert advisory.links == ("https://example.test/advisory",)


def test_a_feed_accepts_a_wrapper_a_list_and_a_single_record(tmp_path: Path) -> None:
    wrapper = tmp_path / "wrapper.json"
    wrapper.write_text(json.dumps({"vulns": [OSV]}), encoding="utf-8")
    single = tmp_path / "single.json"
    single.write_text(json.dumps(OSV), encoding="utf-8")

    assert len(load_feed(wrapper)) == 1
    assert len(load_feed(single)) == 1


def test_requirements_keep_pins_and_ignore_ranges(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _requirements(repo)

    packages, files = read_lockfiles(repo)

    assert files == ["requirements.txt"]
    assert {(item.name, item.version) for item in packages} == {
        ("demo_pkg", "1.2.0"),
        ("other", "2.0.0"),
    }


def test_uv_lock_and_package_lock_are_read(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "uv.lock").write_text(
        '[[package]]\nname = "demo-pkg"\nversion = "1.2.0"\n', encoding="utf-8"
    )
    (repo / "package-lock.json").write_text(
        json.dumps({"packages": {"": {}, "node_modules/left-pad": {"version": "1.0.0"}}}),
        encoding="utf-8",
    )

    packages, files = read_lockfiles(repo)

    assert set(files) == {"uv.lock", "package-lock.json"}
    assert {(item.name, item.ecosystem) for item in packages} == {
        ("demo-pkg", "PyPI"),
        ("left-pad", "npm"),
    }


def test_names_are_normalized() -> None:
    assert normalize("Demo_Pkg") == "demo-pkg"
    assert normalize("zope.interface") == "zope-interface"


def test_ranges_include_and_exclude_the_right_versions() -> None:
    advisory = parse_feed(OSV)[0]

    assert is_affected("1.2.0", advisory, "PyPI") is True
    assert is_affected("1.0.0", advisory, "PyPI") is True
    assert is_affected("1.4.2", advisory, "PyPI") is False
    assert is_affected("0.9.0", advisory, "PyPI") is False
    assert fixed_version(advisory) == "1.4.2"


def test_npm_versions_compare_numerically() -> None:
    advisory = Advisory(
        id="CVE-2026-0002",
        summary="x",
        severity="high",
        package="left-pad",
        ecosystem="npm",
        ranges=(("1.0.0", "1.3.0", None),),
    )

    assert is_affected("1.2.9", advisory, "npm") is True
    assert is_affected("1.3.0", advisory, "npm") is False
    assert is_affected("1.10.0", advisory, "npm") is False


def test_a_scan_creates_one_task_per_package_and_version(paths, tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _requirements(repo)

    result = scan_repository(paths, repo, parse_feed(OSV), product="P")

    assert len(result.hits) == 1
    assert len(result.created) == 1
    task = Queue(paths).load(result.created[0])
    assert task.source.channel == "cve"
    assert task.source.ref == "CVE-2026-0001"
    assert task.source.severity == "S2"
    assert task.source.advisory is not None
    assert task.source.advisory.package == "demo_pkg"


def test_a_second_scan_finds_the_existing_task(paths, tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _requirements(repo)

    first = scan_repository(paths, repo, parse_feed(OSV), product="P")
    second = scan_repository(paths, repo, parse_feed(OSV), product="P")

    assert second.created == []
    assert second.existing == first.created
    assert len(Queue(paths).list_tasks()) == 1


def test_a_package_without_a_hit_is_ignored(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _requirements(repo)
    advisory = parse_feed(OSV)[0]

    packages, _ = read_lockfiles(repo)

    assert find_hits([item for item in packages if item.name != "demo_pkg"], [advisory]) == []


def test_the_advisory_is_rendered_and_bound() -> None:
    from tests.unit.domain.test_evidence import fixed_evidence

    evidence = fixed_evidence().model_copy(
        update={
            "advisory": AdvisoryRef(
                id="CVE-2026-0001",
                package="demo-pkg",
                version="1.2.0",
                severity="high",
                fixed="1.4.2",
                links=["https://example.test/advisory"],
            )
        }
    )

    page = render_markdown(evidence)
    summary = render_summary(evidence)

    assert "## Advisory" in page
    assert "CVE-2026-0001" in page
    assert "Advisory CVE-2026-0001 (high) affects `demo-pkg` 1.2.0; fixed in 1.4.2." in summary
    assert (
        evidence.bind().proof_sha256
        != evidence.model_copy(update={"advisory": None}).bind().proof_sha256
    )


def test_an_old_proof_keeps_its_hash_without_an_advisory(tmp_path: Path) -> None:
    from tests.unit.domain.test_evidence import fixed_evidence

    evidence = fixed_evidence()
    original = evidence.bind().proof_sha256
    raw = json.loads(evidence.model_dump_json())
    raw.pop("advisory")
    old = Evidence.model_validate(raw)
    assert old.bind().proof_sha256 == original


def test_write_evidence_keeps_the_advisory(tmp_path: Path) -> None:
    from tests.unit.domain.test_evidence import fixed_evidence

    evidence = fixed_evidence().model_copy(
        update={
            "advisory": AdvisoryRef(
                id="CVE-2026-0001", package="demo-pkg", version="1.2.0", severity="high"
            )
        }
    )
    json_path, _ = write_evidence(tmp_path, evidence)
    stored = Evidence.model_validate_json(json_path.read_text(encoding="utf-8"))

    assert stored.advisory is not None
    assert stored.advisory.id == "CVE-2026-0001"


def test_osv_fetch_parses_a_batch(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"results": [{"vulns": [OSV]}]}).encode("utf-8")

    monkeypatch.setattr(feed.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    advisories = fetch_osv([("demo-pkg", "1.2.0", "PyPI")])

    assert len(advisories) == 1
    assert advisories[0].id == "CVE-2026-0001"


def test_a_cli_scan_reports_and_creates(paths, tmp_path: Path) -> None:
    from tests.unit.interfaces.cli.test_cli import invoke, payload

    repo = _repo(tmp_path)
    _requirements(repo)
    feed_path = tmp_path / "feed.json"
    feed_path.write_text(json.dumps(OSV), encoding="utf-8")

    result = invoke(paths, "cve", "scan", "--repo", str(repo), "--feed", str(feed_path), "--json")

    assert result.exit_code == 0, result.stderr
    body = payload(result)
    assert body["files"] == ["requirements.txt"]
    assert body["hits"][0]["id"] == "CVE-2026-0001"
    assert len(body["created"]) == 1
