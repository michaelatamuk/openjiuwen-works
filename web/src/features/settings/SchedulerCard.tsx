import { useEffect, useState } from "react";

import { api, waitForJob } from "../../api/client";
import type { SchedulerStatus } from "../../api/client";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function SchedulerCard({ writable }: { writable: boolean }) {
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    try {
      setStatus(await api.scheduler());
      setError("");
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }

  useEffect(() => {
    let alive = true;
    api
      .scheduler()
      .then((value) => {
        if (alive) {
          setStatus(value);
          setError("");
        }
      })
      .catch((reason) => {
        if (alive) setError(errorMessage(reason));
      });
    return () => {
      alive = false;
    };
  }, []);

  async function toggle() {
    if (!status) return;
    setBusy(true);
    try {
      if (status.paused) await api.resumeScheduler();
      else await api.pauseScheduler("settings");
      await load();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function tick() {
    setBusy(true);
    try {
      const accepted = await api.tickScheduler(1);
      await waitForJob(accepted.job.id);
      await load();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  const waiting = status ? Object.entries(status.waiting).slice(0, 6) : [];
  return (
    <section className="settings-section" aria-label="Scheduler">
      <h3>Scheduler</h3>
      {error ? (
        <p className="small" role="alert">
          {error}
        </p>
      ) : null}
      {status ? (
        <>
          <p className="small muted">
            {status.enabled ? "enabled" : "disabled"} · {status.paused ? "paused" : "running"} · tick{" "}
            {status.tick_seconds}s
            {status.limits.remaining_usd !== null
              ? ` · $${status.limits.remaining_usd.toFixed(2)} left today`
              : ""}
          </p>
          <div className="form-row">
            <button
              type="button"
              className="btn ghost"
              onClick={() => void toggle()}
              disabled={!writable || busy}
            >
              {status.paused ? "Resume" : "Pause"}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => void tick()}
              disabled={!writable || busy || !status.enabled}
            >
              Tick now
            </button>
          </div>
          {waiting.length ? (
            <ul className="bullets">
              {waiting.map(([taskId, reason]) => (
                <li key={taskId}>
                  {taskId}: {reason}
                </li>
              ))}
            </ul>
          ) : (
            <p className="small muted">Nothing is waiting.</p>
          )}
        </>
      ) : (
        <p className="small muted">Loading…</p>
      )}
    </section>
  );
}
