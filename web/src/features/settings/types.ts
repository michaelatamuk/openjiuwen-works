/** Domain types for the settings screen. Catalogues come from untyped option
 *  modules, so the screen widens them into these shapes at the boundary. */

export type ProviderMeta = {
  label?: string;
  kind?: string;
  available?: boolean;
  missing?: string;
  reason?: string;
  install?: string[];
};

export type ProviderCatalog = Record<string, ProviderMeta>;

export type RuntimeMeta = {
  label?: string;
  kind?: string;
  scope?: string;
  available?: boolean;
  missing?: string;
};

export type RuntimeCatalog = Record<string, RuntimeMeta>;

export type PlannerModeMeta = {
  id: string;
  label: string;
  kind: string;
};

export type PlannerSettings = {
  mode?: string;
  provider?: string;
  model?: string;
  critic_provider?: string;
  critic_model?: string;
  modes?: PlannerModeMeta[];
};

export type SwarmMeta = {
  available?: boolean;
  detail?: string;
  steps?: string[];
};

export type BuilderCredentials = {
  builder?: string;
  verifier?: string;
};

export type BuilderSettings = {
  runtime?: string;
  provider?: string;
  verifier_provider?: string | null;
  model?: string;
  verifier_model?: string;
  credentials?: BuilderCredentials;
  swarm?: SwarmMeta;
  providers?: ProviderCatalog;
  runtimes?: RuntimeCatalog;
  planner?: PlannerSettings;
};

export type SettingsBuilderPayload = {
  runtime: string;
  provider: string;
  verifier_provider: string | null;
  model: string | null;
  verifier_model: string | null;
  planner_mode: string;
  planner_provider: string | null;
  planner_model: string | null;
  planner_critic_provider: string | null;
  planner_critic_model: string | null;
};

export type SettingsSavePayload = {
  theme: string;
  density: string;
  pollMs: number;
  repo: string;
  builder: SettingsBuilderPayload;
};
