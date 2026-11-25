import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Modal } from "../../ui/Modal";
import { api } from "../../api/client";
import type { Device, Pairing } from "../../api/client";
import { BuilderSection } from "./BuilderSection";
import { buildSavePayload } from "./payload";
import {
  ModelInput,
  PlannerModeCard,
  ProviderCard,
  ProviderSetup,
} from "./cards";
import {
  PLANNER_MODES_FALLBACK,
  PLANNER_PROVIDER_ORDER,
  PROVIDER_FALLBACK,
  PROVIDER_ORDER,
  RUNTIME_FALLBACK,
  credentialLabel,
} from "./options";
import type {
  BuilderSettings,
  PlannerModeMeta,
  ProviderCatalog,
  ProviderMeta,
  RuntimeCatalog,
  SettingsSavePayload,
  SwarmMeta,
} from "./types";

export type SettingsDialogProps = {
  theme: string;
  density: string;
  pollMs: number;
  builder?: BuilderSettings | null;
  writable?: boolean;
  onSave: (payload: SettingsSavePayload) => unknown;
  onClose: () => void;
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function plannerProviderDefault(value: string | undefined): string {
  return value && PLANNER_PROVIDER_ORDER.includes(value) ? value : "claudecode";
}

export function SettingsDialog({
  theme,
  density,
  pollMs,
  builder,
  writable = true,
  onSave,
  onClose,
}: SettingsDialogProps) {
  const providers: ProviderCatalog = { ...PROVIDER_FALLBACK, ...(builder?.providers || {}) };
  const runtimes: RuntimeCatalog = { ...RUNTIME_FALLBACK, ...(builder?.runtimes || {}) };
  if (builder?.swarm?.available) {
    runtimes.swarm = { ...runtimes.swarm, available: true };
  }
  const [nextTheme, setNextTheme] = useState(theme);
  const [nextDensity, setNextDensity] = useState(density);
  const [nextPoll, setNextPoll] = useState(String(pollMs));
  const [repo, setRepo] = useState(localStorage.getItem("works.repo") || "");
  const [runtime, setRuntime] = useState(builder?.runtime || "openjiuwen");
  const [provider, setProvider] = useState(builder?.provider || "claudecode");
  const [separateVerifier, setSeparateVerifier] = useState(
    Boolean(builder?.verifier_provider && builder.verifier_provider !== builder.provider)
  );
  const [verifier, setVerifier] = useState(builder?.verifier_provider || builder?.provider || "claudecode");
  const [model, setModel] = useState(builder?.model || "");
  const [verifierModel, setVerifierModel] = useState(builder?.verifier_model || "");
  const [plannerMode, setPlannerMode] = useState(builder?.planner?.mode || "deterministic");
  const [plannerProvider, setPlannerProvider] = useState<string>(
    plannerProviderDefault(builder?.planner?.provider)
  );
  const [plannerModel, setPlannerModel] = useState(builder?.planner?.model || "");
  const [plannerCriticProvider, setPlannerCriticProvider] = useState<string>(
    plannerProviderDefault(builder?.planner?.critic_provider)
  );
  const [plannerCriticModel, setPlannerCriticModel] = useState(
    builder?.planner?.critic_model || ""
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [devices, setDevices] = useState<Device[]>([]);
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [deviceError, setDeviceError] = useState("");

  useEffect(() => {
    if (!writable) return;
    api.devices()
      .then((body) => setDevices(body.devices || []))
      .catch((err) => setDeviceError(errorMessage(err)));
  }, [writable]);

  async function pairDevice() {
    setDeviceError("");
    try {
      setPairing(await api.pairStart("device"));
    } catch (err) {
      setDeviceError(errorMessage(err));
    }
  }

  async function revokeDevice(deviceId: string) {
    try {
      await api.revokeDevice(deviceId);
      const body = await api.devices();
      setDevices(body.devices || []);
    } catch (err) {
      setDeviceError(errorMessage(err));
    }
  }

  const openjiuwen = runtime === "openjiuwen";
  const plannerModes: PlannerModeMeta[] = builder?.planner?.modes || PLANNER_MODES_FALLBACK;
  const plannerMeta: PlannerModeMeta = plannerModes.find((mode) => mode.id === plannerMode) || PLANNER_MODES_FALLBACK[0];
  const plannerOpen = plannerMode !== "deterministic";
  const plannerProviderMeta: ProviderMeta = providers[plannerProvider] || PROVIDER_FALLBACK.claudecode;
  const plannerCriticMeta: ProviderMeta = providers[plannerCriticProvider] || PROVIDER_FALLBACK.claudecode;
  const builderMeta: ProviderMeta = providers[provider] || PROVIDER_FALLBACK.claudecode;
  const verifierMeta: ProviderMeta = providers[separateVerifier ? verifier : provider] || {};
  const swarm: SwarmMeta = builder?.swarm || {};
  const builderCredential: string = openjiuwen
    ? credentialLabel(provider, builder?.credentials?.builder, providers)
    : swarm.available
      ? "External runtime"
      : "Needs setup";
  const verifierCredential: string = !openjiuwen
    ? "Own challenger"
    : separateVerifier
      ? credentialLabel(verifier, builder?.credentials?.verifier, providers)
      : builder?.credentials?.builder === "ready"
        ? "Uses builder credential"
        : "Needs setup";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await onSave(
        buildSavePayload({
          theme: nextTheme,
          density: nextDensity,
          pollMs: nextPoll,
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
        })
      );
    } catch (err) {
      setError(errorMessage(err) || "Could not save these settings.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal className="settings-dialog" onClose={onClose}>
      <div className="settings-head">
        <div>
          <span className="settings-kicker">Workspace</span>
          <h2>Settings</h2>
        </div>
        <span className={`settings-mode ${writable ? "write" : ""}`}>
          {writable ? "Local / writable" : "Read-only"}
        </span>
      </div>
      <form onSubmit={submit}>
        <BuilderSection
          writable={writable}
          openjiuwen={openjiuwen}
          builderCredential={builderCredential}
          runtime={runtime}
          onRuntime={setRuntime}
          runtimes={runtimes}
          provider={provider}
          onProvider={setProvider}
          providers={providers}
          providersKnown={Boolean(builder?.providers)}
          model={model}
          onModel={setModel}
          builderMeta={builderMeta}
          swarm={swarm}
        />

        <section className="settings-section">
          <div className="settings-section-head">
            <div>
              <h3>Planner</h3>
              <p>How Works turns the flow and scenarios into an approvable plan.</p>
            </div>
            <span className="settings-credential">{plannerOpen ? "Model-assisted" : "Deterministic"}</span>
          </div>
          <div className="planner-mode-grid" role="radiogroup" aria-label="Planner mode">
            {plannerModes.map((mode) => (
              <PlannerModeCard
                key={mode.id}
                id={mode.id}
                meta={mode}
                active={plannerMode === mode.id}
                onSelect={setPlannerMode}
              />
            ))}
          </div>
          <p className="planner-mode-summary">
            <b>{plannerMeta.label}</b> - {plannerMeta.kind}.
            {plannerMode === "shadow"
              ? " The deterministic plan still runs; this proposal is stored for comparison."
              : plannerMode === "assisted"
                ? " You still approve the plan before the build."
                : plannerMode === "deep"
                  ? " An independent critic reviews it before you approve."
                  : plannerMode === "spec"
                    ? " Requirements, design and tasks are saved beside the plan."
                    : plannerMode === "auto"
                      ? " Works picks assisted or deep from planned risk; you still approve."
                      : " No model is called."}
          </p>
          {plannerOpen ? (
            <>
              <div className="settings-subhead">Planner provider</div>
              <div className="provider-grid compact" role="radiogroup" aria-label="Planner provider">
                {PLANNER_PROVIDER_ORDER.map((id: string) => (
                  <ProviderCard
                    key={id}
                    id={id}
                    meta={providers[id] || PROVIDER_FALLBACK[id]}
                    active={plannerProvider === id}
                    disabled={!writable || !(providers[id] || PROVIDER_FALLBACK[id]).available}
                    onSelect={setPlannerProvider}
                  />
                ))}
              </div>
              <ProviderSetup ids={PLANNER_PROVIDER_ORDER} providers={providers} />
              <label className="settings-field" htmlFor="planner-model">
                <span>Planner model <em>{plannerProviderMeta.label} default</em></span>
                <ModelInput
                  id="planner-model"
                  value={plannerModel}
                  disabled={!writable}
                  onChange={(event) => setPlannerModel(event.target.value)}
                  provider={plannerProvider}
                />
              </label>
              {plannerMode === "deep" ? (
                <>
                  <div className="settings-subhead">Critic provider (deep mode)</div>
                  <div className="provider-grid compact" role="radiogroup" aria-label="Planner critic provider">
                    {PLANNER_PROVIDER_ORDER.map((id: string) => (
                      <ProviderCard
                        key={id}
                        id={id}
                        meta={providers[id] || PROVIDER_FALLBACK[id]}
                        active={plannerCriticProvider === id}
                        disabled={!writable || !(providers[id] || PROVIDER_FALLBACK[id]).available}
                        onSelect={setPlannerCriticProvider}
                      />
                    ))}
                  </div>
                  <ProviderSetup ids={PLANNER_PROVIDER_ORDER} providers={providers} />
                  <label className="settings-field" htmlFor="critic-model">
                    <span>Critic model <em>{plannerCriticMeta.label} default</em></span>
                    <ModelInput
                      id="critic-model"
                      value={plannerCriticModel}
                      disabled={!writable}
                      onChange={(event) => setPlannerCriticModel(event.target.value)}
                      provider={plannerCriticProvider}
                    />
                  </label>
                </>
              ) : null}
              <p className="settings-note">
                The planner reads the repository and never edits it. It proposes steps inside the flow
                contract; a person still approves the plan. {plannerMeta.kind}.
              </p>
            </>
          ) : (
            <p className="settings-note">
              Deterministic mode uses only the flow and scenario set. No model, no planner cost.
            </p>
          )}
        </section>

        {openjiuwen ? (
          <section className="settings-section">
            <div className="settings-section-head">
              <div>
                <h3>Verifier</h3>
                <p>Who challenges the builder&apos;s work.</p>
              </div>
              <span className={`settings-credential ${verifierCredential === "Ready" || verifierCredential === "Separate credential" ? "ready" : verifierCredential === "Needs setup" || verifierCredential === "Needs SDK" || verifierCredential === "Needs runtime" ? "missing" : ""}`}>
                {verifierCredential}
              </span>
            </div>
            <label className="settings-switch">
              <input
                type="checkbox"
                checked={separateVerifier}
                disabled={!writable}
                onChange={(event) => setSeparateVerifier(event.target.checked)}
              />
              Use a separate provider for review
            </label>
            {separateVerifier ? (
              <>
                <div className="settings-subhead">Verifier provider</div>
              <div className="provider-grid compact" role="radiogroup" aria-label="Verifier provider">
                  {PROVIDER_ORDER.map((id: string) => (
                    <ProviderCard
                      key={id}
                      id={id}
                      meta={providers[id] || PROVIDER_FALLBACK[id]}
                      active={verifier === id}
                      disabled={!writable || !(providers[id] || PROVIDER_FALLBACK[id]).available}
                      onSelect={setVerifier}
                    />
                  ))}
                </div>
                <ProviderSetup ids={PROVIDER_ORDER} providers={providers} />
                <label className="settings-field" htmlFor="verifier-model">
                  <span>Verifier model <em>{verifierMeta.label} default</em></span>
                  <ModelInput
                    id="verifier-model"
                    value={verifierModel}
                    disabled={!writable}
                    onChange={(event) => setVerifierModel(event.target.value)}
                    provider={verifier}
                  />
                </label>
              </>
            ) : (
              <p className="settings-note">The challenger uses the same provider and credential as the builder.</p>
            )}
          </section>
        ) : (
          <section className="settings-section">
            <div className="settings-section-head">
              <div>
                <h3>Verifier</h3>
                <p>JiuwenSwarm runs its own challenger through the adapter.</p>
              </div>
              <span className="settings-credential">Own challenger</span>
            </div>
            <p className="settings-note">
              Works does not apply its OpenJiuwen provider or credential split to this runtime. The adapter
              returns the challenge verdict, and Works records it as evidence.
            </p>
          </section>
        )}

        <section className="settings-section">
          <h3>Workspace</h3>
          <div className="form-row">
            <label>Theme <select value={nextTheme} onChange={(event) => setNextTheme(event.target.value)}><option value="light">Light</option><option value="dark">Dark</option></select></label>
            <label>Density <select value={nextDensity} onChange={(event) => setNextDensity(event.target.value)}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label>
            <label>Fallback refresh <select value={nextPoll} onChange={(event) => setNextPoll(event.target.value)}><option value="5000">5 s</option><option value="15000">15 s</option><option value="30000">30 s</option><option value="60000">60 s</option></select></label>
          </div>
          <label className="settings-field">
            <span>Default repository</span>
            <input value={repo} onChange={(event) => setRepo(event.target.value)} placeholder="C:\path\to\repo" />
          </label>
          <p className="settings-note">Live updates arrive over SSE; fallback refresh is used only if the stream drops.</p>
        </section>

        {writable ? (
          <section className="settings-section">
            <div className="settings-section-head">
              <div>
                <h3>Devices</h3>
                <p>Pair a phone or another computer; revoke a device you no longer use.</p>
              </div>
              <span className="settings-credential">{devices.length} paired</span>
            </div>
            <div className="device-list">
              {devices.map((device) => (
                <div className="device-row" key={device.id}>
                  <div>
                    <strong>{device.label}</strong>
                    <p className="small muted mono">{device.id}</p>
                    <p className="small muted">
                      Last seen {new Date(device.last_seen * 1000).toLocaleString()}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="btn ghost"
                    onClick={() => revokeDevice(device.id)}
                  >
                    Revoke
                  </button>
                </div>
              ))}
              {!devices.length ? <p className="muted small">No devices paired.</p> : null}
            </div>
            <button type="button" className="btn" onClick={pairDevice}>
              Pair a phone
            </button>
            {pairing ? (
              <p className="settings-note">
                Code <b className="mono">{pairing.code}</b> expires in {pairing.expires_in}s.
                Enter it on the device.
              </p>
            ) : null}
            {deviceError ? <p className="settings-error">{deviceError}</p> : null}
          </section>
        ) : null}

        {error ? <p className="settings-error" role="alert">{error}</p> : null}
        <div className="dialog-actions">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn" disabled={saving}>{saving ? "Saving..." : "Save"}</button>
        </div>
      </form>
    </Modal>
  );
}
