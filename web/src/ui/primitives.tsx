import type { ReactNode } from "react";

import { aiText } from "../lib/format.js";

export type PillProps = {
  tone?: string;
  children?: ReactNode;
};

export function Pill({ tone = "", children }: PillProps) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

export type CardProps = {
  title?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
};

export function Card({ title, actions, children, className = "" }: CardProps) {
  return (
    <section className={`card ${className}`}>
      {title || actions ? (
        <header className="card-head">
          <h2>{title}</h2>
          {actions ? <div className="card-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="card-body">{children}</div>
    </section>
  );
}

export type TableProps = {
  columns: Array<string | undefined>;
  rows: ReactNode[][];
  className?: string;
};

export function Table({ columns, rows, className = "" }: TableProps) {
  return (
    <div className="table-wrap">
      <table className={`table ${className}`}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export type AiTextProps = {
  text?: string | null;
};

export function AiText({ text }: AiTextProps) {
  return (
    <>
      {aiText(text).map((part) => {
        if (part.type === "strong") return <strong key={part.key}>{part.value}</strong>;
        if (part.type === "code") return <code key={part.key}>{part.value}</code>;
        return <span key={part.key}>{part.value}</span>;
      })}
    </>
  );
}

export function EmptyProof() {
  return (
    <div className="card">
      <div className="card-body">
        <div className="empty" style={{ margin: "10px auto 22px" }}>
          <img src="/mira.svg" alt="" width="64" height="64" />
          <h2>No proof yet</h2>
          <p>This task has not produced a run. The queue is the truth; the proof appears when a run finishes.</p>
        </div>
      </div>
    </div>
  );
}

export type ToastProps = {
  message?: string | null;
};

export function Toast({ message }: ToastProps) {
  return (
    <div id="toast" className={message ? "show" : ""} role="status" aria-live="polite">
      {message || ""}
    </div>
  );
}
