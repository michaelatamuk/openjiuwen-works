import { useState } from "react";
import { Modal } from "../../ui/Modal.jsx";

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

function ProviderCard({ id, meta, active, disabled, onSelect }) {
  const letter = PROVIDER_LETTERS[id] || (meta.label || id).slice(0, 1).toUpperCase();
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      className={`provider-card provider-${id} ${active ? "active" : ""}`}
      disabled={disabled}
      onClick={() => onSelect(id)}
    >
      <span className="provider-mark" aria-hidden="true">{letter}</span>
      <span className="provider-copy">
        <b>{meta.label || id}</b>
        <em>{meta.kind || "Model harness"}</em>
      </span>
      <span className={`provider-state ${meta.available ? "ready" : "missing"}`}>
        {meta.available ? "Ready" : (meta.missing || "Needs setup")}
      </span>
    </button>
  );
}

function ModelInput({ id, value, onChange, disabled, provider, placeholder = "Provider default" }) {
  const listId = `model-options-${id}`;
  return (
    <>
      <input
        list={listId}
        value={value}
        disabled={disabled}
        onChange={onChange}
        placeholder={placeholder}
      />
      <datalist id={listId}>
        {(MODEL_SUGGESTIONS[provider] || []).map((model) => (
          <option key={model} value={model} />
        ))}
      </datalist>
    </>
  );
}

function ProviderSetup({ ids, providers }) {
  const missing = ids.filter((id) => !(providers[id] || PROVIDER_FALLBACK[id])?.available);
  if (!missing.length) return null;
  return (
    <details className="provider-setup" open>
      <summary>Setup for unavailable providers</summary>
      {missing.map((id) => {
        const meta = providers[id] || PROVIDER_FALLBACK[id];
        return (
          <div className="provider-setup-row" key={id}>
            <b>{meta.label || id}</b>
            <p>{meta.reason || "This provider is not ready in Works' Python environment."}</p>
            {(meta.install || []).map((command) => (
              <code key={command}>{command}</code>
            ))}
          </div>
        );
      })}
    </details>
  );
}

function PlannerModeCard({ id, meta, active, onSelect }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      className={`planner-mode-card ${active ? "active" : ""}`}
      onClick={() => onSelect(id)}
    >
      <b>{meta.label}</b>
      <em>{meta.kind}</em>
    </button>
  );
}

function RuntimeCard({ id, meta, active, onSelect }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      className={`runtime-card runtime-${id} ${active ? "active" : ""}`}
      onClick={() => onSelect(id)}
    >
      <span className="runtime-copy">
        <b>{meta.label}</b>
        <em>{meta.kind}</em>
      </span>
      <span className={`runtime-state ${meta.available ? "ready" : "missing"}`}>
        {meta.available ? "Ready" : "Needs setup"}
      </span>
      <span className="runtime-scope">{meta.scope || "inside Works"}</span>
      {id === "swarm" ? <span className="runtime-contract">works.swarm.v1</span> : null}
    </button>
  );
}

