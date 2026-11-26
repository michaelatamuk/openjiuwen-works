import { useMemo, useState } from "react";

import { fmtMs, fmtUsd, shortSha } from "../../lib/format.js";
import { Card, EmptyProof, Pill } from "../../ui/primitives";
import { SummaryText } from "../../ui/summary";
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
} from "./sections";

export type EvidenceStage = {
  id: string;
  label?: string;
  state?: string;
  at?: string;
};

export type EvidenceOutcome = {
  id?: string;
  priority?: string;
  passed?: boolean;
  exit_code?: number | null;
  duration_ms?: number;
};

export type EvidenceVerdict = {
  allow?: boolean;
  reason?: string;
  outcomes?: EvidenceOutcome[];
};

export type EvidenceFinding = {
  severity?: string;
  title?: string;
  detail?: string;
};

export type EvidenceChallenge = {
  allow?: boolean;
  reason?: string;
  concerns?: string[];
};

export type EvidenceCommandResult = {
  step?: string;
  argv?: string[];
  exit_code?: number | null;
  duration_ms?: number;
};

export type EvidenceDiffFile = {
  path: string;
  added?: number;
  removed?: number;
};

export type EvidenceViolation = {
  path: string;
  reason?: string;
};

export type EvidenceDecision = {
  verb?: string;
  action?: string;
  reason_code?: string | null;
  confidence?: number | null;
  source?: string | null;
};

const ENGINE_LABELS: Record<string, string> = {
  native: "Jiuwen native",
  dsh: "DeepSeek Harness",
  codex: "OpenAI Codex",
  claudecode: "Claude Code",
  fake: "Recorded trace (fake)",
};

function engineLabel(value?: string | null): string {
  if (!value) return "-";
  return ENGINE_LABELS[value] || value;
}

export type EvidencePayload = {
  model?: string | null;
  provider?: string | null;
  harness?: string | null;
  proof_sha256?: string | null;
  policy?: { ok?: boolean; violations?: EvidenceViolation[] } | null;
  advisory?: {
    id?: string;
    package?: string;
    version?: string;
    severity?: string;
    fixed?: string | null;
    cvss?: number | null;
    links?: string[];
  } | null;
  risk?: {
    level?: string;
    reasons?: string[];
    files?: number;
    lines?: number;
    max_file_churn?: number;
    heavy_files?: number;
    security_paths?: string[];
  } | null;
  decision?: EvidenceDecision | null;
  not_tested?: string[];
  memory_recall?: unknown[];
  findings?: EvidenceFinding[];
  challenge?: EvidenceChallenge | null;
  specialists?: { area?: string; allow?: boolean; reason?: string; concerns?: string[] }[];
  verdict?: EvidenceVerdict | null;
  baseline_exit?: number | null;
  baseline_output_sha256?: string | null;
  reproduce?: EvidenceCommandResult | null;
  reproduction_command?: string[];
  reproduction_source?: string | null;
  reproduction_attempts?: number;
  reproduction_stable?: boolean;
  reproduction_env?: Record<string, string>;
  reproduction_hint?: string | null;
  test?: EvidenceCommandResult | null;
  preview?: EvidenceCommandResult | null;
  diff?: string | null;
  diff_stat?: EvidenceDiffFile[];
};

export type EvidenceRun = {
  run_id?: string;
  flow?: string;
  base_commit?: string | null;
  checks_sha?: string | null;
  duration_ms?: number;
  tokens?: number | null;
  usd?: number | null;
};

export type EvidenceTimelineEvent = {
  seq?: number;
  ts?: string;
  type: string;
  data?: Record<string, unknown>;
};

export type EvidenceArtifact = {
  kind?: string;
  name?: string;
  path?: string;
  sha256?: string;
  size?: number;
  url: string;
};

export type EvidenceFeatureItem = {
  id?: string | null;
  name?: string | null;
  passed?: boolean;
  covered?: boolean;
  scenarios?: string[];
};

