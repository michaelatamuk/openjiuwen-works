import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { eventSummary, fmtMs, stateLabel, stateTone, timeAgo } from "../../lib/format.js";
import { Card, Pill, Table } from "../../ui/primitives.jsx";

function headline(detail) {
  const state = detail.task.state;
  if (state === "blocked") return "Not fixed yet";
  if (state === "proved") return "Ready for release";
  if (state === "released") return `Fixed and back in ${detail.task.product}`;
  if (state === "reverted") return "Reverted";
  if (state === "queued") return "In the queue";
  if (state === "building" || state === "plan_approved") return "Fixing it now";
  if (state === "checking") return "Checking it now";
  return stateLabel(state);
}

function lede(detail) {
  const blocked = detail.pipeline?.blocked;
  if (blocked) return blocked.why;
  if (detail.task.state === "proved") {
    return `The fix is built and checked. A person needs to release it back to ${detail.task.product}.`;
  }
  if (detail.task.state === "released") return `The fix is released and the proof is ready for ${detail.task.product}.`;
  if (detail.task.state === "queued") return "The report is queued. The factory has not started yet.";
  return "The factory is working on the reported problem.";
}

function milestoneCopy(stage, display, detail) {
  const product = detail?.task?.product || "the product";
  const stops = {
    picked_up: { active: "Mira is picking it up", done: "Picked up", blocked: "Mira could not pick it up" },
    confirmed: { active: "Mira is confirming it", done: "Confirmed", blocked: "Mira could not confirm it" },
    fixed: { active: "Mira is fixing it", done: "Fixed", blocked: "Mira stopped while fixing" },
    checked: { active: "Mira is checking it", done: "Checked", blocked: "Mira stopped at a check" },
    delivered: {
      active: stage.label.startsWith("Release") ? "Mira is ready to release" : "Mira is delivering it",
      done: `Delivered to ${product}`,
      blocked: "Mira stopped before delivery",
    },
  };
  return stops[stage.id]?.[display] || stage.label;
}

const ROUTE_X0 = 160;
const ROUTE_X1 = 1040;
// A calm route: a small rise, a dip, then a gradual climb that ends higher than it started.
const ROUTE_KNOTS = [270, 242, 275, 212, 166, 175];

function routeYAt(index, count) {
  if (count === ROUTE_KNOTS.length) return ROUTE_KNOTS[index];
  if (count <= 1) return ROUTE_KNOTS[0];
  const position = (index / (count - 1)) * (ROUTE_KNOTS.length - 1);
  const low = Math.floor(position);
  const high = Math.min(ROUTE_KNOTS.length - 1, low + 1);
  const fraction = position - low;
  return ROUTE_KNOTS[low] + (ROUTE_KNOTS[high] - ROUTE_KNOTS[low]) * fraction;
}

function smoothPath(points) {
  if (!points.length) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  const parts = [`M ${points[0].x} ${points[0].y}`];
  for (let index = 0; index < points.length - 1; index += 1) {
    const p0 = points[index - 1] || points[index];
    const p1 = points[index];
    const p2 = points[index + 1];
    const p3 = points[index + 2] || p2;
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    parts.push(`C ${c1x.toFixed(2)} ${c1y.toFixed(2)} ${c2x.toFixed(2)} ${c2y.toFixed(2)} ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`);
  }
  return parts.join(" ");
}

function lengthAtX(path, x) {
  let low = 0;
  let high = path.getTotalLength();
  for (let step = 0; step < 24; step += 1) {
    const middle = (low + high) / 2;
    if (path.getPointAtLength(middle).x < x) low = middle;
    else high = middle;
  }
  return (low + high) / 2;
}

