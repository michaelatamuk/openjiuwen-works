import type { ChangeEvent } from "react";

import { MODEL_SUGGESTIONS, PROVIDER_FALLBACK, PROVIDER_LETTERS } from "./options";
import type { PlannerModeMeta, ProviderCatalog, ProviderMeta, RuntimeMeta } from "./types";

export type ProviderCardProps = {
  id: string;
  meta: ProviderMeta;
  active: boolean;
  disabled?: boolean;
  onSelect: (id: string) => void;
};

function ProviderCard({ id, meta, active, disabled, onSelect }: ProviderCardProps) {
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

export type ModelInputProps = {
  id: string;
  value: string;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
  disabled?: boolean;
  provider: string;
  placeholder?: string;
};

function ModelInput({ id, value, onChange, disabled, provider, placeholder = "Provider default" }: ModelInputProps) {
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
        {(MODEL_SUGGESTIONS[provider] || []).map((model: string) => (
          <option key={model} value={model} />
        ))}
      </datalist>
    </>
  );
}

export type ProviderSetupProps = {
  ids: string[];
  providers: ProviderCatalog;
};

function ProviderSetup({ ids, providers }: ProviderSetupProps) {
  const missing = ids.filter((id) => !(providers[id] || PROVIDER_FALLBACK[id])?.available);
  if (!missing.length) return null;
  return (
    <details className="provider-setup" open>
      <summary>Setup for unavailable providers</summary>
      {missing.map((id) => {
        const meta: ProviderMeta = providers[id] || PROVIDER_FALLBACK[id];
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

export type PlannerModeCardProps = {
  id: string;
  meta: PlannerModeMeta;
  active: boolean;
  onSelect: (id: string) => void;
};

function PlannerModeCard({ id, meta, active, onSelect }: PlannerModeCardProps) {
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

export type RuntimeCardProps = {
  id: string;
  meta: RuntimeMeta;
  active: boolean;
  onSelect: (id: string) => void;
};

function RuntimeCard({ id, meta, active, onSelect }: RuntimeCardProps) {
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

export { ModelInput, PlannerModeCard, ProviderCard, ProviderSetup, RuntimeCard };
