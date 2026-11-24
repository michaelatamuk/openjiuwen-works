"""A tiny HTTP client used by `works run --daemon` and `works dispatch --daemon`."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from works.adapters.daemon import DaemonInfo, read_token
from works.domain.errors import (
    AuthError,
    ConfigError,
    ConflictError,
    HarnessError,
    NotFoundError,
    PolicyError,
    ReadOnlyError,
    StateError,
    UnavailableError,
    WorksError,
)

ERRORS: dict[str, type[WorksError]] = {
    "config_error": ConfigError,
    "policy_error": PolicyError,
    "state_error": StateError,
    "not_found": NotFoundError,
    "conflict": ConflictError,
    "harness_error": HarnessError,
    "auth_error": AuthError,
    "read_only": ReadOnlyError,
    "unavailable": UnavailableError,
}
FINAL = frozenset({"succeeded", "failed", "cancelled"})


def error_for(code: str | None, message: str | None) -> WorksError:
    message = message or "the daemon rejected the request"
    return ERRORS.get(code or "", WorksError)(message)


class DaemonClient:
    def __init__(self, info: DaemonInfo, *, timeout: float = 30.0) -> None:
        self.info = info
        self.token = read_token(info)
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: Any = None) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, default=str).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(  # noqa: S310 - loopback
            f"{self.info.base_url}{path}", data=data, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                error = json.loads(body).get("error", {})
            except ValueError:
                error = {}
            raise error_for(error.get("code"), error.get("message") or body[:300]) from exc
        except OSError as exc:
            raise ConfigError(f"cannot reach the daemon at {self.info.base_url}: {exc}") from exc
        if not body:
            return {}
        try:
            return json.loads(body)
        except ValueError as exc:
            raise ConfigError(f"the daemon returned invalid JSON: {body[:300]}") from exc

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = self._request("POST", path, payload)
        return body if isinstance(body, dict) else {}

    def get(self, path: str) -> dict[str, Any]:
        body = self._request("GET", path)
        return body if isinstance(body, dict) else {}

    def wait(self, job_id: str, *, timeout: float | None = None) -> dict[str, Any]:
        limit = timeout or float(os.environ.get("WORKS_JOB_TIMEOUT", "3600"))
        deadline = time.monotonic() + limit
        while True:
            job = self.get(f"/api/v1/jobs/{job_id}")
            status = str(job.get("status"))
            if status in FINAL:
                if status == "failed":
                    raise error_for(job.get("error_code"), job.get("error"))
                if status == "cancelled":
                    raise StateError(f"job {job_id} was cancelled")
                return job
            if time.monotonic() > deadline:
                raise ConfigError(f"job {job_id} did not finish within {limit:.0f}s")
            time.sleep(0.5)
