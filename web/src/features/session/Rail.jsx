import { shortSha, stateLabel, timelineLabel } from "../../lib/format.js";
import { decisionFor } from "./model.js";

function Rail({ detail, onAction, onView }) {
  const rail = detail.rail || {};
  const release = detail.release || {};
  const decision = decisionFor(detail);
  const approvers = (rail.people || []).filter(Boolean);
  const blocker = release.blockers?.[0] || decision?.text;
  const checks = rail.checks?.find((item) => item.label === "Verdict")?.value || "—";
  const technical = [
    ["Commit", rail.factory?.base_commit],
    ["Checks", rail.factory?.checks_sha],
    ["Proof", rail.deliverables?.find((item) => item.label === "Proof")?.value],
  ].filter(([, value]) => value);
  return (
    <aside className="cl-rail" aria-label="Task context">
      <section>
        <h3>Decision</h3>
        <p className="cl-rail-state">{stateLabel(detail.task.state)}</p>
        <p className="cl-rail-note">{blocker || "No blocker recorded."}</p>
      </section>
      <section>
        <h3>Activity</h3>
        {(detail.thread || [])
          .filter((item) => !item.type.startsWith("thread.") && !item.type.startsWith("memory."))
          .slice(-5)
          .reverse()
          .map((item) => (
          <div className="cl-activity" key={item.seq}>
            <time>{new Date(item.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
            <span>{timelineLabel(item.type)}</span>
            <b>{String(item.title || item.body || "").slice(0, 70)}</b>
          </div>
          ))}
      </section>
      <section>
        <h3>Run</h3>
        <div className="cl-rail-row"><span>Flow</span><b>{rail.factory?.flow || "—"}</b></div>
        <div className="cl-rail-row"><span>Run</span><b className="mono">{shortSha(rail.factory?.run)}</b></div>
        <div className="cl-rail-row"><span>Checks</span><b>{checks}</b></div>
        <div className="cl-rail-row"><span>Cost</span><b>{rail.cost?.usd != null ? `$${Number(rail.cost.usd).toFixed(4)}` : "—"}</b></div>
      </section>
      <section>
        <h3>People</h3>
        {approvers.length ? approvers.map((person) => (
          <div className="cl-person" key={person}><span className="cl-person-dot" />{person}</div>
        )) : <p className="cl-rail-note">No person has acted yet.</p>}
      </section>
      {technical.length || rail.agents?.length ? (
        <details className="cl-rail-tech">
          <summary>Technical</summary>
          {technical.map(([label, value]) => (
            <div className="cl-rail-row" key={label}><span>{label}</span><b className="mono">{value}</b></div>
          ))}
          {(rail.agents || []).filter((agent) => agent.name).map((agent) => (
            <div className="cl-rail-row" key={agent.role}>
              <span>{agent.role}</span><b>{agent.name}{agent.detail ? ` · ${agent.detail}` : ""}</b>
            </div>
          ))}
        </details>
      ) : null}
    </aside>
  );
}

export { Rail };
