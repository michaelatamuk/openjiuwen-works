export const stateHuman = {
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

export const timelines = {
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
  "note": "Run finished",
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

export const groups = [
  ["needs", "Needs you", ["blocked", "waiting_review", "waiting_ci", "waiting_deploy", "proved"]],
  ["working", "In progress", ["reproducing", "reproduced", "planning", "plan_approved", "building", "checking", "releasing"]],
  ["queued", "Queued", ["queued"]],
  ["done", "Done", ["released", "reverted"]],
];

export const roleLabel = {
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

export const roleLetter = {
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

export function stateLabel(value) {
  return stateHuman[value] || String(value || "unknown").replaceAll("_", " ");
}

export function stateTone(value) {
  if (["proved", "released"].includes(value)) return "green";
  if (["blocked", "reverted"].includes(value)) return "red";
  if (["waiting_review", "waiting_ci", "waiting_deploy"].includes(value)) return "amber";
  return "";
}

export function riskLabel(value) {
  return { low: "Low risk", medium: "Medium risk", high: "High risk" }[value] || value;
}

export function riskTone(value) {
  return { high: "red", medium: "amber", low: "green" }[value] || "";
}

export function timelineLabel(type) {
  return timelines[type] || String(type || "").replaceAll("_", " ");
}

export function fmtUsd(value) {
  const number = Number(value ?? 0);
  return `$${number.toFixed(number >= 10 ? 2 : 4)}`;
}

export function fmtMs(value) {
  const number = Number(value ?? 0);
  if (number < 1000) return `${number} ms`;
  if (number < 60_000) return `${(number / 1000).toFixed(1)} s`;
  return `${Math.round(number / 60_000)} min`;
}

export function timeAgo(iso) {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86_400)}d ago`;
}

export function shortSha(value) {
  return String(value || "").slice(0, 12) || "—";
}

export function eventSummary(event) {
  const data = event?.data || {};
  if (event?.type === "state.changed") return stateLabel(data.to);
  if (event?.type === "gate.decided") return `${data.gate} gate: ${data.decision}`;
  if (event?.type === "step.started") return `step ${data.step}`;
  if (event?.type === "step.finished") return `${data.step} exit ${data.exit_code}`;
  if (event?.type === "decision.made") return `${data.verb} · ${data.reason_code || ""}`;
  if (event?.type === "risk.rated") return `${data.level} risk`;
  if (event?.type === "team.verified") return `${data.verdict} · ${(data.blockers || []).length} blocker(s)`;
  if (event?.type === "thread.agent") return String(data.question || "").slice(0, 80);
  if (event?.type === "note") return String(data.message || "").slice(0, 90);
  if (event?.type === "memory.reported") return `via ${data.via || "run"}`;
  if (event?.type === "plan.drafted") return `${(data.scenario_ids || []).length} scenario(s)`;
  return Object.entries(data)
    .slice(0, 2)
    .map(([key, value]) => `${key}=${String(value).slice(0, 40)}`)
    .join(" · ");
}

export function aiText(text) {
  const value = String(text || "");
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
