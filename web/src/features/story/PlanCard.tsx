import { useEffect, useState } from "react";

import { Card, Pill } from "../../ui/primitives";

export type PlanStep = {
  id?: string;
  node: string;
  title?: string;
  intent?: string;
  files?: string[];
  commands?: string[];
  done_when?: string;
  risk?: string;
  depends_on?: string[];
  reversible?: boolean;
};

export type PlanRecord = {
  version?: number;
  hash?: string;
  summary?: string;
  steps?: PlanStep[];
  validation?: { ok?: boolean; errors?: string[]; warnings?: string[] } | null;
  critique?: { allow?: boolean; score?: number; concerns?: string[] } | null;
  verification?: string[];
  estimated_tokens?: number;
  estimated_usd?: number;
  estimated_minutes?: number;
  notes?: string[];
  approved_by?: string | null;
};

type Props = {
  plan: PlanRecord;
  diff?: string | null;
  onAction: (action: string, body?: Record<string, unknown>) => unknown;
};

const EMPTY: PlanStep = { node: "build", title: "", intent: "", commands: [], done_when: "" };

export function PlanCard({ plan, diff, onAction }: Props) {
  const [steps, setSteps] = useState<PlanStep[]>(plan.steps || []);
  const [draft, setDraft] = useState<PlanStep>(EMPTY);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSteps(plan.steps || []);
  }, [plan.hash]);

  const nodes = [...new Set((plan.steps || []).map((step) => step.node))];

  function change(index: number, field: "intent" | "done_when", value: string) {
    setSteps((current) =>
      current.map((step, position) => (position === index ? { ...step, [field]: value } : step)),
    );
  }

  function remove(index: number) {
    setSteps((current) => current.filter((_, position) => position !== index));
  }

  function add() {
    if (!draft.node.trim() || !draft.done_when?.trim()) return;
    setSteps((current) => [
      ...current,
      {
        ...draft,
        id: draft.id || `person-${current.length + 1}-${draft.node}`,
        title: draft.title || draft.node,
        commands: draft.commands || [],
      },
    ]);
    setDraft({ ...EMPTY, node: draft.node });
  }

  async function save() {
    setBusy(true);
    try {
      await onAction("set-plan", { steps, comment });
      setComment("");
    } finally {
      setBusy(false);
    }
  }

  const validation = plan.validation;

  return (
    <Card
      title={`Plan v${plan.version ?? "?"}`}
      actions={
        <Pill tone={validation?.ok === false ? "red" : plan.approved_by ? "green" : "amber"}>
          {plan.approved_by ? `approved by ${plan.approved_by}` : "waiting for a person"}
        </Pill>
      }
    >
      <p className="muted small">{plan.summary || "No summary recorded."}</p>
      {validation?.errors?.length ? (
        <ul className="bullets">
          {validation.errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      ) : null}
      {validation?.warnings?.length ? (
        <p className="muted small">{validation.warnings.join(" · ")}</p>
      ) : null}
      <ol className="bullets">
        {steps.map((step, index) => (
          <li key={`${step.id || step.node}-${index}`}>
            <strong>{step.title || step.node}</strong>
            <div className="kv">
              <label>
                Intent
                <input
                  aria-label={`Intent for ${step.node}`}
                  value={step.intent || ""}
                  onChange={(event) => change(index, "intent", event.target.value)}
                />
              </label>
              <label>
                Done when
                <input
                  aria-label={`Done when for ${step.node}`}
                  value={step.done_when || ""}
                  onChange={(event) => change(index, "done_when", event.target.value)}
                />
              </label>
            </div>
            {step.commands?.length ? (
              <p className="mono small">{step.commands.join(" · ")}</p>
            ) : null}
            <button className="btn ghost" type="button" onClick={() => remove(index)}>
              Remove
            </button>
          </li>
        ))}
      </ol>
      <div className="stack">
        <div className="export-row">
          <select
            aria-label="Node for the new step"
            value={draft.node}
            onChange={(event) => setDraft({ ...draft, node: event.target.value })}
          >
            {nodes.map((node) => (
              <option key={node} value={node}>
                {node}
              </option>
            ))}
          </select>
          <input
            aria-label="New step title"
            placeholder="Step title"
            value={draft.title}
            onChange={(event) => setDraft({ ...draft, title: event.target.value })}
          />
          <input
            aria-label="New step done when"
            placeholder="Done when"
            value={draft.done_when}
            onChange={(event) => setDraft({ ...draft, done_when: event.target.value })}
          />
          <button className="btn" type="button" onClick={add}>
            Add step
          </button>
        </div>
        <div className="export-row">
          <input
            aria-label="Plan comment"
            placeholder="Why this edit?"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
          <button className="btn" type="button" disabled={busy} onClick={save}>
            Save new version
          </button>
        </div>
      </div>
      {diff ? <pre className="mono small">{diff}</pre> : null}
    </Card>
  );
}