function Route({ stages, selected, onSelect, taskState, detail }) {
  const progressRef = useRef(null);
  const [points, setPoints] = useState([]);
  const activeIndex = Math.max(0, stages.findIndex((stage) =>
    ["active", "blocked"].includes(stage.state)
  ));
  const effectiveIndex = stages.some((stage) => ["active", "blocked"].includes(stage.state))
    ? activeIndex
    : Math.max(0, stages.map((stage) => stage.state).lastIndexOf("done"));
  const routePoints = stages.map((_, index) => ({
    x: ROUTE_X0 + (ROUTE_X1 - ROUTE_X0) * (index / Math.max(1, stages.length - 1)),
    y: routeYAt(index, stages.length),
  }));
  const routeD = smoothPath(routePoints);
  const baseD = smoothPath(routePoints.slice(1));
  const intakeD = routePoints.length > 1
    ? `M ${routePoints[0].x} ${routePoints[0].y} C ${routePoints[0].x + 60} ${routePoints[0].y - 45} ${routePoints[1].x - 55} ${routePoints[0].y + 18} ${routePoints[1].x} ${routePoints[1].y}`
    : "";

  useLayoutEffect(() => {
    const path = progressRef.current;
    if (!path || !stages.length) return;
    const length = path.getTotalLength();
    const next = stages.map((stage, index) => {
      const point = routePoints[index];
      return {
        stage,
        display: index === 0 ? "source" : stage.state || "pending",
        side: index % 2 === 0 ? "above" : "below",
        point,
      };
    });
    setPoints(next);
    const progress = progressRef.current;
    if (progress) {
      const stageLengths = next.map(({ point }) => lengthAtX(path, point.x));
      const start = stageLengths[1] ?? 0;
      const end = stageLengths[effectiveIndex] ?? start;
      progress.style.strokeDasharray = `${Math.max(0, end - start)} ${length}`;
      progress.style.strokeDashoffset = `${-start}`;
      progress.classList.toggle("blocked", stages[effectiveIndex]?.state === "blocked");
    }
  }, [stages, effectiveIndex]);

  const activePoint = points[effectiveIndex]?.point;
  const showMira = taskState !== "queued" && effectiveIndex > 0 && Boolean(activePoint);
  const node = (display, kind) =>
    display === "done" ? "✓" : display === "blocked" ? "!" : display === "active" ? (kind === "gate" ? "◆" : "•") : "";

  return (
    <section className="route-block" aria-label="Fix route">
      <div className="route-head">
        <span className="route-title">The fix route</span>
        <span className="route-legend">
          <span><i className="legend-dot origin" />Origin</span>
          <span><i className="legend-dot pending" />Not started</span>
          <span><i className="legend-dot active" />Mira is here</span>
          <span><i className="legend-dot waiting" />Waits for you</span>
          <span><i className="legend-dot done" />Done</span>
          <span><i className="legend-dot blocked" />Stopped</span>
        </span>
      </div>
      <div className="route-scroll">
        <div className="route-wrap">
          <svg className="route-svg" viewBox="0 0 1200 380" preserveAspectRatio="none" aria-hidden="true">
            <path className="route-base" d={baseD} />
            <path className="route-intake" d={intakeD} />
            <path ref={progressRef} className="route-progress" d={routeD} />
          </svg>
          <div className="route-points" role="list" aria-label="Fix milestones">
            {points.map(({ stage, display, side, point }, index) => {
              const copy = display === "source" ? "Reported" : milestoneCopy(stage, display, detail);
              return (
                <div
                  key={stage.id}
                  className={`milestone ${display} ${side}${stage.kind === "gate" ? " gate" : ""}${stage.id === selected ? " selected" : ""}`}
                  style={{ left: `${(point.x / 1200) * 100}%`, top: `${(point.y / 380) * 100}%` }}
                  role="listitem"
                  aria-label={`${copy}, ${display === "source" ? "origin" : display}${stage.at ? `, ${timeAgo(stage.at)}` : ""}`}
                  aria-current={display === "active" ? "step" : undefined}
                  onClick={() => onSelect(stage.id)}
                >
                  <span className="m-node" aria-hidden="true">{node(display, stage.kind)}</span>
                  <span className="m-copy">
                    <strong>{copy}</strong>
                    {stage.at && display !== "pending" ? (
                      <em>
                        {display === "source"
                          ? `from ${detail.task.source.ref} · ${timeAgo(stage.at)}`
                          : timeAgo(stage.at)}
                      </em>
                    ) : null}
                  </span>
                </div>
              );
            })}
          </div>
          <div
            className={`route-mira${effectiveIndex % 2 === 1 ? " above-node" : ""}${effectiveIndex === stages.length - 1 ? " finish" : ""}`}
            style={activePoint ? { left: `${(activePoint.x / 1200) * 100}%`, top: `${(activePoint.y / 380) * 100}%` } : { display: "none" }}
            hidden={!showMira}
            aria-hidden="true"
          >
            <img src="/mira.svg" alt="" width="52" height="52" />
          </div>
        </div>
      </div>
    </section>
  );
}

function Receipt({ detail }) {
  const evidence = detail.evidence;
  const blocked = detail.task.state === "blocked";
  const files = evidence?.files_changed?.length || 0;
  const changed = blocked ? "No change released" : files ? `${files} file${files === 1 ? "" : "s"} changed` : "No change yet";
  const outcomes = evidence?.verdict?.outcomes || [];
  const must = outcomes.filter((item) => item.priority === "P0");
  const passed = must.filter((item) => item.passed).length;
  const checked = must.length
    ? passed === must.length
      ? `${passed} of ${must.length} must-pass checks passed`
      : `${must.length - passed} of ${must.length} must-pass checks failed`
    : "No checks yet";
  const note = !evidence?.verdict
    ? "No checks yet"
    : evidence.verdict.allow
      ? evidence.challenge?.allow ? "Independent review passed" : "No independent review"
      : "A must-pass check failed";
  return (
    <div className="receipt">
      <div><span>Changed</span><strong>{changed}</strong><p>{files ? (evidence.files_changed || []).join(", ") : "No diff yet."}</p></div>
      <div><span>Checked</span><strong>{checked}</strong><p>{note}</p></div>
      <div><span>Not checked</span><strong>{evidence?.not_tested?.[0] || "No gaps recorded"}</strong><p>The proof says what was not covered.</p></div>
      <div><span>Decides</span><strong>A person</strong><p>Human gates stay human.</p></div>
    </div>
  );
}

