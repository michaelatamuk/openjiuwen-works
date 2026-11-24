import { useMemo, useRef, useState } from "react";
import { api } from "../../lib/api.js";
import { Modal } from "../../ui/Modal.jsx";

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
