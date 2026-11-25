/** Provider, runtime and planner catalogues with fallbacks for an offline UI. */

import type { PlannerModeMeta, ProviderMeta, RuntimeMeta } from "./types";

export const PROVIDER_FALLBACK: Record<string, ProviderMeta> = {
  // Never claim a provider is ready before the daemon says so: an offline or unauthenticated
  // page must not offer a provider it cannot run.
  claudecode: {
    label: "Claude Code",
    kind: "General coding harness",
    available: false,
    missing: "Unknown",
  },
  dsh: { label: "DeepSeek Harness", kind: "DeepSeek native", available: false, missing: "Unknown" },
  native: {
    label: "Jiuwen native",
    kind: "In-process DeepAgent",
    available: false,
    missing: "Unknown",
  },
  codex: { label: "Codex", kind: "OpenAI Codex", available: false, missing: "Unknown" },
};

export const PROVIDER_ORDER: string[] = ["claudecode", "dsh", "native", "codex"];

export const RUNTIME_FALLBACK: Record<string, RuntimeMeta> = {
  openjiuwen: {
    label: "OpenJiuwen harness",
    kind: "One agent inside Works; pick a provider",
    scope: "inside Works",
    available: true,
  },
  swarm: {
    label: "JiuwenSwarm",
    kind: "A multi-agent team outside Works",
    scope: "outside Works",
    available: false,
  },
};

export const RUNTIME_ORDER: string[] = ["openjiuwen", "swarm"];

export const PLANNER_MODES_FALLBACK: PlannerModeMeta[] = [
  { id: "deterministic", label: "Deterministic", kind: "Flow + scenarios only; no model" },
  { id: "shadow", label: "Shadow", kind: "Model proposal stored beside the plan" },
  { id: "assisted", label: "Assisted", kind: "Model proposal merged and linted" },
  { id: "deep", label: "Deep", kind: "Assisted plus an independent critic" },
  { id: "spec", label: "Spec", kind: "Requirements, design and tasks artefacts plus the plan" },
  { id: "auto", label: "Auto", kind: "Pick assisted or deep from planned risk; you still approve" },
];

export const PLANNER_PROVIDER_ORDER: string[] = ["claudecode", "native"];

export const MODEL_SUGGESTIONS: Record<string, string[]> = {
  claudecode: [
    "deepseek-chat",
    "deepseek-reasoner",
    "claude-sonnet-4-5",
    "claude-opus-4-1",
    "claude-haiku-4-5",
  ],
  dsh: ["deepseek-chat", "deepseek-reasoner"],
  native: ["deepseek-chat", "deepseek-reasoner", "gpt-5", "gpt-5-mini"],
  codex: ["gpt-5", "gpt-5-codex", "o4-mini"],
};

const CREDENTIAL_LABELS: Record<string, string> = {
  ready: "Ready",
  missing: "Needs setup",
  separate: "Separate credential",
  shared: "Shared credential",
  builder: "Uses builder credential",
};

export function credentialLabel(
  provider: string,
  state: string | undefined,
  providers: Record<string, ProviderMeta>,
): string {
  const meta = providers[provider];
  if (!meta?.available) return meta?.missing || "Needs setup";
  if (provider === "dsh" || provider === "codex") return "Provider-managed";
  return CREDENTIAL_LABELS[state || ""] || "Managed locally";
}

export const PROVIDER_LETTERS: Record<string, string> = {
  claudecode: "C",
  dsh: "D",
  native: "J",
  codex: "X",
};
