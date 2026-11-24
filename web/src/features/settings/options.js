/** Provider, runtime and planner catalogues with fallbacks for an offline UI. */

const PROVIDER_FALLBACK = {
  claudecode: { label: "Claude Code", kind: "General coding harness", available: true, missing: "Needs SDK" },
  dsh: { label: "DeepSeek Harness", kind: "DeepSeek native", available: false, missing: "Needs SDK" },
  native: { label: "Jiuwen native", kind: "In-process DeepAgent", available: false, missing: "Needs runtime" },
  codex: { label: "Codex", kind: "OpenAI Codex", available: false, missing: "Needs SDK" },
};

const PROVIDER_ORDER = ["claudecode", "dsh", "native", "codex"];

const RUNTIME_FALLBACK = {
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

const RUNTIME_ORDER = ["openjiuwen", "swarm"];

const PLANNER_MODES_FALLBACK = [
  { id: "deterministic", label: "Deterministic", kind: "Flow + scenarios only; no model" },
  { id: "shadow", label: "Shadow", kind: "Model proposal stored beside the plan" },
  { id: "assisted", label: "Assisted", kind: "Model proposal merged and linted" },
  { id: "deep", label: "Deep", kind: "Assisted plus an independent critic" },
  { id: "spec", label: "Spec", kind: "Requirements, design and tasks artefacts plus the plan" },
  { id: "auto", label: "Auto", kind: "Pick assisted or deep from planned risk; you still approve" },
];

const PLANNER_PROVIDER_ORDER = ["claudecode", "native"];

const MODEL_SUGGESTIONS = {
  claudecode: ["deepseek-chat", "deepseek-reasoner", "claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"],
  dsh: ["deepseek-chat", "deepseek-reasoner"],
  native: ["deepseek-chat", "deepseek-reasoner", "gpt-5", "gpt-5-mini"],
  codex: ["gpt-5", "gpt-5-codex", "o4-mini"],
};

function credentialLabel(provider, state, providers) {
  const meta = providers[provider];
  if (!meta?.available) return meta?.missing || "Needs setup";
  if (provider === "dsh" || provider === "codex") return "Provider-managed";
  return {
    ready: "Ready",
    missing: "Needs setup",
    separate: "Separate credential",
    shared: "Shared credential",
    builder: "Uses builder credential",
  }[state] || "Managed locally";
}

const PROVIDER_LETTERS = { claudecode: "C", dsh: "D", native: "J", codex: "X" };

export {
  MODEL_SUGGESTIONS,
  PLANNER_MODES_FALLBACK,
  PLANNER_PROVIDER_ORDER,
  PROVIDER_FALLBACK,
  PROVIDER_LETTERS,
  PROVIDER_ORDER,
  RUNTIME_FALLBACK,
  RUNTIME_ORDER,
  credentialLabel,
};
