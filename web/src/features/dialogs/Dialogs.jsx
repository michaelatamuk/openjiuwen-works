import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../lib/api.js";
import { fmtMs, fmtUsd, shortSha } from "../../lib/format.js";
import { Pill, Table } from "../../ui/primitives.jsx";

function Modal({ children, onClose, className = "" }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => {
      if (ref.current?.open) ref.current.close();
    };
  }, []);
  return (
    <dialog ref={ref} className={className} onCancel={(event) => { event.preventDefault(); onClose(); }} onClose={onClose}>
      {children}
    </dialog>
  );
}

function parsePrompt(text, products = []) {
  const clean = String(text || "").trim();
  const draft = { ref: "", repo: "", product: "", title: "" };
  if (!clean) return draft;
  let match = clean.match(/https?:\/\/github\.com\/([\w.-]+)\/([\w.-]+)\/(?:issues|pull)\/(\d+)/i);
  if (match) {
    draft.repo = `${match[1]}/${match[2]}`;
    draft.ref = `${match[1]}/${match[2]}#${match[3]}`;
  }
  if (!draft.ref) {
    match = clean.match(/\b([\w.-]+)\/([\w.-]+)#(\d+)\b/);
    if (match) {
      draft.repo = draft.repo || `${match[1]}/${match[2]}`;
      draft.ref = `${match[1]}/${match[2]}#${match[3]}`;
    }
  }
  if (!draft.ref) {
    match = clean.match(/\b([A-Z][A-Z0-9]{1,9}-\d+)\b/);
    if (match) draft.ref = match[1];
  }
  if (!draft.repo) {
    match = clean.match(/\b[A-Za-z]:\\[^\s"'<>]+/);
    if (match) draft.repo = match[0].replace(/[.,;)]+$/, "");
  }
  const escape = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  draft.product = products.find((product) =>
    new RegExp(`\\b${escape(product)}\\b`, "i").test(clean)
  ) || "";
  const firstLine = clean.split(/\r?\n/).map((line) => line.trim()).find(Boolean) || clean;
  let title = firstLine.replace(/\s+/g, " ").replace(/\s+\bin\b\s+[A-Za-z]:\\.*$/i, "").trim();
  if (!title || /^https?:\/\/\S+$/i.test(title)) title = draft.ref ? `Fix ${draft.ref}` : "";
  draft.title = title.slice(0, 140);
  return draft;
}

function draftRows(draft) {
  return [["Reference", draft.ref], ["Product", draft.product], ["Repository", draft.repo], ["Title", draft.title]]
    .filter(([, value]) => value);
}

export function NewTaskDialog({ products, onClose, onCreated, onToast }) {
  const [prompt, setPrompt] = useState("");
  const [product, setProduct] = useState("openjiuwen");
  const [repo, setRepo] = useState(localStorage.getItem("works.repo") || "");
  const [ref, setRef] = useState("");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("manual");
  const [taskKind, setTaskKind] = useState("fix");
  const [flow, setFlow] = useState("fix-issue");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const touched = useRef(new Set());
  const draft = useMemo(() => parsePrompt(prompt, products), [prompt, products]);
  const rows = draftRows(draft);

  function sync() {
    const set = (name, value, current, setter) => {
      if (touched.current.has(name)) return;
      if (value) setter(value);
      else if (name === "ref" || name === "title") setter("");
      return current;
    };
    set("ref", draft.ref, ref, setRef);
    set("repo", draft.repo, repo, setRepo);
    set("product", draft.product, product, setProduct);
    set("title", draft.title, title, setTitle);
  }

  function openDetails() {
    setDetailsOpen(true);
    sync();
  }

  function useDraft() {
    if (draft.ref) setRef(draft.ref);
    if (draft.repo) setRepo(draft.repo);
    if (draft.product) setProduct(draft.product);
    if (draft.title) setTitle(draft.title);
    setDetailsOpen(true);
    onToast("Draft applied to the fields.");
  }

  async function submit(event) {
    event.preventDefault();
    sync();
    const valueFor = (name, current) => touched.current.has(name) ? current : draft[name] || current;
    const finalRef = valueFor("ref", ref).trim();
    const finalTitle = valueFor("title", title).trim();
    if (!finalRef || !finalTitle) {
      setDetailsOpen(true);
      onToast("Add a reference and a title under Details.");
      return;
    }
    setBusy(true);
    try {
      const result = await api("/api/tasks", {
        method: "POST",
        headers: { "X-Works-Write": "1" },
        body: {
          repo: valueFor("repo", repo).trim(),
          product: valueFor("product", product).trim(),
          ref: finalRef,
          title: finalTitle,
          kind,
          task_kind: taskKind,
          flow,
        },
      });
      const finalRepo = valueFor("repo", repo).trim();
      if (finalRepo) localStorage.setItem("works.repo", finalRepo);
      onToast(result.created ? `Created ${result.task.id}. It is queued.` : `${result.task.id} already existed.`);
      onCreated(result.task.id);
    } catch (error) {
      onToast(`Create failed: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} className="report-dialog">
      <h2>New task</h2>
      <form onSubmit={submit}>
        <div className="report-composer">
          <textarea
            rows={3}
            value={prompt}
            placeholder="What should Mira work on? Paste a bug, an issue link or a few lines."
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) event.currentTarget.form?.requestSubmit();
            }}
          />
          <div className="report-composer-actions">
            <span className="muted small">Nothing is created or started until you press Create task.</span>
            <button type="button" className="btn ghost" onClick={useDraft} disabled={!rows.length}>Use draft</button>
          </div>
        </div>
        {rows.length ? (
          <div className="report-draft">
            <div className="report-draft-head">
              <span className="eyebrow">Draft from your text</span>
              <span className="muted small">local, no model</span>
            </div>
            <div className="report-draft-rows">
              {rows.map(([label, value]) => <span className="chip" key={label}>{label}: {value}</span>)}
            </div>
          </div>
        ) : null}
        <details className="report-details" open={detailsOpen} onToggle={(event) => { if (event.currentTarget.open) openDetails(); }}>
          <summary>Details <span className="muted small">product, repository, reference, title</span></summary>
          <div className="report-fields">
            <label>Product
              <input value={product} list="product-list" onChange={(event) => { touched.current.add("product"); setProduct(event.target.value); }} />
              <datalist id="product-list">{products.map((item) => <option key={item} value={item} />)}</datalist>
            </label>
            <label>Repository <span className="small muted">(optional when the product is mapped)</span>
              <input value={repo} placeholder="C:\path\to\repo" onChange={(event) => { touched.current.add("repo"); setRepo(event.target.value); }} />
            </label>
            <label>Reference
              <input value={ref} placeholder="GH-123, PROJ-7 or owner/repo#12" onChange={(event) => { touched.current.add("ref"); setRef(event.target.value); }} />
            </label>
            <label>Title
              <input value={title} placeholder="What went wrong?" onChange={(event) => { touched.current.add("title"); setTitle(event.target.value); }} />
            </label>
            <div className="form-row">
              <label>Source
                <select value={kind} onChange={(event) => setKind(event.target.value)}>
                  <option value="manual">A person</option>
                  <option value="tracker">Tracker</option>
                  <option value="detector">Monitoring</option>
                </select>
              </label>
              <label>Task kind
                <select value={taskKind} onChange={(event) => setTaskKind(event.target.value)}>
                  <option value="fix">Fix</option>
                  <option value="check-change">Check a change</option>
                </select>
              </label>
              <label>Flow
                <input value={flow} onChange={(event) => setFlow(event.target.value)} />
              </label>
            </div>
          </div>
        </details>
        <p className="small muted">Draft fields reads only the text you typed. This adds one queued task; it never starts a run or approves a gate.</p>
        <div className="dialog-actions">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn" disabled={busy}>{busy ? "Creating…" : "Create task"}</button>
        </div>
      </form>
    </Modal>
  );
}

export function ImportDialog({ products, detectors, onClose, onImported, onToast }) {
  const [source, setSource] = useState("github");
  const [repository, setRepository] = useState("");
  const [label, setLabel] = useState("bug");
  const [url, setUrl] = useState("");
  const [jql, setJql] = useState("");
  const [detector, setDetector] = useState(detectors[0]?.name || "");
  const [product, setProduct] = useState(products[0] || "openjiuwen");
  const [repo, setRepo] = useState(localStorage.getItem("works.repo") || "");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const body = { source, product, repo };
      if (source === "github") { body.repository = repository; body.label = label; }
      if (source === "jira") { body.url = url; body.jql = jql; }
      if (source === "detector") { body.name = detector; }
      const result = await api("/api/sources", { method: "POST", headers: { "X-Works-Write": "1" }, body });
      onToast(`${result.imported ?? 0} task(s) imported.`);
      onImported();
    } catch (error) {
      onToast(`Import failed: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose}>
      <h2>Import signals</h2>
      <form onSubmit={submit}>
        <label>Source
          <select value={source} onChange={(event) => setSource(event.target.value)}>
            <option value="github">GitHub Issues</option>
            <option value="jira">Jira</option>
            <option value="detector">Detector</option>
          </select>
        </label>
        {source === "github" ? (
          <div className="form-row">
            <label>Repository <input value={repository} placeholder="owner/name" onChange={(event) => setRepository(event.target.value)} /></label>
            <label>Label <input value={label} placeholder="bug" onChange={(event) => setLabel(event.target.value)} /></label>
          </div>
        ) : null}
        {source === "jira" ? (
          <div className="form-row">
            <label>Jira URL <input value={url} placeholder="https://jira.example" onChange={(event) => setUrl(event.target.value)} /></label>
            <label>JQL <input value={jql} placeholder="project = FIRE AND status = Open" onChange={(event) => setJql(event.target.value)} /></label>
          </div>
        ) : null}
        {source === "detector" ? (
          <label>Detector
            <select value={detector} onChange={(event) => setDetector(event.target.value)}>
              {detectors.map((item) => <option key={item.name} value={item.name}>{item.name} · {item.product}</option>)}
            </select>
          </label>
        ) : null}
        <div className="form-row">
          <label>Product
            <input value={product} list="product-list" onChange={(event) => setProduct(event.target.value)} />
            <datalist id="product-list">{products.map((item) => <option key={item} value={item} />)}</datalist>
          </label>
          <label>Repository override <input value={repo} placeholder="(optional)" onChange={(event) => setRepo(event.target.value)} /></label>
        </div>
        <p className="small muted">Imports only firing or open signals. Duplicates return the same task.</p>
        <div className="dialog-actions">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn" disabled={busy}>{busy ? "Importing…" : "Import"}</button>
        </div>
      </form>
    </Modal>
  );
}

export function FactoryDialog({ onClose }) {
  const [metrics, setMetrics] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([api("/api/metrics"), api("/api/ledger")])
      .then(([m, l]) => { setMetrics(m.metrics || {}); setLedger((l.rows || []).slice().reverse().slice(0, 30)); })
      .catch((exc) => setError(exc.message));
  }, []);
  const cards = metrics ? [
    ["Tasks", metrics.tasks], ["Proved", metrics.proved], ["Blocked", metrics.blocked],
    ["Human touches", metrics.human_touches], ["Runs without human", metrics.runs_without_human],
    ["Median wall", fmtMs(metrics.median_duration_ms ?? 0)], ["Tokens", metrics.tokens], ["USD", fmtUsd(metrics.usd)],
  ] : [];
  return (
    <Modal onClose={onClose} className="factory-dialog">
      <h2>Factory</h2>
      {error ? <p className="bad small">{error}</p> : null}
      {!metrics && !error ? <p className="muted small">Loading factory metrics…</p> : null}
      {metrics ? (
        <>
          <div className="metrics-grid">
            {cards.map(([label, value]) => (
              <div className="metric" key={label}><span>{label}</span><strong>{value}</strong></div>
            ))}
          </div>
          <h3 className="factory-subtitle">Ledger</h3>
          <Table
            columns={["Time", "Task", "State", "Verdict", "Tokens", "USD"]}
            rows={ledger.map((row) => [
              new Date(row.ts).toLocaleString(), <span className="mono">{row.task_id}</span>, row.state,
              row.verdict || "—", row.tokens ?? 0, fmtUsd(row.usd),
            ])}
          />
        </>
      ) : null}
      <div className="dialog-actions"><button type="button" className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}

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

export function RunDialog({ detail, onClose }) {
  const run = detail.run || {};
  const evidence = detail.evidence || {};
  const verdict = evidence.verdict || {};
  const lines = [
    ["Run", run.run_id || "—"], ["Flow", run.flow || "—"], ["Base commit", run.base_commit || "—"],
    ["Checks SHA", run.checks_sha || "-"], ["Proof SHA", evidence.proof_sha256 || "-"],
    ["Plan", run.plan_id || "-"], ["Plan hash", run.plan_hash ? shortSha(run.plan_hash) : "-"],
    ["Planner", run.planner_mode || "-"],
    ["Verdict", verdict.allow ? "allow" : evidence.verdict ? "block" : "-"],
    ["Risk", evidence.risk?.level || "—"], ["Files", (evidence.files_changed || []).join(", ") || "—"],
    ["Not tested", (evidence.not_tested || []).join(", ") || "none recorded"],
    ["Tokens", evidence.tokens ?? 0], ["USD", fmtUsd(evidence.usd ?? 0)],
  ];
  return (
    <Modal onClose={onClose}>
      <h2>Run</h2>
      <dl className="kv">
        {lines.map(([label, value]) => (
          <Fragment key={label}><dt>{label}</dt><dd className="mono">{value}</dd></Fragment>
        ))}
      </dl>
      <div className="dialog-actions"><button type="button" className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}

export function CompareDialog({ detail, onClose }) {
  const runs = (detail.runs || []).slice().reverse();
  const [a, setA] = useState(runs[0]?.run_id || "");
  const [b, setB] = useState(runs[1]?.run_id || runs[0]?.run_id || "");
  const find = (id) => runs.find((run) => run.run_id === id);
  const first = find(a);
  const second = find(b);
  const fields = [
    ["State", "state", (value) => value],
    ["Base commit", "base_commit", (value) => <span className="mono">{shortSha(value)}</span>],
    ["Proof SHA", "proof_sha256", (value) => <span className="mono">{shortSha(value)}</span>],
    ["Verdict", "verdict", (value) => <Pill tone={value === "allow" ? "green" : "red"}>{value}</Pill>],
    ["Risk", "risk", (value) => value],
    ["Files", "files", (value) => (value || []).join(", ") || "—"],
    ["Not tested", "not_tested", (value) => (value || []).join(", ") || "none"],
    ["Tokens", "tokens", (value) => value],
    ["USD", "usd", (value) => fmtUsd(value)],
    ["Wall", "duration_ms", (value) => fmtMs(value)],
    ["Delivered", "delivered", (value) => value ? "yes" : "no"],
    ["Confirmed", "confirmed", (value) => value ? "pass" : "no"],
  ];
  return (
    <Modal onClose={onClose}>
      <h2>Compare runs</h2>
      {runs.length < 2 ? <p className="muted small">Comparison needs at least two finished runs. This task has {runs.length}.</p> : (
        <>
          <div className="form-row">
            <label>Run A <select value={a} onChange={(event) => setA(event.target.value)}>{runs.map((run) => <option key={run.run_id} value={run.run_id}>{run.run_id} · {run.verdict}</option>)}</select></label>
            <label>Run B <select value={b} onChange={(event) => setB(event.target.value)}>{runs.map((run) => <option key={run.run_id} value={run.run_id}>{run.run_id} · {run.verdict}</option>)}</select></label>
          </div>
          {first && second ? (
            <Table
              columns={["Field", first.run_id, second.run_id]}
              rows={fields.map(([label, key, render]) => [label, render(first[key]), render(second[key])])}
            />
          ) : null}
        </>
      )}
      <div className="dialog-actions"><button type="button" className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}

export function Lightbox({ image, onClose }) {
  if (!image) return null;
  return (
    <Modal onClose={onClose}>
      <h2 className="small muted">Artifact</h2>
      <img className="lightbox-image" src={image.url} alt={image.alt || "artifact"} />
      <div className="dialog-actions"><button type="button" className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}

export function EventDialog({ event, onClose }) {
  if (!event) return null;
  return (
    <Modal onClose={onClose}>
      <h2>Event</h2>
      <pre className="run-dialog-body">{JSON.stringify(event, null, 2)}</pre>
      <div className="dialog-actions"><button type="button" className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}

export function Palette({ tasks, onSelect, onAction, onClose, writable = false }) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const actions = [
    ...(writable ? [["New task", () => onAction("new")], ["Import signals", () => onAction("import")]] : []),
    ["Factory metrics", () => onAction("factory")],
    ["Settings", () => onAction("settings")],
    ["Toggle theme", () => onAction("theme")],
    ["Toggle density", () => onAction("density")],
    ["Refresh now", () => onAction("refresh")],
    ["Keyboard help", () => onAction("help")],
  ].filter(([label]) => !needle || label.toLowerCase().includes(needle));
  const rows = tasks.filter((task) => !needle || [task.title, task.id, task.product].join(" ").toLowerCase().includes(needle)).slice(0, 12);
  return (
    <Modal onClose={onClose}>
      <h2>Jump to</h2>
      <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Task, action or view" aria-label="Command palette search" />
      <div className="palette-results">
        {actions.map(([label, run]) => <button key={label} type="button" className="palette-row" onClick={() => run()}>{label}</button>)}
        {rows.map((task) => (
          <button key={task.id} type="button" className="palette-row" onClick={() => { onSelect(task.id); onClose(); }}>
            <span>{task.title || task.id}</span><span className="muted small">{task.product} · {task.state}</span>
          </button>
        ))}
      </div>
    </Modal>
  );
}

export function HelpDialog({ onClose }) {
  return (
    <Modal onClose={onClose}>
      <h2>Keyboard</h2>
      <dl className="kv">
        <dt>/</dt><dd>Search tasks</dd>
        <dt>Ctrl K</dt><dd>Command palette</dd>
        <dt>j / k</dt><dd>Next / previous task</dd>
        <dt>t</dt><dd>Toggle theme</dd>
        <dt>c</dt><dd>Present mode in Story</dd>
        <dt>?</dt><dd>This help</dd>
        <dt>Esc</dt><dd>Close a dialog or Present mode</dd>
        <dt>Ctrl Enter</dt><dd>Send in the worklog</dd>
      </dl>
      <div className="dialog-actions"><button type="button" className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}
