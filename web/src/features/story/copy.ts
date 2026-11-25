import { stateLabel } from "../../lib/format";

export type CopyTask = {
  state: string;
  product?: string;
};

export type CopyDetail = {
  task: CopyTask;
  pipeline?: { blocked?: { why?: string } } | null;
};

export type CopyStage = {
  id: string;
  label: string;
};

export function headline(detail: CopyDetail): string {
  const state = detail.task.state;
  if (state === "blocked") return "Not fixed yet";
  if (state === "proved") return "Ready for release";
  if (state === "released") return `Fixed and back in ${detail.task.product}`;
  if (state === "reverted") return "Reverted";
  if (state === "queued") return "In the queue";
  if (state === "building" || state === "plan_approved") return "Fixing it now";
  if (state === "checking") return "Checking it now";
  return stateLabel(state);
}

export function lede(detail: CopyDetail): string {
  const blocked = detail.pipeline?.blocked;
  if (blocked) return blocked.why ?? "";
  if (detail.task.state === "proved") {
    return `The fix is built and checked. A person needs to release it back to ${detail.task.product}.`;
  }
  if (detail.task.state === "released") {
    return `The fix is released and the proof is ready for ${detail.task.product}.`;
  }
  if (detail.task.state === "queued") return "The report is queued. The factory has not started yet.";
  return "The factory is working on the reported problem.";
}

const STOPS: Record<string, Record<string, string>> = {
  picked_up: {
    active: "Mira is picking it up",
    done: "Picked up",
    blocked: "Mira could not pick it up",
  },
  confirmed: {
    active: "Mira is confirming it",
    done: "Confirmed",
    blocked: "Mira could not confirm it",
  },
  fixed: { active: "Mira is fixing it", done: "Fixed", blocked: "Mira stopped while fixing" },
  checked: { active: "Mira is checking it", done: "Checked", blocked: "Mira stopped at a check" },
  delivered: {
    active: "Mira is delivering it",
    done: "Delivered",
    blocked: "Mira stopped before delivery",
  },
};

export function milestoneCopy(
  stage: CopyStage,
  display: string,
  detail?: CopyDetail | null,
): string {
  const product = detail?.task?.product || "the product";
  const stops = { ...STOPS };
  stops.delivered = {
    ...stops.delivered,
    active: stage.label.startsWith("Release") ? "Mira is ready to release" : "Mira is delivering it",
    done: `Delivered to ${product}`,
  };
  return stops[stage.id]?.[display] || stage.label;
}
