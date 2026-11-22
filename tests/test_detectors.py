from __future__ import annotations

import json
from pathlib import Path

import pytest

from works.detectors import (
    Alert,
    alerts_for,
    fetch_alerts,
    ingest_alerts,
    ingest_named,
    load_config,
    parse_alerts,
    read_alert_file,
)
from works.errors import ConfigError
from works.queue import Queue


def test_alertmanager_payload_keeps_only_firing_alerts() -> None:
    alerts = parse_alerts(
        {
            "alerts": [
                {
                    "status": "firing",
                    "fingerprint": "abc",
                    "labels": {"alertname": "HighErrorRate", "severity": "critical"},
                    "annotations": {"summary": "5xx above 5%"},
                },
                {
                    "status": "resolved",
                    "fingerprint": "def",
                    "labels": {"alertname": "Gone"},
                },
            ]
        }
    )

    assert [(alert.ref, alert.title, alert.severity) for alert in alerts] == [
        ("abc", "HighErrorRate: 5xx above 5%", "critical")
    ]


def test_a_generic_alert_gets_a_stable_fingerprint() -> None:
    payload = {"title": "Disk full", "severity": "warning"}

    first = parse_alerts(payload)
    second = parse_alerts(payload)

    assert first[0].ref == second[0].ref
    assert first[0].ref.startswith("alert-")
    assert first[0].title == "Disk full"
    assert first[0].severity == "warning"


def test_an_invalid_payload_is_refused() -> None:
    with pytest.raises(ConfigError, match="object or a list"):
        parse_alerts("not alerts")


def test_ndjson_and_pretty_json_files(tmp_path: Path) -> None:
    ndjson = tmp_path / "alerts.jsonl"
    ndjson.write_text(
        json.dumps({"id": "a1", "title": "One"})
        + "\n"
        + json.dumps({"id": "a2", "title": "Two"})
        + "\n",
        encoding="utf-8",
    )
    pretty = tmp_path / "alerts.json"
    pretty.write_text(json.dumps([{"id": "b1", "title": "Three"}]), encoding="utf-8")

    assert [alert.ref for alert in read_alert_file(ndjson)] == ["a1", "a2"]
    assert [alert.ref for alert in read_alert_file(pretty)] == ["b1"]


def test_a_missing_or_broken_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        read_alert_file(tmp_path / "absent.json")
    broken = tmp_path / "broken.jsonl"
    broken.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"broken\.jsonl:1"):
        read_alert_file(broken)


def test_fetch_alerts_adds_a_token_and_refuses_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, str]] = []

    def transport(url, headers):
        calls.append(headers)
        return 200, [{"id": "a1", "title": "One"}]

    monkeypatch.setenv("DETECTOR_TOKEN", "secret")
    alerts = fetch_alerts("https://alerts.example", transport=transport)

    assert alerts[0].ref == "a1"
    assert calls[0]["Authorization"] == "Bearer secret"

    with pytest.raises(ConfigError, match="refused"):
        fetch_alerts("https://alerts.example", transport=lambda url, headers: (500, {}))


def test_configured_detector_ingests_once(paths, repo) -> None:
    (paths.root / ".works").mkdir()
    alerts = paths.root / ".works" / "alerts.json"
    alerts.write_text(json.dumps([{"id": "a1", "title": "Disk full"}]), encoding="utf-8")
    (paths.root / ".works" / "detectors.yaml").write_text(
        "detectors:\n"
        "  prod:\n"
        f'    file: "{alerts.as_posix()}"\n'
        "    product: firefox\n"
        f'    repo: "{repo.path.as_posix()}"\n',
        encoding="utf-8",
    )

    config = load_config(paths)
    assert list(config.detectors) == ["prod"]
    assert alerts_for(paths, "prod")[0].title == "Disk full"

    first = ingest_named(paths, "prod")
    second = ingest_named(paths, "prod")

    assert [created for _, created in first] == [True]
    assert [created for _, created in second] == [False]
    assert first[0][0].source.kind.value == "detector"


def test_ingest_alerts_uses_the_detector_kind(paths, repo) -> None:
    created = ingest_alerts(
        Queue(paths),
        product="firefox",
        repo=str(repo.path),
        alerts=[Alert(ref="a1", title="Disk full", severity="critical")],
    )

    assert created[0][0].source.kind.value == "detector"
    assert created[0][0].source.title == "Disk full"


def test_an_unknown_named_detector_is_refused(paths) -> None:
    with pytest.raises(ConfigError, match="unknown detector"):
        ingest_named(paths, "absent")
