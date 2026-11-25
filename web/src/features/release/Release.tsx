import { useState } from "react";

import { fmtMs, fmtUsd, shortSha, timeAgo } from "../../lib/format.js";
import { Card, Pill, Table } from "../../ui/primitives";

export type ReleaseGateDecision = {
  decision?: string | null;
  gate?: string | null;
  by?: string | null;
};

export type ReleaseGateValue = string | ReleaseGateDecision | null;

export type ReleasePacket = {
  task_id?: string;
  run_id?: string | null;
  commit?: string | null;
  proof_sha256?: string | null;
  plan_gate?: ReleaseGateValue;
  release_gate?: ReleaseGateValue;
  ready?: boolean;
  released?: boolean;
  blockers?: string[];
};

export type ReleaseDelivery = {
  commit?: string | null;
  branch?: string | null;
  pr_url?: string | null;
  comment_url?: string | null;
  dry_run?: boolean;
  provider?: string;
  tracker?: string | null;
  steps?: { step: string; status: string; detail?: string }[];
  failure?: string | null;
  completed?: boolean;
};

export type ReleaseDeploymentStatus = "deployed" | "failed" | "dry_run";

export type ReleaseDeployment = {
  status?: ReleaseDeploymentStatus | null;
  environment?: string | null;
  commit?: string | null;
  output_tail?: string | null;
};

export type ReleaseConfirmation = {
  ok?: boolean;
  target?: string | null;
  output_sha256?: string | null;
  code?: string | null;
  unstable?: boolean | null;
  deployment_status?: string | null;
  at?: string | null;
};

export type ReleaseRunSummary = {
  run_id?: string;
  base_commit?: string | null;
  verdict?: string | null;
  risk?: string | null;
  duration_ms?: number;
  usd?: number;
};

export type ReleaseRun = {
  run_id?: string;
  finished_at?: string | null;
  state?: string | null;
  base_commit?: string | null;
};

export type ReleaseEvidence = {
  proof_sha256?: string | null;
};

export type ReleaseTeamReview = {
  verdict?: string | null;
  team?: string | null;
  blockers?: string[];
};

export type LaixVerdict = string | { verb?: string | null } | null;

export type LaixComparison = {
  gate?: string;
  /** The decision.shadow event writes `agree`; the screen reads `agrees`. */
  agree?: boolean | null;
  agrees?: boolean | null;
  error?: string | null;
  shadow?: unknown;
  deterministic?: LaixVerdict;
  candidate?: LaixVerdict;
  reason_codes?: string[];
  reasons?: string[];
};

export type ReleaseDetail = {
  release?: ReleasePacket | null;
  runs?: ReleaseRunSummary[] | null;
  run?: ReleaseRun | null;
  evidence?: ReleaseEvidence | null;
  delivery?: ReleaseDelivery | null;
  deployment?: ReleaseDeployment | null;
  confirmation?: ReleaseConfirmation | null;
  confirmations?: ReleaseConfirmation[] | null;
  team?: { latest?: ReleaseTeamReview | null; history?: unknown[] } | null;
  verifier?: { name?: string; isolation?: string } | null;
  laix?: LaixComparison[] | null;
};

export type ReleaseActionBody = Record<string, unknown>;