export function SettingsDialog({
  theme,
  density,
  pollMs,
  builder,
  writable = true,
  onSave,
  onClose,
}) {
  const providers = { ...PROVIDER_FALLBACK, ...(builder?.providers || {}) };
  const runtimes = { ...RUNTIME_FALLBACK, ...(builder?.runtimes || {}) };
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
  const [plannerProvider, setPlannerProvider] = useState(
    PLANNER_PROVIDER_ORDER.includes(builder?.planner?.provider)
      ? builder.planner.provider
      : "claudecode"
  );
  const [plannerModel, setPlannerModel] = useState(builder?.planner?.model || "");
  const [plannerCriticProvider, setPlannerCriticProvider] = useState(
    PLANNER_PROVIDER_ORDER.includes(builder?.planner?.critic_provider)
      ? builder.planner.critic_provider
      : "claudecode"
  );
  const [plannerCriticModel, setPlannerCriticModel] = useState(
    builder?.planner?.critic_model || ""
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const openjiuwen = runtime === "openjiuwen";
  const plannerModes = builder?.planner?.modes || PLANNER_MODES_FALLBACK;
  const plannerMeta = plannerModes.find((mode) => mode.id === plannerMode) || PLANNER_MODES_FALLBACK[0];
  const plannerOpen = plannerMode !== "deterministic";
  const plannerProviderMeta = providers[plannerProvider] || PROVIDER_FALLBACK.claudecode;
  const plannerCriticMeta = providers[plannerCriticProvider] || PROVIDER_FALLBACK.claudecode;
  const builderMeta = providers[provider] || PROVIDER_FALLBACK.claudecode;
  const verifierMeta = providers[separateVerifier ? verifier : provider] || provider;
  const swarm = builder?.swarm || {};
  const builderCredential = openjiuwen
    ? credentialLabel(provider, builder?.credentials?.builder, providers)
    : swarm.available
      ? "External runtime"
      : "Needs setup";
  const verifierCredential = !openjiuwen
    ? "Own challenger"
    : separateVerifier
      ? credentialLabel(verifier, builder?.credentials?.verifier, providers)
      : builder?.credentials?.builder === "ready"
        ? "Uses builder credential"
        : "Needs setup";

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await onSave({
        theme: nextTheme,
        density: nextDensity,
        pollMs: Number(nextPoll),
        repo,
        builder: {
          runtime,
          provider,
          verifier_provider: separateVerifier && verifier !== provider ? verifier : null,
          model: model.trim() || null,
          verifier_model: separateVerifier ? (verifierModel.trim() || null) : null,
          planner_mode: plannerMode,
          planner_provider: plannerMode === "deterministic" ? null : plannerProvider,
          planner_model: plannerOpen ? (plannerModel.trim() || null) : null,
          planner_critic_provider: plannerMode === "deep" ? plannerCriticProvider : null,
          planner_critic_model:
            plannerMode === "deep" ? (plannerCriticModel.trim() || null) : null,
        },
      });
    } catch (err) {
      setError(err.message || "Could not save these settings.");
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
        <section className="settings-section">
          <div className="settings-section-head">
            <div>
              <h3>Builder</h3>
              <p>First choose where the builder runs. Provider cards belong to OpenJiuwen inside Works only.</p>
            </div>
            <span className={`settings-credential ${builderCredential === "Ready" || builderCredential === "External runtime" ? "ready" : builderCredential === "Needs setup" || builderCredential === "Needs runtime" ? "missing" : ""}`}>
              {builderCredential}
            </span>
          </div>
          <div className="runtime-grid" role="radiogroup" aria-label="Builder runtime">
            {RUNTIME_ORDER.map((id) => (
              <RuntimeCard
                key={id}
                id={id}
                meta={runtimes[id] || RUNTIME_FALLBACK[id]}
                active={runtime === id}
                onSelect={setRuntime}
              />
            ))}
          </div>
          <p className="settings-note runtime-note">
            <b>Jiuwen native</b> is one agent inside Works. <b>JiuwenSwarm</b> is a separate multi-agent team outside Works.
          </p>
          {openjiuwen ? (
            <>
              <div className="settings-subhead">Provider inside Works</div>
              <div className="provider-grid" role="radiogroup" aria-label="Builder provider">
                {PROVIDER_ORDER.map((id) => (
                  <ProviderCard
                    key={id}
                    id={id}
                    meta={providers[id] || PROVIDER_FALLBACK[id]}
                    active={provider === id}
                    disabled={!writable || !(providers[id] || PROVIDER_FALLBACK[id]).available}
                    onSelect={setProvider}
                  />
                ))}
              </div>
              <ProviderSetup ids={PROVIDER_ORDER} providers={providers} />
              <label className="settings-field">
                <span>Model <em>{builderMeta.label} default</em></span>
                <ModelInput
                  id="builder-model"
                  value={model}
                  disabled={!writable}
                  onChange={(event) => setModel(event.target.value)}
                  provider={provider}
                />
              </label>
              <p className="settings-note">
                Credentials stay in the local environment. Works never stores a key in this screen or in the browser.
                {provider === "native" ? " Jiuwen native runs in the Works process and uses the same builder credential." : ""}
              </p>
            </>
          ) : (
            <div className="swarm-panel">
              <div className="swarm-panel-head">
                <b>JiuwenSwarm is a separate team, not a provider</b>
                <span className={`settings-credential ${swarm.available ? "ready" : "missing"}`}>
                  {swarm.available ? "Ready" : "Needs setup"}
                </span>
              </div>
              <p>
                It runs outside Works with its own multi-agent builder, challenger, gateway and models.
                Works sends the task through the <code>works.swarm.v1</code> adapter and records the returned
                patch, challenge and usage as evidence.
              </p>
              <p className="settings-note">{swarm.detail || "A run probes the adapter before it starts."}</p>
              {swarm.steps?.length ? (
                <details className="provider-setup" open={!swarm.available}>
                  <summary>{swarm.available ? "How this runtime works" : "Setup steps"}</summary>
                  <ul className="settings-steps">
                    {swarm.steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
              <p className="settings-note">
                JiuwenSwarm selects its own models through its gateway configuration. Works does not
                expose a model picker here because it does not run those models itself.
              </p>
            </div>
          )}
        </section>

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
                {PLANNER_PROVIDER_ORDER.map((id) => (
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
              <label className="settings-field">
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
                    {PLANNER_PROVIDER_ORDER.map((id) => (
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
                  <label className="settings-field">
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
                  {PROVIDER_ORDER.map((id) => (
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
                <label className="settings-field">
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

        {error ? <p className="settings-error" role="alert">{error}</p> : null}
        <div className="dialog-actions">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn" disabled={saving}>{saving ? "Saving..." : "Save"}</button>
        </div>
      </form>
    </Modal>
  );
}
