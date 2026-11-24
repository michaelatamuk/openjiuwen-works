import { RuntimeCard, ModelInput, ProviderCard, ProviderSetup } from "./cards.jsx";
import {
  PROVIDER_FALLBACK,
  PROVIDER_ORDER,
  RUNTIME_FALLBACK,
  RUNTIME_ORDER,
} from "./options.js";

export function BuilderSection({
  writable,
  openjiuwen,
  builderCredential,
  runtime,
  onRuntime,
  runtimes,
  provider,
  onProvider,
  providers,
  model,
  onModel,
  builderMeta,
  swarm,
}) {
  return (
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
              onSelect={onRuntime}
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
                  onSelect={onProvider}
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
                onChange={(event) => onModel(event.target.value)}
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
  );
}
