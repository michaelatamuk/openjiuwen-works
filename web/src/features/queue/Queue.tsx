import type { ChangeEvent } from "react";

import { groups, riskLabel, riskTone, stateLabel, timeAgo } from "../../lib/format.js";
import type { Inbox } from "../../api/client";
import { Pill } from "../../ui/primitives";

export type QueueTask = {
  id: string;
  state: string;
  title?: string;
  product?: string;
  source?: string;
  flow?: string;
  risk?: string;
  updated_at?: string;
};

export type QueueProps = {
  tasks: QueueTask[];
  selected: string | null;
  onSelect: (id: string) => void;
  filter: string;
  onFilter: (id: string) => void;
  productFilter: string;
  onProductFilter: (value: string) => void;
  sourceFilter: string;
  onSourceFilter: (value: string) => void;
  query: string;
  onQuery: (value: string) => void;
  writable: boolean;
  inbox: Inbox | null;
  onMerge: (taskId: string, into: string) => void;
  onNew: () => void;
};

const GROUPS = groups as Array<[string, string, string[]]>;

export function Queue({
  tasks,
  selected,
  onSelect,
  filter,
  onFilter,
  productFilter,
  onProductFilter,
  sourceFilter,
  onSourceFilter,
  query,
  onQuery,
  writable,
  inbox,
  onMerge,
  onNew,
}: QueueProps) {
  const products = [...new Set(tasks.map((task) => task.product).filter(Boolean))].sort();
  const states: Record<string, string[]> = Object.fromEntries(
    GROUPS.map(([id, , stateList]) => [id, stateList]),
  );
  const needle = query.trim().toLowerCase();
  const visible = tasks.filter((task) => {
    if (filter !== "all" && !(states[filter] || []).includes(task.state)) return false;
    if (productFilter && task.product !== productFilter) return false;
    if (sourceFilter && String(task.source || "").split(":")[0] !== sourceFilter) return false;
    if (!needle) return true;
    return [task.title, task.id, task.source, task.product, task.flow, stateLabel(task.state)]
      .join(" ")
      .toLowerCase()
      .includes(needle);
  });

  return (
    <aside className="sidebar" aria-label="Queue">
      <div className="search">
        <input
          type="search"
          placeholder="Search tasks"
          aria-label="Search tasks"
          autoComplete="off"
          value={query}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onQuery(event.target.value)}
        />
        <kbd>/</kbd>
      </div>

      <div className="filters" role="group" aria-label="Filter tasks">
        {[
          ["all", "All"],
          ["needs", "Needs you"],
          ["working", "In progress"],
          ["done", "Done"],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`filter ${filter === id ? "active" : ""}`}
            onClick={() => onFilter(id)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="filter-selects">
        <select
          aria-label="Filter by product"
          value={productFilter}
          onChange={(event: ChangeEvent<HTMLSelectElement>) => onProductFilter(event.target.value)}
        >
          <option value="">All products</option>
          {products.map((product) => (
            <option key={product} value={product}>
              {product}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by source"
          value={sourceFilter}
          onChange={(event: ChangeEvent<HTMLSelectElement>) => onSourceFilter(event.target.value)}
        >
          <option value="">All sources</option>
          <option value="manual">A person</option>
          <option value="tracker">Tracker</option>
          <option value="detector">Monitoring</option>
        </select>
      </div>

      {writable ? (
        <button className="btn report-btn" type="button" onClick={onNew}>
          + New task
        </button>
      ) : null}

      {inbox && inbox.gates?.length ? (
        <section className="inbox" aria-label="Waiting for your decision">
          <h2>Waiting for you</h2>
          {inbox.gates.slice(0, 3).map((gate) => (
            <div className="inbox-row" key={gate.task_id}>
              <button className="btn ghost" type="button" onClick={() => onSelect(gate.task_id)}>
                {gate.title}
              </button>
              {gate.overdue ? (
                <Pill tone="amber">overdue</Pill>
              ) : (
                <span className="small muted">{gate.waiting_hours ?? 0}h</span>
              )}
            </div>
          ))}
        </section>
      ) : null}

      {inbox && inbox.duplicates.length ? (
        <section className="inbox" aria-label="Possible duplicates">
          <h2>Possible duplicates</h2>
          {inbox.duplicates.slice(0, 3).map((group) => (
            <div className="inbox-row" key={group.key}>
              <span className="small" title={group.tasks[0].title}>
                {group.tasks[0].title}
              </span>
              <button
                className="btn"
                type="button"
                disabled={!writable}
                onClick={() => onMerge(group.tasks[1].id, group.tasks[0].id)}
              >
                Merge
              </button>
            </div>
          ))}
        </section>
      ) : null}

      <div className="task-list" aria-live="polite">
        {!visible.length ? (
          <p className="muted small" style={{ padding: "16px 12px" }}>
            No tasks match.
          </p>
        ) : null}
        {GROUPS.map(([id, label, stateList]) => {
          const rows = visible.filter((task) => stateList.includes(task.state));
          if (!rows.length) return null;
          return (
            <div key={id}>
              <div className="group-label">
                {label}
                <span>{rows.length}</span>
              </div>
              {rows.map((task) => {
                const active = task.id === selected;
                const risk =
                  task.risk && task.risk !== "low" ? (
                    <Pill tone={riskTone(task.risk)}>{riskLabel(task.risk)}</Pill>
                  ) : null;
                return (
                  <button
                    key={task.id}
                    type="button"
                    className={`task ${active ? "active" : ""}`}
                    aria-current={active ? "true" : undefined}
                    onClick={() => onSelect(task.id)}
                  >
                    <span className={`product-mark ${task.state}`} aria-hidden="true">
                      {(task.product || "?")[0]}
                    </span>
                    <span className="task-main">
                      <span className="task-title">{task.title || `Task ${task.id}`}</span>
                      <span className="task-meta">
                        {task.product} · {stateLabel(task.state)}
                      </span>
                    </span>
                    <span className="task-side">
                      {risk}
                      <span className="time">{timeAgo(task.updated_at)}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
      <footer className="sidebar-foot">
        <span className={`live-dot ${writable ? "on" : ""}`} />
        {writable ? "Local / write" : "Local / read-only"}
      </footer>
    </aside>
  );
}
