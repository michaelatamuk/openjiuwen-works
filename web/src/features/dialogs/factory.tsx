import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../../api/client";
import { fmtMs, fmtUsd } from "../../lib/format.js";
import { Table } from "../../ui/primitives";
import { Modal } from "../../ui/Modal";

export type FactoryMetrics = {
  tasks?: number;
  proved?: number;
  blocked?: number;
  human_touches?: number;
  runs_without_human?: number;
  median_duration_ms?: number;
  tokens?: number;
  usd?: number;
};

export type FactoryLedgerRow = {
  ts?: string;
  task_id?: string;
  state?: string;
  verdict?: string | null;
  tokens?: number | null;
  usd?: number | null;
};

export type FactoryDialogProps = {
  onClose: () => void;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function metricsFrom(value: unknown): FactoryMetrics {
  if (!isRecord(value)) return {};
  return {
    tasks: numberValue(value.tasks),
    proved: numberValue(value.proved),
    blocked: numberValue(value.blocked),
    human_touches: numberValue(value.human_touches),
    runs_without_human: numberValue(value.runs_without_human),
    median_duration_ms: numberValue(value.median_duration_ms),
    tokens: numberValue(value.tokens),
    usd: numberValue(value.usd),
  };
}

function ledgerRows(value: unknown): FactoryLedgerRow[] {
  const rows = isRecord(value) && Array.isArray(value.rows) ? value.rows : [];
  return rows.flatMap((item) => {
    if (!isRecord(item)) return [];
    return [{
      ts: stringValue(item.ts),
      task_id: stringValue(item.task_id),
      state: stringValue(item.state),
      verdict: typeof item.verdict === "string" ? item.verdict : null,
      tokens: numberValue(item.tokens) ?? null,
      usd: numberValue(item.usd) ?? null,
    }];
  });
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function FactoryDialog({ onClose }: FactoryDialogProps) {
  const [metrics, setMetrics] = useState<FactoryMetrics | null>(null);
  const [ledger, setLedger] = useState<FactoryLedgerRow[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([api.metrics(), api.ledger()])
      .then(([m, l]) => {
        setMetrics(metricsFrom(m.metrics));
        setLedger(ledgerRows(l).slice().reverse().slice(0, 30));
      })
      .catch((error: unknown) => setError(errorMessage(error)));
  }, []);
  const cards: Array<[string, ReactNode]> = metrics ? [
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
              new Date(row.ts ?? "").toLocaleString(), <span className="mono">{row.task_id}</span>, row.state,
              row.verdict || "—", row.tokens ?? 0, fmtUsd(row.usd),
            ])}
          />
        </>
      ) : null}
      <div className="dialog-actions"><button type="button" className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}
