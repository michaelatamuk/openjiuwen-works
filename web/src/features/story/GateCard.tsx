import { useState } from "react";

import { Card, Pill } from "../../ui/primitives";
import type { PlanRecord } from "./PlanCard";

type Props = {
  plan: PlanRecord;
  diff?: string | null;
  task: { id: string; state: string; budget?: { tokens?: number; usd?: number } };
  risk?: string | null;
  onAction: (action: string, body?: Record<string, unknown>) => unknown;
};

export function GateCard({ plan, diff, task, risk, onAction }: Props) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const validation = plan.validation;
  const critique = plan.critique;
  const budget = task.budget || {};

  async function decide(decision: string) {
    setBusy(true);
    try {
      await onAction("approve-plan", {
        decision,
        comment,
        by: "ui",
        device: "local",
      });
      setComment("");
    } finally {
      setBusy(false);
    }
  }

  function blocked(decision: string): boolean {
    return decision !== "approved" && !comment.trim();
  }

  return (
    <Card
      title="Plan gate"
      actions={<Pill tone={validation?.ok === false ? "red" : "amber"}>needs a person</Pill>}
    >
      <p className="muted small">
        You are approving plan v{plan.version ?? "?"}. The approval is bound to this plan, its
        starting version and its tests; editing the plan invalidates it.
      </p>
      <dl className="kv">
        <dt>Plan checks</dt>
        <dd>{validation?.ok === false ? `blocked: ${validation.errors?.join("; ")}` : "passed"}</dd>
        <dt>Reviewer</dt>
        <dd>
          {critique
            ? `${critique.allow ? "allow" : "block"} · score ${Math.round((critique.score || 0) * 100)}%`
            : "not run"}
          {critique?.concerns?.length ? ` · ${critique.concerns.join("; ")}` : ""}
        </dd>
        <dt>Budget</dt>
        <dd>
          estimate {plan.estimated_tokens ?? 0} tokens / ${(plan.estimated_usd ?? 0).toFixed(2)} of{" "}
          {budget.tokens ?? "?"} / ${(budget.usd ?? 0).toFixed(2)}
        </dd>
        <dt>Risk</dt>
        <dd>{risk || "low"}</dd>
        <dt>Impact</dt>
        <dd>
          {plan.verification?.filter(line => line.startsWith("Impact:")).join("; ") ||
            "no file names in the report"}
        </dd>
        <dt>Tests</dt>
        <dd>{plan.verification?.filter(line => line.includes("P0")).join("; ") || "as in the plan"}</dd>
      </dl>
      {diff ? <pre className="mono small">{diff}</pre> : null}
      <div className="export-row">
        <input
          aria-label="Gate comment"
          placeholder="Why? (required for changes or rejection)"
          value={comment}
          onChange={event => setComment(event.target.value)}
        />
        <button className="btn" type="button" disabled={busy || validation?.ok === false} onClick={() => decide("approved")}>
          Approve
        </button>
        <button className="btn ghost" type="button" disabled={busy || blocked("changes_requested")} onClick={() => decide("changes_requested")}>
          Request changes
        </button>
        <button className="btn ghost" type="button" disabled={busy || blocked("rejected")} onClick={() => decide("rejected")}>
          Reject
        </button>
      </div>
    </Card>
  );
}
