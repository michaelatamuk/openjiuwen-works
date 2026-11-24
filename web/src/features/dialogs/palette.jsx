import { useState } from "react";
import { Modal } from "../../ui/Modal.jsx";

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
