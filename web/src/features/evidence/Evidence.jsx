import { useMemo } from "react";
import { fmtMs, fmtUsd, shortSha } from "../../lib/format.js";
import { Card, EmptyProof, Pill } from "../../ui/primitives.jsx";
import {
  Artifacts,
  ChallengeCard,
  Change,
  Commands,
  Features,
  Findings,
  Pipeline,
  Readiness,
  Timeline,
  VerdictCard,
} from "./sections.jsx";

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
