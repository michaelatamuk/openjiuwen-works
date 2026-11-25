import type { SettingsSavePayload } from "./types";

export type SavePayloadInput = {
  theme: string;
  density: string;
  pollMs: string | number;
  repo: string;
  runtime: string;
  provider: string;
  separateVerifier: boolean;
  verifier: string;
  model: string;
  verifierModel: string;
  plannerMode: string;
  plannerProvider: string;
  plannerModel: string;
  plannerCriticProvider: string;
  plannerCriticModel: string;
};

export function buildSavePayload({
  theme,
  density,
  pollMs,
  repo,
  runtime,
  provider,
  separateVerifier,
  verifier,
  model,
  verifierModel,
  plannerMode,
  plannerProvider,
  plannerModel,
  plannerCriticProvider,
  plannerCriticModel,
}: SavePayloadInput): SettingsSavePayload {
  const plannerOpen = plannerMode !== "deterministic";
  const deep = plannerMode === "deep";
  return {
    theme,
    density,
    pollMs: Number(pollMs),
    repo,
    builder: {
      runtime,
      provider,
      verifier_provider: separateVerifier && verifier !== provider ? verifier : null,
      model: model.trim() || null,
      verifier_model: separateVerifier ? verifierModel.trim() || null : null,
      planner_mode: plannerMode,
      planner_provider: plannerMode === "deterministic" ? null : plannerProvider,
      planner_model: plannerOpen ? plannerModel.trim() || null : null,
      planner_critic_provider: deep ? plannerCriticProvider : null,
      planner_critic_model: deep ? plannerCriticModel.trim() || null : null,
    },
  };
}
