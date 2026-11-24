import { useEffect, useState } from "react";

import { eventSummary, fmtMs, stateLabel, timeAgo } from "../../lib/format.js";
import { Card } from "../../ui/primitives";
import { Receipt } from "./Receipt";
import { Route } from "./Route";
import { headline, lede } from "./copy.js";

export type StoryStage = {
  id: string;
  label: string;
  state?: string;
  kind?: string;
  at?: string;
};

export type StoryOutcome = {
  priority?: string;
  passed?: boolean;
};

export type StoryEvidence = {
  files_changed?: string[];
  verdict?: {
    allow?: boolean;
    outcomes?: StoryOutcome[];
  } | null;
  challenge?: { allow?: boolean } | null;
  not_tested?: string[];
};

export type StoryEvent = {
  type: string;
  seq?: number;
  at?: string;
  data?: Record<string, unknown>;
};

export type StoryDetail = {
  task: {
    id: string;
    product: string;
    state: string;
    created_at?: string;
    source?: { ref?: string };
  };
  pipeline?: {
    story?: StoryStage[];
    replay?: StoryEvent[];
    blocked?: { why: string; next: string };
  };
  timeline?: { type: string }[];
  summary?: { risk?: string | null };
  run?: { run_id: string; duration_ms: number };
  evidence?: StoryEvidence | null;
};

export type StoryProps = {
  detail: StoryDetail;
  onView: (view: string) => void;
  onToast: (message: string) => void;
  onShowRun: () => void;
};

