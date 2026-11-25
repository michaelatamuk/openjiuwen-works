"""How every HTTP route is allowed to run.

The plan (M10) forbids "async-first" churn: a route is classified here,
`scripts/dump_route_classes.py` renders the table in `docs/reference/http-api.md`, and CI fails when
a new route is unclassified or a class disappears.

A blocking route stays sync and runs in the thread pool; it is not rewritten for fashion.
"""

from __future__ import annotations

from typing import Literal

RouteClass = Literal["async-safe", "blocking", "subprocess", "sse"]

# "METHOD /path" -> (class, note)
ROUTE_CLASSES: dict[str, tuple[RouteClass, str]] = {
    "POST /api/v1/actions": (
        "blocking",
        "short calls answer inline; long ones are submitted as jobs",
    ),
    "POST /api/v1/admin/pair": ("blocking", "writes the device list and the audit log"),
    "POST /api/v1/admin/rotate-token": ("blocking", "rewrites the token file and audits"),
    "POST /api/v1/admin/shutdown": ("blocking", "asks the server to stop after the response"),
    "GET /api/v1/admin/devices": ("blocking", "reads the device file"),
    "DELETE /api/v1/admin/devices/{device_id}": ("blocking", "rewrites the device list and audits"),
    "POST /api/v1/ask/stream": ("sse", "streams model tokens; a job owns the work"),
    "GET /api/v1/detectors": ("blocking", "reads the detector catalogue"),
    "POST /api/v1/dispatch": ("blocking", "selects queued tasks and submits run jobs"),
    "GET /api/v1/events": ("sse", "server-sent task events with a subscriber cap"),
    "GET /api/v1/health": ("blocking", "kept for compatibility; builder/provider diagnostics"),
    "GET /api/v1/health/live": ("async-safe", "no file or model access; cheap liveness"),
    "GET /api/v1/health/ready": ("blocking", "probes builder and provider readiness"),
    "GET /api/v1/jobs/{job_id}": ("async-safe", "reads the in-memory job record"),
    "DELETE /api/v1/jobs/{job_id}": ("async-safe", "sets the in-memory cancel flag"),
    "POST /api/v1/hooks/{source}": (
        "blocking",
        "verifies HMAC, writes the task, the audit line and the metrics",
    ),
    "GET /api/v1/inbox": ("blocking", "reads tasks and groups possible duplicates"),
    "POST /api/v1/inbox/mute": ("blocking", "rewrites the source registry"),
    "GET /api/v1/ledger": ("blocking", "reads the append-only ledger"),
    "GET /api/v1/metrics": ("blocking", "reads job and queue counters"),
    "GET /api/v1/ops/metrics": ("blocking", "reads jobs, SSE subscribers and disk counters"),
    "POST /api/v1/pair": ("blocking", "mints a device token and writes the audit log"),
    "GET /api/v1/products": ("blocking", "reads the product map"),
    "POST /api/v1/readiness": ("blocking", "submits a readiness job; the job runs the commands"),
    "POST /api/v1/runs": ("blocking", "submits a run job; the supervisor spawns subprocesses"),
    "GET /api/v1/runs/{run_id}": ("blocking", "reads the run record and evidence"),
    "POST /api/v1/session": ("async-safe", "compares a token against in-memory sessions"),
    "GET /api/v1/sources": ("blocking", "reads the source registry and its metrics"),
    "GET /api/v1/settings/builder": ("blocking", "reads the builder settings file"),
    "POST /api/v1/settings/builder": ("blocking", "writes the builder settings file"),
    "POST /api/v1/sources": ("blocking", "submits an import job; the job calls the forge API"),
    "GET /api/v1/tasks": ("async-safe", "index page ids then hydrated summaries; no full scan"),
    "POST /api/v1/tasks/{task_id}/merge": (
        "blocking",
        "records the merge event and transitions the duplicate",
    ),
    "POST /api/v1/tasks": ("blocking", "writes a task and its event"),
    "GET /api/v1/tasks/{task_id}": ("blocking", "reads events, runs and artifacts"),
    "GET /api/v1/tasks/{task_id}/artifacts/{name:path}": (
        "blocking",
        "streams a file from the run dir",
    ),
    "GET /api/v1/tasks/{task_id}/export/{kind}": ("blocking", "builds and streams an export"),
    "GET /api/v1/tasks/{task_id}/runs": ("blocking", "reads run summaries"),
}