export function Story({ detail, onView, onToast, onShowRun }) {
  const stages = detail.pipeline?.story || [];
  const [selected, setSelected] = useState(stages.find((stage) => stage.state === "active")?.id || "");
  const [at, setAtState] = useState(() => {
    const match = location.hash.match(/[?&]at=(\d+)/);
    return match ? Number(match[1]) : null;
  });
  const [present, setPresent] = useState(false);
  const replay = detail.pipeline?.replay || [];
  const scene = at == null ? null : replay[Math.min(at, replay.length - 1)];

  function updateAt(value) {
    setAtState(value);
    const suffix = value == null ? "" : `?at=${value}`;
    history.replaceState(null, "", `#/task/${encodeURIComponent(detail.task.id)}/story${suffix}`);
  }

  useEffect(() => {
    function onKey(event) {
      const inField = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
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
              <span><strong>{detail.task.product}</strong></span>
              <span>Reported <strong>{timeAgo(detail.task.created_at)}</strong></span>
              <span className={`memory-${memory.tone}`}>Memory <strong>{memory.label}</strong></span>
              {detail.summary?.risk && detail.summary.risk !== "low" ? (
                <span>Risk <strong>{detail.summary.risk}</strong></span>
              ) : null}
            </div>
            <div className="hero-actions">
              <button type="button" className="btn" onClick={() => onView("evidence")}>Open evidence</button>
              <button type="button" className="btn ghost" onClick={() => setPresent(true)}>Present</button>
              <button type="button" className="btn ghost" onClick={() => onToast("Link copied.")}>Copy link</button>
            </div>
          </div>
          <img className="story-mira" src="/mira.svg" alt="Mira, the courier" width="140" height="140" />
        </section>

        <Route stages={stages} selected={selected} onSelect={setSelected} taskState={detail.task.state} detail={detail} />
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
            <summary>How we got here · {replay.length} step{replay.length === 1 ? "" : "s"}</summary>
            <div className="replay-body">
              <Card title="Steps" actions={`${replay.length} steps`}>
                <div className="replay-row">
                  <button type="button" className="btn ghost" onClick={() => updateAt(Math.max(0, (at ?? replay.length - 1) - 1))} aria-label="Previous event">←</button>
                  <button type="button" className="btn" onClick={() => updateAt(null)}>Live</button>
                  <button type="button" className="btn ghost" onClick={() => updateAt(Math.min(replay.length - 1, (at ?? replay.length - 1) + 1))} aria-label="Next event">→</button>
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
                  <span className="faint"> · {(at ?? replay.length - 1) + 1} / {replay.length}</span>
                </p>
              </Card>
            </div>
          </details>
        ) : null}
      </div>

      <aside className="story-rail">
        <div className="rail-title">{detail.task.state === "proved" ? "What happens next" : "Where it stands"}</div>
        {detail.task.state === "proved" ? (
          <>
            <p className="rail-kicker">Ready for a person</p>
            <p className="rail-big">Release to {detail.task.product}</p>
            <p>The fix is built and checked. A person needs to release it back to {detail.task.product}.</p>
            <dl className="rail-facts"><dt>Next step</dt><dd>Release to {detail.task.product}</dd></dl>
          </>
        ) : (
          <>
            <p className="rail-kicker">{stateLabel(detail.task.state)}</p>
            <p className="rail-big">{headline(detail)}</p>
            <p>{lede(detail)}</p>
            {detail.run ? (
              <dl className="rail-facts">
                <dt>Run</dt><dd className="mono">{detail.run.run_id}</dd>
                <dt>Wall</dt><dd>{fmtMs(detail.run.duration_ms)}</dd>
              </dl>
            ) : null}
          </>
        )}
        <div className="rail-actions">
          <button type="button" className="btn ghost" onClick={() => onView("evidence")}>Open evidence</button>
          <button type="button" className="btn ghost" onClick={onShowRun} disabled={!detail.run}>Open run</button>
        </div>
      </aside>
      {present ? (
        <div className="present-mode" role="dialog" aria-modal="true" aria-label="Present mode">
          <div className="present-card">
            <div className="eyebrow">{detail.task.product} · {stateLabel(detail.task.state)}</div>
            <h1>{headline(detail)}</h1>
            <p className="present-lede">{lede(detail)}</p>
            <Receipt detail={detail} />
            <div className="present-actions">
              <button type="button" className="btn" onClick={() => setPresent(false)}>Exit · Esc</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