export type EvidenceFeatures = {
  available?: boolean;
  covered?: number;
  total?: number;
  uncovered?: number;
  note?: string;
  files?: string[];
  features?: EvidenceFeatureItem[];
};

export type EvidenceReadiness = {
  available?: boolean;
  status?: string;
  passed?: number;
  total?: number;
  failed?: number;
  note?: string;
  checks?: unknown[];
  import_edges?: Record<string, string[]>;
  import_cycles?: string[][];
  features?: unknown[];
};

export type EvidenceTeamReview = {
  verdict?: string | null;
  team?: string | null;
  blockers?: string[];
};

export type EvidenceTask = {
  id: string;
  flow?: string;
  state?: string;
  product?: string;
};

export type EvidenceDetail = {
  task: EvidenceTask;
  pipeline?: { technical?: EvidenceStage[] } | null;
  evidence?: EvidencePayload | null;
  proof_summary?: { text?: string; sha256?: string; derived?: boolean } | null;
  run?: EvidenceRun | null;
  release?: { released?: boolean; ready?: boolean; blockers?: string[] } | null;
  delivery?: unknown;
  confirmation?: unknown;
  readiness?: EvidenceReadiness | null;
  features?: EvidenceFeatures | null;
  artifacts?: EvidenceArtifact[] | null;
  timeline?: EvidenceTimelineEvent[] | null;
  summary?: { risk?: string | null } | null;
  verifier?: { name?: string; isolation?: string } | null;
  team?: { latest?: EvidenceTeamReview | null; history?: unknown[] } | null;
};

export type EvidenceProps = {
  detail: EvidenceDetail;
  onShowRun: () => void;
  onAction: (action: string, body?: Record<string, unknown>) => unknown;
  onLightbox: (url: string, alt?: string) => void;
  onOpenEvent: (event: EvidenceTimelineEvent) => void;
  onToast: (message: string) => void;
};

type ExportLink = [label: string, kind: string];

function ReproductionCard({
  evidence,
  onAction,
}: {
  evidence?: EvidencePayload | null;
  onAction: (action: string, body?: Record<string, unknown>) => unknown;
}) {
  const [command, setCommand] = useState("");
  const current = evidence?.reproduction_command || [];
  return (
    <Card
      title="How to reproduce"
      actions={
        <Pill tone={evidence?.reproduction_stable === false ? "amber" : "green"}>
          {evidence?.reproduction_source || "not recorded"}
        </Pill>
      }
    >
      <dl className="kv">
        <dt>Command</dt>
        <dd className="mono">{current.length ? current.join(" ") : "?"}</dd>
        <dt>Attempts</dt>
        <dd>{evidence?.reproduction_attempts ?? 1}</dd>
        <dt>Stable</dt>
        <dd>{evidence?.reproduction_stable === false ? "no ? rerun changed the result" : "yes"}</dd>
        <dt>Reporter hint</dt>
        <dd>{evidence?.reproduction_hint || "?"}</dd>
        <dt>Environment</dt>
        <dd className="mono">
          {evidence?.reproduction_env
            ? Object.entries(evidence.reproduction_env).map(([key, value]) => `${key}=${value}`).join(", ")
            : "?"}
        </dd>
      </dl>
      <div className="export-row">
        <input
          aria-label="Reproduction command"
          placeholder={current.join(" ") || "python -m pytest -q"}
          value={command}
          onChange={(event) => setCommand(event.target.value)}
        />
        <button
          className="btn"
          type="button"
          disabled={!command.trim()}
          onClick={() => onAction("set-reproduction", { command })}
        >
          Save command
        </button>
      </div>
    </Card>
  );
}