export function Story({ detail, onView, onToast, onShowRun }: StoryProps) {
  const stages = detail.pipeline?.story || [];
  const [selected, setSelected] = useState(
    stages.find((stage) => stage.state === "active")?.id || "",
  );
  const [at, setAtState] = useState<number | null>(() => {
    const match = location.hash.match(/[?&]at=(\d+)/);
    return match ? Number(match[1]) : null;
  });
  const [present, setPresent] = useState(false);
  const replay = detail.pipeline?.replay || [];
  const scene = at == null ? null : replay[Math.min(at, replay.length - 1)];

  function updateAt(value: number | null) {
    setAtState(value);
    const suffix = value == null ? "" : `?at=${value}`;
    history.replaceState(
      null,
      "",
      `#/task/${encodeURIComponent(detail.task.id)}/story${suffix}`,
    );
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const inField = ["INPUT", "TEXTAREA", "SELECT"].includes(
        document.activeElement?.tagName || "",
      );
      if (event.key === "Escape") setPresent(false);
      if (!inField && !document.querySelector("dialog[open]") && event.key.toLowerCase() === "c") {
        setPresent((current) => !current);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const memory = (detail.timeline || []).some((event) => event.type === "memory.reported")
    ? { label: "PPMA synced", tone: "ok" }
    : (detail.timeline || []).some((event) => event.type === "memory.failed")
      ? { label: "PPMA failed", tone: "bad" }
      : { label: "Not recorded", tone: "" };

  return (
    <div className="story-body">
      <div className="story-left">
        <section className="story-main">
          <div className="story-hero-copy">
            <div className="eyebrow">{detail.task.product} · report</div>
            <h2 className="story-answer">{headline(detail)}</h2>
            <p className="story-lede">{lede(detail)}</p>
            <div className="story-meta">
              <span>
                <strong>{detail.task.product}</strong>
              </span>
              <span>
                Reported <strong>{timeAgo(detail.task.created_at)}</strong>
              </span>
              <span className={`memory-${memory.tone}`}>
                Memory <strong>{memory.label}</strong>
              </span>
              {detail.summary?.risk && detail.summary.risk !== "low" ? (
                <span>
                  Risk <strong>{detail.summary.risk}</strong>
                </span>
              ) : null}
            </div>
            <div className="hero-actions">
              <button type="button" className="btn" onClick={() => onView("evidence")}>
                Open evidence
              </button>
              <button type="button" className="btn ghost" onClick={() => setPresent(true)}>
                Present
              </button>
              <button type="button" className="btn ghost" onClick={() => onToast("Link copied.")}>
                Copy link
              </button>
            </div>
          </div>
          <img
            className="story-mira"
            src="/mira.svg"
            alt="Mira, the courier"
            width="140"
            height="140"
          />
        </section>

        <Route
          stages={stages}
          selected={selected}
          onSelect={setSelected}
          taskState={detail.task.state}
          detail={detail}
        />
        <Receipt detail={detail} />

        {detail.pipeline?.blocked ? (
          <div className="blocked-callout">
            <div>
              <strong>Why it stopped</strong>
              <p>{detail.pipeline.blocked.why}</p>
              <p className="small muted">{detail.pipeline.blocked.next}</p>
            </div>
          </div>
        ) : null}

        {replay.length ? (
          <details className="replay-details">
            <summary>
              How we got here · {replay.length} step{replay.length === 1 ? "" : "s"}
            </summary>
            <div className="replay-body">
              <Card title="Steps" actions={`${replay.length} steps`}>
                <div className="replay-row">
                  <button
                    type="button"
                    className="btn ghost"
                    onClick={() => updateAt(Math.max(0, (at ?? replay.length - 1) - 1))}
                    aria-label="Previous event"
                  >
                    ←
                  </button>
                  <button type="button" className="btn" onClick={() => updateAt(null)}>
                    Live
                  </button>
                  <button
                    type="button"
                    className="btn ghost"
                    onClick={() =>
                      updateAt(Math.min(replay.length - 1, (at ?? replay.length - 1) + 1))
                    }
                    aria-label="Next event"
                  >
                    →
                  </button>
                  <input
                    type="range"
                    min="0"
                    max={replay.length - 1}
                    value={at ?? replay.length - 1}
                    aria-label="Replay position"
                    onChange={(event) => updateAt(Number(event.target.value))}
                  />
                </div>
                <p className="small muted" style={{ margin: "10px 0 0" }}>
                  {scene ? `${scene.type} · ${eventSummary(scene)}` : "Current position"}
                  <span className="faint">
                    {" "}
                    · {(at ?? replay.length - 1) + 1} / {replay.length}
                  </span>
                </p>
              </Card>
            </div>
          </details>
        ) : null}
      </div>

      <aside className="story-rail">
        <div className="rail-title">
          {detail.task.state === "proved" ? "What happens next" : "Where it stands"}
        </div>
        {detail.task.state === "proved" ? (
          <>
            <p className="rail-kicker">Ready for a person</p>
            <p className="rail-big">Release to {detail.task.product}</p>
            <p>
              The fix is built and checked. A person needs to release it back to{" "}
              {detail.task.product}.
            </p>
            <dl className="rail-facts">
              <dt>Next step</dt>
              <dd>Release to {detail.task.product}</dd>
            </dl>
          </>
        ) : (
          <>
            <p className="rail-kicker">{stateLabel(detail.task.state)}</p>
            <p className="rail-big">{headline(detail)}</p>
            <p>{lede(detail)}</p>
            {detail.run ? (
              <dl className="rail-facts">
                <dt>Run</dt>
                <dd className="mono">{detail.run.run_id}</dd>
                <dt>Wall</dt>
                <dd>{fmtMs(detail.run.duration_ms)}</dd>
              </dl>
            ) : null}
          </>
        )}
        <div className="rail-actions">
          <button type="button" className="btn ghost" onClick={() => onView("evidence")}>
            Open evidence
          </button>
          <button type="button" className="btn ghost" onClick={onShowRun} disabled={!detail.run}>
            Open run
          </button>
        </div>
      </aside>
      {present ? (
        <div
          className="present-mode"
          role="dialog"
          aria-modal="true"
          aria-label="Present mode"
        >
          <div className="present-card">
            <div className="eyebrow">
              {detail.task.product} · {stateLabel(detail.task.state)}
            </div>
            <h1>{headline(detail)}</h1>
            <p className="present-lede">{lede(detail)}</p>
            <Receipt detail={detail} />
            <div className="present-actions">
              <button type="button" className="btn" onClick={() => setPresent(false)}>
                Exit · Esc
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