export type ReleaseProps = {
  detail: ReleaseDetail;
  onAction: (action: string, body?: ReleaseActionBody) => unknown;
  onShowRuns: () => void;
  onShowRun: () => void;
  onToast: (message: string) => void;
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function verdictText(value: LaixVerdict | undefined): string {
  if (!value) return "—";
  if (typeof value === "string") return value;
  return value.verb || "—";
}

function gateText(value: ReleaseGateValue | undefined): string {
  if (!value) return "NOT YET";
  if (typeof value === "string") return value;
  const decision = String(value.decision || value.gate || "").toUpperCase();
  return value.by ? `${decision} · ${value.by}` : decision || "NOT YET";
}

type GateProps = {
  label: string;
  value?: ReleaseGateValue;
};

function Gate({ label, value }: GateProps) {
  const text = gateText(value);
  const ready = text.toLowerCase().includes("approved");
  return (
    <div className="gate-row">
      <span>{label}</span>
      <Pill tone={ready ? "green" : "amber"}>{text}</Pill>
    </div>
  );
}

export function Release({ detail, onAction, onShowRuns, onShowRun, onToast }: ReleaseProps) {
  const release = detail.release || {};
  const runs = detail.runs || [];
  const [provider, setProvider] = useState("none");
  const [tracker, setTracker] = useState("");
  const [dryRun, setDryRun] = useState(false);
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [comment, setComment] = useState("");

  async function deliver() {
    try {
      await onAction("deliver", { provider, tracker: tracker || null, dry_run: dryRun });
    } catch (error) {
      onToast(`Delivery failed: ${errorMessage(error)}`);
    }
  }

  async function confirm() {
    try {
      await onAction("confirm", {
        url: url.trim() || null,
        command: command.trim() ? command.trim().split(/\s+/) : null,
        close: false,
      });
    } catch (error) {
      onToast(`Confirmation failed: ${errorMessage(error)}`);
    }
  }

  return (
    <div className="grid">
      <div className="stack">
        <Card title="Release packet" actions={<Pill tone={release.ready ? "green" : "red"}>{release.released ? "RELEASED" : release.ready ? "READY" : "BLOCKED"}</Pill>}>
          <div className="release-pack">
            <Gate label="Plan gate" value={release.plan_gate} />
            <Gate label="Release gate" value={release.release_gate} />
            <Gate label="Packet" value={release.released ? "RELEASED" : release.ready ? "READY" : "BLOCKED"} />
            <div className="gate-row"><span>Commit</span><b className="mono">{shortSha(release.commit || detail.run?.base_commit)}</b></div>
            <div className="gate-row"><span>Proof SHA-256</span><b className="mono">{shortSha(release.proof_sha256 || detail.evidence?.proof_sha256)}</b></div>
          </div>
          {release.blockers?.length ? (
            <ul className="bullets">{release.blockers.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : <p className="good small">No release blockers.</p>}
          <div className="export-row">
            <input
              aria-label="Release comment"
              placeholder="Why? (required for hold or reject)"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
            <button
              type="button"
              className="btn"
              disabled={!release.ready || release.released}
              onClick={() => onAction("release", { decision: "approved", comment })}
            >
              {release.released ? "Released" : "Approve release"}
            </button>
            <button
              type="button"
              className="btn ghost"
              disabled={!release.ready || release.released || !comment.trim()}
              onClick={() => onAction("release", { decision: "changes_requested", comment })}
            >
              Hold
            </button>
            <button
              type="button"
              className="btn ghost"
              disabled={release.released || !comment.trim()}
              onClick={() => onAction("release", { decision: "rejected", comment })}
            >
              Reject
            </button>
          </div>
        </Card>

        <Card title="Delivery" actions={detail.delivery ? <Pill tone={detail.delivery.dry_run ? "amber" : "green"}>{detail.delivery.dry_run ? "dry run" : "delivered"}</Pill> : null}>
          {detail.delivery ? (
            <>
              <dl className="kv">
                <dt>Commit</dt><dd className="mono">{shortSha(detail.delivery.commit)}</dd>
                <dt>Branch</dt><dd className="mono">{detail.delivery.branch || "—"}</dd>
                <dt>Pull request</dt><dd>{detail.delivery.pr_url ? <a href={detail.delivery.pr_url} target="_blank" rel="noopener noreferrer">{detail.delivery.pr_url}</a> : "—"}</dd>
                <dt>Comment</dt><dd>{detail.delivery.comment_url ? <a href={detail.delivery.comment_url} target="_blank" rel="noopener noreferrer">open</a> : "—"}</dd>
              </dl>
              {detail.delivery.steps?.length ? (
                <ul className="bullets">
                  {detail.delivery.steps.map((step) => (
                    <li key={step.step}>
                      {step.step}: {step.status}
                      {step.detail ? ` — ${step.detail}` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <>
              <div className="form-row">
                <label>Provider
                  <select value={provider} onChange={(event) => setProvider(event.target.value)}>
                    <option value="none">None</option>
                    <option value="github">GitHub</option>
                    <option value="gitlab">GitLab</option>
                  </select>
                </label>
                <label>Tracker
                  <select value={tracker} onChange={(event) => setTracker(event.target.value)}>
                    <option value="">None</option>
                    <option value="github">GitHub</option>
                    <option value="gitlab">GitLab</option>
                    <option value="jira">Jira</option>
                  </select>
                </label>
                <label className="check-row"><input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} /> Dry run</label>
              </div>
              <button type="button" className="btn" disabled={!release.released} onClick={deliver}>Deliver</button>
            </>
          )}
        </Card>

        <Card title="Deployment" actions={detail.deployment ? <Pill tone={detail.deployment.status === "deployed" ? "green" : detail.deployment.status === "failed" ? "red" : "amber"}>{detail.deployment.status}</Pill> : null}>
          {detail.deployment ? (
            <dl className="kv">
              <dt>Environment</dt><dd>{detail.deployment.environment || "—"}</dd>
              <dt>Commit</dt><dd className="mono">{shortSha(detail.deployment.commit)}</dd>
              <dt>Status</dt><dd>{detail.deployment.status}</dd>
              {detail.deployment.output_tail ? <><dt>Output</dt><dd className="mono">{String(detail.deployment.output_tail).slice(-240)}</dd></> : null}
            </dl>
          ) : (
            <p className="muted small">No deployment recorded. Run `works deploy &lt;task-id&gt;` with the product command.</p>
          )}
        </Card>

        <Card title="Confirmation" actions={detail.confirmation ? <Pill tone={detail.confirmation.ok ? "green" : "red"}>{detail.confirmation.ok ? "pass" : "fail"}</Pill> : null}>
          {detail.confirmation ? (
            <>
              <dl className="kv">
                <dt>Target</dt><dd>{detail.confirmation.target || "—"}</dd>
                {detail.confirmation.code ? (
                  <>
                    <dt>Code</dt>
                    <dd>{detail.confirmation.code}</dd>
                  </>
                ) : null}
                {detail.confirmation.unstable ? (
                  <>
                    <dt>Stability</dt>
                    <dd>unstable — retry changed the result</dd>
                  </>
                ) : null}
                {detail.confirmation.deployment_status ? (
                  <>
                    <dt>Deployment</dt>
                    <dd>{detail.confirmation.deployment_status}</dd>
                  </>
                ) : null}
                <dt>Output</dt><dd className="mono">{shortSha(detail.confirmation.output_sha256)}</dd>
              </dl>
              {detail.confirmations?.length ? (
                <ul className="bullets">
                  {detail.confirmations.map((item, index) => (
                    <li key={`${item.at || "earlier"}-${index}`}>
                      {item.at || "earlier"}: {item.target || "-"} — {item.ok ? "pass" : "fail"}
                      {item.code ? ` (${item.code})` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <>
              <div className="form-row">
                <label>URL
                  <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://app.example/health" />
                </label>
                <label>Command
                  <input value={command} onChange={(event) => setCommand(event.target.value)} placeholder="pytest -q" />
                </label>
              </div>
              <button type="button" className="btn" disabled={!detail.delivery} onClick={confirm}>Confirm</button>
            </>
          )}
        </Card>

        <Card title="Run history" actions={`${runs.length} run(s)`}>
          {runs.length ? (
            <Table
              columns={["Run", "Commit", "Verdict", "Risk", "Wall", "USD", ""]}
              rows={runs.slice().reverse().map((run) => [
                <span className="mono">{run.run_id}</span>,
                <span className="mono">{shortSha(run.base_commit)}</span>,
                <Pill tone={run.verdict === "allow" ? "green" : "red"}>{run.verdict}</Pill>,
                run.risk,
                fmtMs(run.duration_ms),
                fmtUsd(run.usd),
                <button type="button" className="btn ghost" onClick={onShowRuns}>Compare</button>,
              ])}
            />
          ) : <p className="muted small">No finished runs yet.</p>}
        </Card>
      </div>

      <div className="stack">
        <Card title="Verification team" actions={detail.team?.latest ? <Pill tone={detail.team.latest.verdict === "allow" ? "green" : "red"}>{detail.team.latest.verdict}</Pill> : null}>
          {detail.team?.latest ? (
            <p className="muted small">{[detail.team.latest.team, ...(detail.team.latest.blockers || [])].join(" · ")}</p>
          ) : <p className="muted small">Not run yet.</p>}
          <button type="button" className="btn ghost" onClick={() => onAction("team-verify")}>Verify with team</button>
        </Card>
        <Card title="Verifier" actions={null}>
          <dl className="kv">
            <dt>Name</dt><dd>{detail.verifier?.name || "local"}</dd>
            <dt>Isolation</dt><dd>{detail.verifier?.isolation || "process"}</dd>
          </dl>
        </Card>
        <Card title="Latest run" actions={<button type="button" className="btn ghost" disabled={!detail.run} onClick={onShowRun}>Open run</button>}>
          {detail.run ? (
            <dl className="kv">
              <dt>Run</dt><dd className="mono">{detail.run.run_id}</dd>
              <dt>Finished</dt><dd>{timeAgo(detail.run.finished_at)}</dd>
              <dt>State</dt><dd>{detail.run.state}</dd>
            </dl>
          ) : <p className="muted small">No run yet.</p>}
        </Card>
        <Card title="LAIX shadow" actions={null}>
          {detail.laix?.length ? (
            <Table
              columns={["Comparison", "Deterministic", "LAIX", "Reasons"]}
              rows={detail.laix.map((event) => [
                event.agrees == null ? "—" : event.agrees ? "agree" : "disagree",
                verdictText(event.deterministic),
                verdictText(event.candidate),
                (event.reason_codes || event.reasons || []).join(", ") || "—",
              ])}
            />
          ) : <p className="muted small">LAIX is off, or no shadow decision was recorded for this run.</p>}
        </Card>
      </div>
    </div>
  );
}