export function Evidence({ detail, onShowRun, onAction, onLightbox, onOpenEvent }: EvidenceProps) {
  const evidence = detail.evidence;
  const task = detail.task;
  const stages = detail.pipeline?.technical || [];
  const summary = detail.proof_summary;
  const [mode, setMode] = useState<"summary" | "technical">("technical");
  const exports = useMemo<ExportLink[]>(() => {
    const links: ExportLink[] = [
      ["proof.md", "evidence.md"],
      ["evidence.json", "evidence.json"],
      ["run.json", "run.json"],
    ];
    if (detail.release?.released) links.push(["release.json", "release.json"]);
    if (detail.delivery) links.push(["delivery.json", "delivery.json"]);
    if (detail.confirmation) links.push(["confirmation.json", "confirmation.json"]);
    return links;
  }, [detail]);

  if (!evidence && !detail.run) return <EmptyProof />;

  const showSummary = Boolean(summary?.text);
  const verdictOk = evidence?.verdict?.allow;

  return (
    <>
      {showSummary ? (
        <div className="proof-head">
          <div className="segmented" role="tablist" aria-label="Proof view">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "summary"}
              onClick={() => setMode("summary")}
            >
              Summary
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "technical"}
              onClick={() => setMode("technical")}
            >
              Technical
            </button>
          </div>
          <span className="muted small">
            {summary?.derived
              ? "derived from the record"
              : `bound · ${shortSha(summary?.sha256)}`}
          </span>
        </div>
      ) : null}
      {showSummary && mode === "summary" ? (
        <div className="grid">
          <div className="stack">
            <Card
              title="Plain-language summary"
              actions={
                <Pill tone={summary?.derived ? "amber" : "green"}>
                  {summary?.derived ? "derived" : "bound"}
                </Pill>
              }
            >
              <SummaryText text={summary?.text} />
              <div className="summary-facts">
                <Pill tone={detail.summary?.risk === "low" ? "green" : detail.summary?.risk === "medium" ? "amber" : "red"}>
                  risk {detail.summary?.risk || "—"}
                </Pill>
                <Pill tone={verdictOk === false ? "red" : "green"}>
                  verdict {verdictOk === false ? "block" : evidence?.verdict ? "allow" : "not recorded"}
                </Pill>
                <span className="muted small">
                  {evidence?.diff_stat?.length || 0} file(s) changed
                </span>
                <span className="mono small">{shortSha(evidence?.proof_sha256)}</span>
              </div>
            </Card>
          </div>
        </div>
      ) : (
    <div className="grid">
      <div className="stack">
        <Pipeline stages={stages} />
        <Card
          title="Run metadata"
          actions={
            <>
              <button type="button" className="btn ghost" onClick={onShowRun}>
                Open run
              </button>
              {task.state === "released" ? (
                <button type="button" className="btn ghost" onClick={() => onAction("confirm")}>
                  Re-check
                </button>
              ) : null}
            </>
          }
        >
          <dl className="kv">
            <dt>Run</dt><dd className="mono">{detail.run?.run_id || "—"}</dd>
            <dt>Flow</dt><dd>{detail.run?.flow || task.flow}</dd>
            <dt>Model</dt><dd>{evidence?.model || "—"}</dd>
            <dt>Provider</dt><dd>{evidence?.provider || "—"}</dd>
            <dt>Engine</dt><dd>{engineLabel(evidence?.harness)}</dd>
            <dt>Base commit</dt><dd className="mono">{shortSha(detail.run?.base_commit)}</dd>
            <dt>Checks SHA</dt><dd className="mono">{shortSha(detail.run?.checks_sha)}</dd>
            <dt>Proof SHA-256</dt><dd className="mono">{shortSha(evidence?.proof_sha256)}</dd>
            <dt>Wall</dt><dd>{fmtMs(detail.run?.duration_ms)}</dd>
            {evidence?.baseline_exit !== null && evidence?.baseline_exit !== undefined ? (
              <>
                <dt>Base check</dt>
                <dd>
                  exit {evidence.baseline_exit} ? {shortSha(evidence.baseline_output_sha256)}
                </dd>
              </>
            ) : null}
            <dt>Tokens</dt><dd>{detail.run?.tokens ?? 0}</dd>
            <dt>USD</dt><dd>{fmtUsd(detail.run?.usd)}</dd>
          </dl>
          <div className="export-row">
            {exports.map(([label, kind]) => (
              <a key={kind} className="btn ghost" href={`/api/v1/tasks/${encodeURIComponent(task.id)}/export/${kind}`} download>{label}</a>
            ))}
          </div>
        </Card>
        <VerdictCard evidence={evidence} />
        <Findings findings={evidence?.findings} />
        <ChallengeCard challenge={evidence?.challenge} />
        {evidence?.specialists?.length ? (
          <Card
            title="Specialist reviews"
            actions={<Pill>{evidence.specialists.length}</Pill>}
          >
            <ul className="bullets">
              {evidence.specialists.map((item) => (
                <li key={item.area}>
                  <Pill tone={item.allow === false ? "red" : "green"}>
                    {item.area}
                  </Pill>{" "}
                  {item.reason || (item.allow === false ? "blocked" : "allowed")}
                </li>
              ))}
            </ul>
          </Card>
        ) : null}
        <Commands evidence={evidence} />
        <ReproductionCard evidence={evidence} onAction={onAction} />
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
        {evidence?.advisory ? (
          <Card
            title="Advisory"
            actions={
              <Pill tone={evidence.advisory.severity === "critical" || evidence.advisory.severity === "high" ? "red" : evidence.advisory.severity === "low" ? "green" : "amber"}>
                {evidence.advisory.severity || "unknown"}
              </Pill>
            }
          >
            <dl className="kv">
              <dt>Id</dt><dd className="mono">{evidence.advisory.id || "?"}</dd>
              <dt>Package</dt><dd>{evidence.advisory.package || "?"} {evidence.advisory.version || ""}</dd>
              <dt>Fixed in</dt><dd>{evidence.advisory.fixed || "not recorded"}</dd>
              {typeof evidence.advisory.cvss === "number" ? (<><dt>CVSS</dt><dd>{evidence.advisory.cvss}</dd></>) : null}
            </dl>
            {evidence.advisory.links?.length ? (
              <p className="small"><a href={evidence.advisory.links[0]} target="_blank" rel="noopener noreferrer">advisory</a></p>
            ) : null}
          </Card>
        ) : null}
        <Card title="Risk" actions={<Pill tone={detail.summary?.risk === "low" ? "green" : detail.summary?.risk === "medium" ? "amber" : "red"}>{detail.summary?.risk || "—"}</Pill>}>
          <ul className="bullets">{(evidence?.risk?.reasons || []).map((item) => <li key={item}>{item}</li>)}</ul>
          {evidence?.risk ? (
            <p className="muted small">
              {evidence.risk.files || 0} file(s) · {evidence.risk.lines || 0} line(s) · largest file {evidence.risk.max_file_churn || 0}
              {evidence.risk.heavy_files ? ` · ${evidence.risk.heavy_files} heavy file(s)` : ""}
            </p>
          ) : null}
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
        <Card title="Residual risk" actions={null}>
          <ul className="bullets">
            {evidence?.not_tested?.length
              ? evidence.not_tested.map((item) => <li key={item}>Not tested: {item}</li>)
              : <li>No untested area recorded.</li>}
          </ul>
        </Card>
        <Card title="Cost" actions={null}>
          <dl className="kv">
            <dt>Tokens</dt><dd>{detail.run?.tokens ?? 0}</dd>
            <dt>USD</dt><dd>{fmtUsd(detail.run?.usd)}</dd>
            <dt>Memory</dt><dd>{evidence?.memory_recall?.length ? `${evidence.memory_recall.length} recalled` : "Not recorded"}</dd>
          </dl>
        </Card>
        <Card title="Verifier" actions={null}>
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
      )}
    </>
  );
}
