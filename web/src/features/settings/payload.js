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
}) {
  const plannerOpen = plannerMode !== "deterministic";
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
      planner_critic_provider: plannerMode === "deep" ? plannerCriticProvider : null,
      planner_critic_model: plannerMode === "deep" ? plannerCriticModel.trim() || null : null,
    },
  };
}
