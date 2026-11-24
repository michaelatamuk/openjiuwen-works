"""Write routes: each one validates the body, runs the action and returns a payload."""

from __future__ import annotations

import threading
from http import HTTPStatus
from pathlib import Path
from typing import Any

from works.adapters.queue.store import Queue
from works.application.intake.detectors import ingest_named
from works.application.intake.products import resolve_repo
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.domain.records import Source, SourceKind, TaskKind

Result = tuple[HTTPStatus, dict[str, Any]]


def create_task(paths: WorksPaths, payload: dict[str, Any], lock: threading.Lock) -> Result:
    repo_raw = str(payload.get("repo") or "").strip()
    ref = str(payload.get("ref") or "").strip()
    title = str(payload.get("title") or "").strip()
    product = str(payload.get("product") or "openjiuwen").strip()
    flow = str(payload.get("flow") or "fix-issue").strip()
    if not product:
        raise ValueError("product is required")
    if repo_raw:
        repo = Path(repo_raw).expanduser()
        repo = (Path.cwd() / repo).resolve() if not repo.is_absolute() else repo.resolve()
    else:
        try:
            repo = resolve_repo(paths, product)
        except ConfigError as exc:
            raise ValueError(str(exc)) from exc
    if not repo.is_dir():
        raise ValueError(f"repository does not exist: {repo}")
    if not (repo / ".git").exists():
        raise ValueError(f"not a git repository: {repo}")
    if not ref or not title:
        raise ValueError("reference and title are required")
    if len(ref) > 120 or len(title) > 240:
        raise ValueError("reference or title is too long")
    try:
        source_kind = SourceKind(str(payload.get("kind") or "manual"))
    except ValueError as exc:
        raise ValueError("kind must be manual, tracker or detector") from exc
    try:
        task_kind = TaskKind(str(payload.get("task_kind") or "fix"))
    except ValueError as exc:
        raise ValueError("task_kind must be fix or check-change") from exc
    queue = Queue(paths)
    with lock:
        task, created = queue.submit(
            source=Source(kind=source_kind, ref=ref, title=title),
            flow=flow,
            product=product,
            repo=str(repo),
            task_kind=task_kind,
        )
    return (
        HTTPStatus.CREATED if created else HTTPStatus.OK,
        {
            "ok": True,
            "created": created,
            "task": task.model_dump(mode="json"),
            "repo": str(repo),
            "url": f"#/task/{task.id}/story",
        },
    )


def run_action(paths: WorksPaths, payload: dict[str, Any], lock: threading.Lock) -> Result:
    action = str(payload.get("action") or "").strip()
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("task_id is required")
    queue = Queue(paths)
    queue.load(task_id)
    with lock:
        if action == "add-context":
            message = str(payload.get("message") or "").strip()
            if not message:
                raise ValueError("message is required")
            if len(message) > 2000:
                raise ValueError("message is too long")
            event = queue.append(
                task_id,
                "thread.note",
                {"message": message, "by": "person"},
            )
            return (
                HTTPStatus.OK,
                {
                    "ok": True,
                    "action": action,
                    "event": event.model_dump(mode="json"),
                },
            )
        if action == "ask":
            from works.application.assistant.chat import ask_mira

            question = str(payload.get("question") or "").strip()
            answer = ask_mira(paths, task_id, question)
            return HTTPStatus.OK, {"ok": True, "action": action, "answer": answer}
        if action == "commentary":
            from works.application.assistant.chat import generate_commentary

            messages = generate_commentary(paths, task_id)
            return HTTPStatus.OK, {"ok": True, "action": action, "messages": messages}
        if action == "discussion":
            from works.application.assistant.chat import generate_discussion

            messages = generate_discussion(paths, task_id)
            return HTTPStatus.OK, {"ok": True, "action": action, "messages": messages}
        if action == "approve-plan":
            from works.application.approvals.gates import approve_plan

            task, event = approve_plan(paths, task_id, by="ui")
            return (
                HTTPStatus.OK,
                {
                    "ok": True,
                    "action": action,
                    "task": task.model_dump(mode="json"),
                    "event": event.model_dump(mode="json"),
                },
            )
        if action == "release":
            from works.application.delivery.release import approve_release

            task, packet, created = approve_release(paths, task_id)
            return (
                HTTPStatus.OK,
                {
                    "ok": True,
                    "action": action,
                    "created": created,
                    "task": task.model_dump(mode="json"),
                    "release": packet.as_dict(),
                },
            )
        if action == "deliver":
            from works.application.delivery.deliver import deliver

            delivery = deliver(
                paths,
                task_id,
                provider=str(payload.get("provider") or "none"),
                tracker=payload.get("tracker") or None,
                dry_run=bool(payload.get("dry_run")),
            )
            return (
                HTTPStatus.OK,
                {"ok": True, "action": action, "delivery": delivery.as_dict()},
            )
        if action == "confirm":
            from works.application.delivery.confirm import confirm

            result = confirm(
                paths,
                task_id,
                url=str(payload.get("url") or "").strip() or None,
                command=payload.get("command"),
                tracker=payload.get("tracker") or None,
                close_issue=bool(payload.get("close")),
                force=bool(payload.get("force")),
            )
            return (
                HTTPStatus.OK,
                {"ok": result.ok, "action": action, "confirmation": result.as_dict()},
            )
        if action == "team-verify":
            from works.application.team.launcher import run_team_verify

            team_result = run_team_verify(paths, task_id)
            return (
                HTTPStatus.OK,
                {
                    "ok": team_result.get("verdict") == "allow",
                    "action": action,
                    "team": team_result,
                },
            )
    raise ValueError(f"unknown action {action!r}")


