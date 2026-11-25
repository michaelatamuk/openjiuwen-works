export const stateHuman: Record<string, string> = {
  queued: "Waiting in queue",
  reproducing: "Confirming the problem",
  reproduced: "Problem confirmed",
  planning: "Planning the fix",
  plan_approved: "Plan approved",
  building: "Fixing it now",
  checking: "Checking it now",
  proved: "Ready for release",
  waiting_review: "Waiting for a person",
  waiting_ci: "Running checks",
  waiting_deploy: "Delivering the fix",
  releasing: "Delivering the fix",
  released: "Delivered",
  reverted: "Reverted",
  blocked: "Needs attention",
  done: "Done",
  active: "In progress",
  pending: "Not yet",
};

export const timelines: Record<string, string> = {
  "task.created": "Reported",
  "state.changed": "Stage changed",
  "plan.drafted": "Plan drafted",
  "gate.decided": "Approval recorded",
  "step.started": "Step started",
  "step.finished": "Step finished",
  "decision.made": "Decision recorded",
  "decision.shadow": "Shadow comparison",
  "risk.rated": "Risk assessed",
  "challenge.decided": "Independent check",
  note: "Run finished",
  finding: "Finding recorded",
  "memory.reported": "PPMA memory",
  "memory.failed": "PPMA memory failed",
  "memory.recalled": "Memory recall",
  "memory.recall_failed": "Memory recall failed",
  "readiness.checked": "Readiness checked",
  "team.verified": "Verification team",
  "delivery.finished": "Delivered",
  "confirmation.finished": "Confirmed",
  "thread.note": "Context added",
  "thread.agent": "Mira answered",
  "thread.commentary": "AI commentary",
  "thread.discussion": "AI discussion",
  "wait.started": "Waiting",
  "wait.woken": "Woke up",
  "wait.expired": "Wait expired",
};

export const groups: Array<[string, string, string[]]> = [
  ["needs", "Needs you", ["blocked", "waiting_review", "waiting_ci", "waiting_deploy", "proved"]],
  ["working", "In progress", ["reproducing", "reproduced", "planning", "plan_approved", "building", "checking", "releasing"]],
  ["queued", "Queued", ["queued"]],
  ["done", "Done", ["released", "reverted"]],
];

export const roleLabel: Record<string, string> = {
  person: "Person",
  builder: "Builder",
  verifier: "Verifier",
  challenger: "Challenger",
  team: "Team",
  delivery: "Delivery",
  confirmation: "Confirmation",
  system: "System",
  tracker: "Tracker",
  monitor: "Monitor",
  mira: "Mira",
  inspector: "Inspector",
  reporter: "Reporter",
};

export const roleLetter: Record<string, string> = {
  person: "P",
  builder: "B",
  verifier: "V",
  challenger: "C",
  team: "T",
  delivery: "D",
  confirmation: "✓",
  system: "·",
  tracker: "T",
  monitor: "M",
  mira: "M",
  inspector: "I",
  reporter: "R",
};

function text(value: unknown): string {
  return value == null ? "" : String(value);
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function stateLabel(value: string | null | undefined): string {
  return stateHuman[value ?? ""] || String(value || "unknown").replaceAll("_", " ");
}

export function riskLabel(value: string | null | undefined): string {
  return (
    { low: "Low risk", medium: "Medium risk", high: "High risk" }[value ?? ""] ?? value ?? ""
  );
}

export function riskTone(value: string | null | undefined): string {
  return { high: "red", medium: "amber", low: "green" }[value ?? ""] || "";
}

export function timelineLabel(type: string | null | undefined): string {
  return timelines[type ?? ""] || String(type || "").replaceAll("_", " ");
}

export function fmtUsd(value: unknown): string {
  const number = Number(value ?? 0);
  return `$${number.toFixed(number >= 10 ? 2 : 4)}`;
}

export function fmtMs(value: unknown): string {
  const number = Number(value ?? 0);
  if (number < 1000) return `${number} ms`;
  if (number < 60_000) return `${(number / 1000).toFixed(1)} s`;
  return `${Math.round(number / 60_000)} min`;
}

export function timeAgo(iso?: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86_400)}d ago`;
}

export function shortSha(value?: unknown): string {
  return String(value || "").slice(0, 12) || "—";
}

export type SummaryEvent = {
  type?: string;
  data?: Record<string, unknown>;
};

export function eventSummary(event?: SummaryEvent | null): string {
  const data = event?.data || {};
  if (event?.type === "state.changed") return stateLabel(text(data.to));
  if (event?.type === "gate.decided") return `${text(data.gate)} gate: ${text(data.decision)}`;
  if (event?.type === "step.started") return `step ${text(data.step)}`;
  if (event?.type === "step.finished") return `${text(data.step)} exit ${text(data.exit_code)}`;
  if (event?.type === "decision.made") {
    return `${text(data.verb)} · ${text(data.reason_code || "")}`;
  }
  if (event?.type === "risk.rated") return `${text(data.level)} risk`;
  if (event?.type === "team.verified") {
    return `${text(data.verdict)} · ${list(data.blockers).length} blocker(s)`;
  }
  if (event?.type === "thread.agent") return text(data.question).slice(0, 80);
  if (event?.type === "note") return text(data.message).slice(0, 90);
  if (event?.type === "memory.reported") return `via ${text(data.via || "run")}`;
  if (event?.type === "plan.drafted") return `${list(data.scenario_ids).length} scenario(s)`;
  return Object.entries(data)
    .slice(0, 2)
    .map(([key, value]) => `${key}=${String(value).slice(0, 40)}`)
    .join(" · ");
}

export type AiSegment = {
  type: "strong" | "code" | "text";
  value: string;
  key: number;
};

export function aiText(input?: string | null): AiSegment[] {
  const value = String(input || "");
  const parts = value.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return { type: "strong", value: part.slice(2, -2), key: index };
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return { type: "code", value: part.slice(1, -1), key: index };
    }
    return { type: "text", value: part, key: index };
  });
}
