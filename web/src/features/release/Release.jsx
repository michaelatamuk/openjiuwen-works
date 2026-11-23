import { useState } from "react";
import { fmtMs, fmtUsd, shortSha, timeAgo } from "../../lib/format.js";
import { Card, Pill, Table } from "../../ui/primitives.jsx";

function gateText(value) {
  if (!value) return "NOT YET";
  if (typeof value === "string") return value;
  const decision = String(value.decision || value.gate || "").toUpperCase();
  return value.by ? `${decision} · ${value.by}` : decision || "NOT YET";
}

function Gate({ label, value }) {
  const text = gateText(value);
  const ready = text.toLowerCase().includes("approved");
  return (
    <div className="gate-row">
      <span>{label}</span>
      <Pill tone={ready ? "green" : "amber"}>{text}</Pill>
    </div>
  );
}

export function Release({ detail, onAction, onShowRuns, onShowRun, onToast }) {
  const release = detail.release || {};
  const runs = detail.runs || [];
  const [provider, setProvider] = useState("none");
  const [tracker, setTracker] = useState("");
  const [dryRun, setDryRun] = useState(false);
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");

  async function deliver() {
    try {
      await onAction("deliver", { provider, tracker: tracker || null, dry_run: dryRun });
    } catch (error) {
      onToast(`Delivery failed: ${error.message}`);
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
      onToast(`Confirmation failed: ${error.message}`);
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
          <button type="button" className="btn" disabled={!release.ready || release.released} onClick={() => onAction("release")}>
            {release.released ? "Released" : "Approve release"}
          </button>
        </Card>

        <Card title="Delivery" actions={detail.delivery ? <Pill tone={detail.delivery.dry_run ? "amber" : "green"}>{detail.delivery.dry_run ? "dry run" : "delivered"}</Pill> : null}>
          {detail.delivery ? (
            <dl className="kv">
              <dt>Commit</dt><dd className="mono">{shortSha(detail.delivery.commit)}</dd>
              <dt>Branch</dt><dd className="mono">{detail.delivery.branch || "—"}</dd>
              <dt>Pull request</dt><dd>{detail.delivery.pr_url ? <a href={detail.delivery.pr_url} target="_blank" rel="noopener noreferrer">{detail.delivery.pr_url}</a> : "—"}</dd>
              <dt>Comment</dt><dd>{detail.delivery.comment_url ? <a href={detail.delivery.comment_url} target="_blank" rel="noopener noreferrer">open</a> : "—"}</dd>
            </dl>
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
            <dl className="kv">
              <dt>Target</dt><dd>{detail.confirmation.target || "—"}</dd>
              <dt>Output</dt><dd className="mono">{shortSha(detail.confirmation.output_sha256)}</dd>
            </dl>
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
        <Card title="Verifier">
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
        <Card title="LAIX shadow">
          {detail.laix?.length ? (
            <Table
              columns={["Comparison", "Deterministic", "LAIX", "Reasons"]}
              rows={detail.laix.map((event) => [
                event.agrees == null ? "—" : event.agrees ? "agree" : "disagree",
                event.deterministic?.verb || event.deterministic || "—",
                event.candidate?.verb || event.candidate || "—",
                (event.reason_codes || event.reasons || []).join(", ") || "—",
              ])}
            />
          ) : <p className="muted small">LAIX is off, or no shadow decision was recorded for this run.</p>}
        </Card>
      </div>
    </div>
  );
}