def run_readiness(payload: dict[str, Any]) -> Result:
    from works.application.execution.readiness import assess

    repo_raw = str(payload.get("repo") or "").strip()
    if not repo_raw:
        raise ValueError("repository path is required")
    repo = Path(repo_raw).expanduser()
    repo = (Path.cwd() / repo).resolve() if not repo.is_absolute() else repo.resolve()
    if not repo.is_dir():
        raise ValueError(f"repository does not exist: {repo}")
    report = assess(repo, run_commands=True)
    return HTTPStatus.OK, {"ok": report.status != "fail", **report.as_dict()}


def save_builder_settings(paths: WorksPaths, payload: dict[str, Any]) -> Result:
    from works.application.settings import builder_health
    from works.application.settings import save_builder_settings as save

    settings = save(paths, payload)
    return HTTPStatus.OK, {"ok": True, "builder": builder_health(paths, settings)}


def run_source(paths: WorksPaths, payload: dict[str, Any], lock: threading.Lock) -> Result:
    source = str(payload.get("source") or "").strip()
    product = str(payload.get("product") or "").strip()
    repo_raw = str(payload.get("repo") or "").strip()
    try:
        limit = max(1, min(50, int(payload.get("limit") or 20)))
    except (TypeError, ValueError):
        limit = 20
    if source in ("github", "jira"):
        if not product:
            raise ValueError("product is required")
        try:
            repo = (
                Path(repo_raw).expanduser().resolve() if repo_raw else resolve_repo(paths, product)
            )
        except ConfigError as exc:
            raise ValueError(str(exc)) from exc
        queue = Queue(paths)
        if source == "github":
            from works.application.intake.sources import github_issues, ingest_issues

            repository = str(payload.get("repository") or "").strip()
            if not repository:
                raise ValueError("repository is required (owner/name)")
            issues = github_issues(
                repository,
                label=str(payload.get("label") or "").strip() or None,
                limit=limit,
            )
        else:
            from works.application.intake.sources import ingest_issues, jira_issues

            url = str(payload.get("url") or "").strip()
            jql = str(payload.get("jql") or "").strip()
            if not url or not jql:
                raise ValueError("Jira needs url and jql")
            issues = jira_issues(url, jql, limit=limit)
        with lock:
            created = ingest_issues(queue, product=product, repo=str(repo), issues=issues)
        return (
            HTTPStatus.OK,
            {
                "ok": True,
                "source": source,
                "found": len(issues),
                "created": sum(1 for _, was_created in created if was_created),
                "tasks": [task.id for task, _ in created],
            },
        )
    if source == "detector":
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("detector name is required")
        with lock:
            created = ingest_named(paths, name)
        return (
            HTTPStatus.OK,
            {
                "ok": True,
                "source": source,
                "found": len(created),
                "created": sum(1 for _, was_created in created if was_created),
                "tasks": [task.id for task, _ in created],
            },
        )
    raise ValueError(f"unknown source {source!r}")
