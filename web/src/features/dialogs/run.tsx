import { Fragment, useState } from "react";
import type { ReactNode } from "react";

import { fmtMs, fmtUsd, shortSha } from "../../lib/format.js";
import { Pill, Table } from "../../ui/primitives";
import { Modal } from "../../ui/Modal";

export type RunDialogRun = {
  run_id?: string;
  flow?: string;
  base_commit?: string | null;
  checks_sha?: string | null;
  plan_id?: string | null;
  plan_hash?: string | null;
  planner_mode?: string | null;
};

export type RunDialogEvidence = {
  proof_sha256?: string | null;
  verdict?: { allow?: boolean } | null;
  risk?: { level?: string | null } | null;
  files_changed?: string[];
  not_tested?: string[];
  tokens?: number | null;
  usd?: number | null;
};

export type RunDialogDetail = {
  run?: RunDialogRun | null;
  evidence?: RunDialogEvidence | null;
};

export type RunDialogProps = {
  detail: RunDialogDetail | null;
  onClose: () => void;
};

export type CompareRun = {
  run_id?: string;
  state?: string | null;
  base_commit?: string | null;
  proof_sha256?: string | null;
  verdict?: string | null;
  risk?: string | null;
  files?: string[];
  not_tested?: string[];
  tokens?: number | null;
  usd?: number | null;
  duration_ms?: number | null;
  delivered?: boolean | null;
  confirmed?: boolean | null;
};

export type CompareDialogDetail = {
  runs?: CompareRun[] | null;
};

export type CompareDialogProps = {
  detail: CompareDialogDetail | null;
  onClose: () => void;
};

type CompareCell = string | number | boolean | string[] | null | undefined;

type CompareField = [string, keyof CompareRun, (value: CompareCell) => ReactNode];

function text(value: CompareCell): string {
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  return "";
}

function list(value: CompareCell, fallback: string): string {
  return (Array.isArray(value) ? value.join(", ") : "") || fallback;
}

export function RunDialog({ detail, onClose }: RunDialogProps) {
  if (!detail) return null;
  const run = detail.run || {};
  const evidence = detail.evidence || {};
  const verdict = evidence.verdict || {};
  const lines: Array<[string, ReactNode]> = [
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

export function CompareDialog({ detail, onClose }: CompareDialogProps) {
  const runs = (detail?.runs || []).slice().reverse();
  const [a, setA] = useState(runs[0]?.run_id || "");
  const [b, setB] = useState(runs[1]?.run_id || runs[0]?.run_id || "");
  if (!detail) return null;
  const find = (id: string) => runs.find((run) => run.run_id === id);
  const first = find(a);
  const second = find(b);
  const fields: CompareField[] = [
    ["State", "state", (value) => text(value)],
    ["Base commit", "base_commit", (value) => <span className="mono">{shortSha(value)}</span>],
    ["Proof SHA", "proof_sha256", (value) => <span className="mono">{shortSha(value)}</span>],
    ["Verdict", "verdict", (value) => <Pill tone={value === "allow" ? "green" : "red"}>{text(value)}</Pill>],
    ["Risk", "risk", (value) => text(value)],
    ["Files", "files", (value) => list(value, "—")],
    ["Not tested", "not_tested", (value) => list(value, "none")],
    ["Tokens", "tokens", (value) => text(value)],
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
