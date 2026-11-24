import { useState } from "react";
import { api, waitForJob } from "../../api/client";
import { Modal } from "../../ui/Modal.jsx";

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
      const accepted = await api.sources(body);
      const job = await waitForJob(accepted.job.id);
      if (job.status !== "succeeded") throw new Error(job.error || "import failed");
      const result = job.result || {};
      onToast(`${result.created ?? 0} task(s) imported.`);
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
