import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { fmtMs, fmtUsd } from "../../lib/format.js";
import { Table } from "../../ui/primitives.jsx";
import { Modal } from "../../ui/Modal.jsx";

export function FactoryDialog({ onClose }) {
  const [metrics, setMetrics] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([api.metrics(), api.ledger()])
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
