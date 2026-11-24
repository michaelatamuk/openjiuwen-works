export const REVIEW_TYPES = new Set(["thread.commentary", "thread.discussion"]);

export const PHASES = [
  { id: "plan", label: "Plan" },
  { id: "build", label: "Build" },
  { id: "check", label: "Check" },
  { id: "release", label: "Release" },
];

export function phaseFor(message) {
  const type = message.type;
  if (type === "task.created" || type?.startsWith("memory.")) return null;
  if (type === "team.verified" || type === "decision.made") return null;
  if (type === "plan.drafted") return "plan";
  if (type === "gate.decided") return /plan/i.test(message.title || "") ? "plan" : "release";
  if (type === "attempt.started") return "build";
  if (type === "risk.rated" || type === "plan.deviation") return "build";
  if (type === "note") return /proposal/i.test(`${message.title} ${message.body}`) ? "build" : "release";
  if (type === "step.started" || type === "step.finished") {
    const text = `${message.title} ${message.body} ${(message.facts || []).join(" ")}`;
    return /test/i.test(text) ? "check" : "plan";
  }
  if (["challenge.decided", "finding"].includes(type)) return "check";
  if (type === "delivery.finished" || type === "confirmation.finished") return "release";
  if (type?.startsWith("thread.")) return "release";
  return "release";
}

export function currentPhase(state) {
  if (["queued", "reproducing", "reproduced", "planning"].includes(state)) return "plan";
  if (["plan_approved", "building"].includes(state)) return "build";
  if (state === "checking") return "check";
  return "release";
}

export function phaseState(phase, currentId, taskState) {
  if (["released", "reverted"].includes(taskState)) return "done";
  const order = ["plan", "build", "check", "release"];
  const index = order.indexOf(phase);
  const current = order.indexOf(currentId);
  if (index < current) return "done";
  if (index === current) return taskState === "blocked" ? "blocked" : "current";
  return "pending";
}

export function phaseSummary(id, detail, items) {
  if (!items.length) return "Not started";
  if (id === "plan") {
    const plan = items.find((item) => item.type === "plan.drafted");
    const rows = plan?.card?.rows || [];
    return rows[0]?.[1] ? `${rows[0][1]} scenarios` : "Plan drafted";
  }
  if (id === "build") {
    const files = detail.evidence?.files_changed?.length || 0;
    return files ? `${files} file${files === 1 ? "" : "s"} changed` : "Build recorded";
  }
  if (id === "check") {
    const outcomes = detail.evidence?.verdict?.outcomes || [];
    const passed = outcomes.filter((item) => item.passed).length;
    return outcomes.length ? `${passed}/${outcomes.length} checks passed` : "Check recorded";
  }
  if (detail.release?.released) return "Released";
  if (detail.task.state === "proved") return "Needs your approval";
  if (detail.task.state === "blocked") return "Blocked";
  return "Waiting";
}

export function groupItems(items) {
  const out = [];
  for (const message of items) {
    if (REVIEW_TYPES.has(message.type)) {
      const last = out[out.length - 1];
      if (last?.review) last.review.push(message);
      else out.push({ key: `review-${message.seq}`, review: [message] });
    } else {
      out.push({ key: message.seq, message });
    }
  }
  return out;
}

export function sourceUrl(task) {
  const ref = String(task?.source?.ref || "");
  if (/^https?:\/\//.test(ref)) return ref;
  const match = ref.match(/^([^/]+)\/([^#]+)#(\d+)$/);
  if (match) return `https://github.com/${match[1]}/${match[2]}/issues/${match[3]}`;
  return "";
}

export function decisionFor(detail) {
  const state = detail.task.state;
  const release = detail.release || {};
  if (state === "planning") {
    return {
      tone: "amber",
      label: "Plan gate",
      text: "A person needs to approve the plan before the build starts.",
      action: "approve-plan",
      button: "Approve plan",
    };
  }
  if (state === "proved" && !release.released) {
    return {
      tone: "amber",
      label: "Release gate",
      text: "The proof is ready. A person needs to release it back to the product.",
      action: "release",
      button: "Approve release",
    };
  }
  if (state === "blocked") {
    return {
      tone: "red",
      label: "Blocked",
      text: detail.pipeline?.blocked?.why || "The run stopped and needs a person.",
      action: null,
      view: "evidence",
      button: "Open evidence",
    };
  }
  return null;
}
