import { useMemo, useState } from "react";
import { fmtMs, fmtUsd, stateLabel, shortSha, timeAgo, timelineLabel, eventSummary } from "../../lib/format.js";
import { Card, Pill, Table, EmptyProof } from "../../ui/primitives.jsx";

function Pipeline({ stages }) {
  return (
    <Card title={`Pipeline · ${stages.length} steps`}>
      <div className="pipeline">
        {stages.map((stage, index) => (
          <div className={`stage-row ${stage.state}`} key={stage.id}>
            <span className="stage-index">{index + 1}</span>
            <div>
              <strong>{stage.label}</strong>
              <p>{stage.state}{stage.at ? ` · ${timeAgo(stage.at)}` : ""}</p>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function VerdictCard({ evidence }) {
  const verdict = evidence?.verdict;
  if (!verdict) return <Card title="Verdict"><p className="muted small">No verdict was produced.</p></Card>;
  const rows = (verdict.outcomes || []).map((outcome) => [
    <span className="mono">{outcome.id}</span>,
    outcome.priority,
    <Pill tone={outcome.passed ? "green" : "red"}>{outcome.passed ? "PASS" : "FAIL"}</Pill>,
    outcome.exit_code,
    fmtMs(outcome.duration_ms),
  ]);
  return (
    <Card title="Verdict" actions={<Pill tone={verdict.allow ? "green" : "red"}>{verdict.allow ? "allow" : "block"}</Pill>}>
      <p className="muted small">{verdict.reason}</p>
      <Table columns={["Scenario", "Priority", "Result", "Exit", "Time"]} rows={rows} />
    </Card>
  );
}

function Findings({ findings }) {
  if (!findings?.length) return null;
  return (
    <Card title="Findings">
      <Table
        columns={["Severity", "Title", "Detail"]}
        rows={findings.map((finding) => [
          <Pill tone={finding.severity === "high" ? "red" : finding.severity === "medium" ? "amber" : "green"}>{finding.severity}</Pill>,
          finding.title,
          finding.detail,
        ])}
      />
    </Card>
  );
}

function ChallengeCard({ challenge }) {
  if (!challenge) return null;
  return (
    <Card title="Challenge" actions={<Pill tone={challenge.allow ? "green" : "red"}>{challenge.allow ? "allow" : "block"}</Pill>}>
      <p className="muted small">{challenge.reason}</p>
      {challenge.concerns?.length ? <ul className="bullets">{challenge.concerns.map((item) => <li key={item}>{item}</li>)}</ul> : null}
    </Card>
  );
}

function Commands({ evidence }) {
  const commands = [evidence?.reproduce, evidence?.test, evidence?.preview].filter(Boolean);
  if (!commands.length) return null;
  return (
    <Card title="Commands">
      <Table
        columns={["Step", "Command", "Result", "Time"]}
        rows={commands.map((command) => [
          command.step,
          <span className="mono small">{command.argv.join(" ")}</span>,
          <Pill tone={command.exit_code === 0 ? "green" : "red"}>{command.exit_code === 0 ? "PASS" : "FAIL"}</Pill>,
          fmtMs(command.duration_ms),
        ])}
      />
    </Card>
  );
}

function Change({ evidence }) {
  const rows = evidence?.diff_stat || [];
  if (!rows.length) return null;
  return (
    <Card title="Change">
      <Table
        columns={["File", "+", "−"]}
        rows={rows.map((item) => [<span className="mono">{item.path}</span>, item.added, item.removed])}
      />
      {evidence.diff ? <pre className="diff">{evidence.diff}</pre> : null}
    </Card>
  );
}

function Readiness({ readiness, onRun }) {
  if (!readiness) return null;
  const edges = Object.entries(readiness.import_edges || {}).flatMap(([from, targets]) =>
    (targets || []).map((to) => `${from} → ${to}`)
  );
  return (
    <Card title="Readiness" actions={<Pill tone={readiness.status === "pass" ? "green" : "red"}>{readiness.status}</Pill>}>
      <p className="muted small">{readiness.passed}/{readiness.total} check(s) passed{readiness.note ? ` · ${readiness.note}` : ""}</p>
      {edges.length ? (
        <details>
          <summary className="small muted">Import graph · {readiness.import_cycles?.length ?? 0} cycle(s)</summary>
          <ul className="bullets">
            {edges.slice(0, 12).map((edge) => <li key={edge} className="mono small">{edge}</li>)}
          </ul>
        </details>
      ) : null}
      <button type="button" className="btn ghost" onClick={onRun}>Run checks</button>
    </Card>
  );
}

function Features({ features }) {
  if (!features?.available || !features.features?.length) return null;
  return (
    <Card title="Feature coverage" actions={<Pill tone={features.uncovered ? "amber" : "green"}>{features.covered}/{features.total}</Pill>}>
      <Table
        columns={["Feature", "Status", "Scenarios"]}
        rows={features.features.map((feature) => [
          feature.name || feature.id,
          <Pill tone={feature.passed ? "green" : feature.covered ? "amber" : "red"}>{feature.passed ? "covered" : feature.covered ? "failed" : "uncovered"}</Pill>,
          (feature.scenarios || []).join(", ") || "—",
        ])}
      />
    </Card>
  );
}

function Artifacts({ artifacts, onLightbox }) {
  if (!artifacts?.length) return null;
  const images = artifacts.filter((item) => item.kind === "image");
  const before = images.find((item) => /before/i.test(item.name || item.path));
  const after = images.find((item) => /after/i.test(item.name || item.path));
  const [position, setPosition] = useState(50);
  return (
    <Card title="Runtime artifacts" actions={artifacts.length}>
      {before && after ? (
        <div className="cl-compare">
          <div className="cl-compare-stage" style={{ "--pos": `${position}%` }}>
            <img src={before.url} alt="before the fix" />
            <img className="after" src={after.url} alt="after the fix" />
          </div>
          <input type="range" min="0" max="100" value={position} onChange={(event) => setPosition(Number(event.target.value))} aria-label="Before and after" />
          <div className="compare-labels"><span>Before</span><span>After</span></div>
        </div>
      ) : null}
      {artifacts.map((item) => (
        <div className="artifact-row" key={item.url}>
          <div className="artifact-main"><strong>{item.kind}</strong><span className="mono small">{item.path}</span></div>
          {item.kind === "image" ? (
            <button type="button" className="artifact-thumb-btn" onClick={() => onLightbox(item.url, item.name)}>
              <img className="artifact-thumb" src={item.url} alt={item.name} loading="lazy" />
            </button>
          ) : item.kind === "video" ? (
            <video className="artifact-video" controls preload="metadata" src={item.url} />
          ) : (
            <a href={item.url} target="_blank" rel="noopener noreferrer">open</a>
          )}
          <span className="check-detail">{item.sha256 ? shortSha(item.sha256) : ""}</span>
        </div>
      ))}
    </Card>
  );
}

function Timeline({ events, onOpenEvent }) {
  const [filter, setFilter] = useState("all");
  const filters = ["all", "gates", "delivery", "confirmation", "readiness"];
  const matches = {
    gates: ["gate.decided", "approval.recorded"],
    delivery: ["delivery.finished"],
    confirmation: ["confirmation.finished"],
    readiness: ["readiness.checked"],
  };
  const visible = events.filter((event) => filter === "all" || (matches[filter] || []).includes(event.type));
  return (
    <Card
      title="Timeline"
      actions={filters.map((id) => (
        <button key={id} type="button" className={`btn ghost ${filter === id ? "active" : ""}`} onClick={() => setFilter(id)}>{id}</button>
      ))}
    >
      <ul className="timeline">
        {visible.slice().reverse().map((event) => (
          <li key={event.seq}>
            <button type="button" className="event-row" onClick={() => onOpenEvent(event)}>
              <time>{new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
              <span className="type">{timelineLabel(event.type)}</span>
              <span className="data">{eventSummary(event)}</span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function Evidence({ detail, onShowRun, onAction, onLightbox, onOpenEvent, onToast }) {
  const evidence = detail.evidence;
  const task = detail.task;
  const stages = detail.pipeline?.technical || [];
  const exports = useMemo(() => [
    ["proof.md", "evidence.md"],
    ["evidence.json", "evidence.json"],
    ["run.json", "run.json"],
    ...(detail.release?.released ? [["release.json", "release.json"]] : []),
    ...(detail.delivery ? [["delivery.json", "delivery.json"]] : []),
    ...(detail.confirmation ? [["confirmation.json", "confirmation.json"]] : []),
  ], [detail]);

  if (!evidence && !detail.run) return <EmptyProof />;

  return (
    <div className="grid">
      <div className="stack">
        <Pipeline stages={stages} />
        <Card
          title="Run metadata"
          actions={<button type="button" className="btn ghost" onClick={onShowRun}>Open run</button>}
        >
          <dl className="kv">
            <dt>Run</dt><dd className="mono">{detail.run?.run_id || "—"}</dd>
            <dt>Flow</dt><dd>{detail.run?.flow || task.flow}</dd>
            <dt>Model</dt><dd>{evidence?.model || "—"}</dd>
            <dt>Provider</dt><dd>{evidence?.provider || "—"}</dd>
            <dt>Base commit</dt><dd className="mono">{shortSha(detail.run?.base_commit)}</dd>
            <dt>Checks SHA</dt><dd className="mono">{shortSha(detail.run?.checks_sha)}</dd>
            <dt>Proof SHA-256</dt><dd className="mono">{shortSha(evidence?.proof_sha256)}</dd>
            <dt>Wall</dt><dd>{fmtMs(detail.run?.duration_ms)}</dd>
            <dt>Tokens</dt><dd>{detail.run?.tokens ?? 0}</dd>
            <dt>USD</dt><dd>{fmtUsd(detail.run?.usd)}</dd>
          </dl>
          <div className="export-row">
            {exports.map(([label, kind]) => (
              <a key={kind} className="btn ghost" href={`/api/tasks/${encodeURIComponent(task.id)}/export/${kind}`} download>{label}</a>
            ))}
          </div>
        </Card>
        <VerdictCard evidence={evidence} />
        <Findings findings={evidence?.findings} />
        <ChallengeCard challenge={evidence?.challenge} />
        <Commands evidence={evidence} />
        <Change evidence={evidence} />
        <Readiness readiness={detail.readiness} onRun={() => onAction("run-readiness")} />
        <Features features={detail.features} />
        <Artifacts artifacts={detail.artifacts} onLightbox={onLightbox} />
        <Timeline events={detail.timeline || []} onOpenEvent={onOpenEvent} />
      </div>
      <div className="stack">
        <Card title="Policy" actions={<Pill tone={evidence?.policy?.ok ? "green" : "red"}>{evidence?.policy?.ok ? "pass" : "fail"}</Pill>}>
          {evidence?.policy?.violations?.length ? (
            <ul className="bullets">{evidence.policy.violations.map((item) => <li key={item.path}>{item.path}</li>)}</ul>
          ) : <p className="muted small">No policy violations recorded.</p>}
        </Card>
        <Card title="Risk" actions={<Pill tone={detail.summary?.risk === "low" ? "green" : detail.summary?.risk === "medium" ? "amber" : "red"}>{detail.summary?.risk || "—"}</Pill>}>
          <ul className="bullets">{(evidence?.risk?.reasons || []).map((item) => <li key={item}>{item}</li>)}</ul>
        </Card>
        <Card title="Decision" actions={evidence?.decision?.verb ? <Pill>{evidence.decision.verb}</Pill> : null}>
          {evidence?.decision ? (
            <dl className="kv">
              <dt>Action</dt><dd>{evidence.decision.action}</dd>
              <dt>Reason</dt><dd>{evidence.decision.reason_code || "—"}</dd>
              <dt>Confidence</dt><dd>{Math.round((evidence.decision.confidence || 0) * 100)}%</dd>
              <dt>Source</dt><dd>{evidence.decision.source || "—"}</dd>
            </dl>
          ) : <p className="muted small">No decision recorded.</p>}
        </Card>
        <Card title="Residual risk">
          <ul className="bullets">
            {(evidence?.not_tested || []).length
              ? evidence.not_tested.map((item) => <li key={item}>Not tested: {item}</li>)
              : <li>No untested area recorded.</li>}
          </ul>
        </Card>
        <Card title="Cost">
          <dl className="kv">
            <dt>Tokens</dt><dd>{detail.run?.tokens ?? 0}</dd>
            <dt>USD</dt><dd>{fmtUsd(detail.run?.usd)}</dd>
            <dt>Memory</dt><dd>{evidence?.memory_recall?.length ? `${evidence.memory_recall.length} recalled` : "Not recorded"}</dd>
          </dl>
        </Card>
        <Card title="Verifier">
          <dl className="kv">
            <dt>Name</dt><dd>{detail.verifier?.name || "local"}</dd>
            <dt>Isolation</dt><dd>{detail.verifier?.isolation || "process"}</dd>
          </dl>
        </Card>
        <Card title="Verification team" actions={detail.team?.latest ? <Pill tone={detail.team.latest.verdict === "allow" ? "green" : "red"}>{detail.team.latest.verdict}</Pill> : null}>
          {detail.team?.latest ? (
            <p className="muted small">{(detail.team.latest.blockers || []).join(", ") || "No blockers"}</p>
          ) : <p className="muted small">Not run yet.</p>}
          <button type="button" className="btn ghost" onClick={() => onAction("team-verify")}>Verify with team</button>
        </Card>
      </div>
    </div>
  );
}
