import { groups, riskLabel, riskTone, stateLabel, timeAgo } from "../lib/format.js";
import { Pill } from "./ui.jsx";

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
  onNew,
}) {
  const products = [...new Set(tasks.map((task) => task.product).filter(Boolean))].sort();
  const states = Object.fromEntries(groups.map(([id, , stateList]) => [id, stateList]));
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
      <header className="brand">
        <div className="mark" aria-hidden="true">W</div>
        <div className="brand-copy">
          <strong>openJiuwen Works</strong>
          <span className="preview">LOCAL FACTORY</span>
        </div>
      </header>

      <div className="search">
        <input
          type="search"
          placeholder="Search tasks"
          aria-label="Search tasks"
          autoComplete="off"
          value={query}
          onChange={(event) => onQuery(event.target.value)}
        />
        <kbd>/</kbd>
      </div>

      <div className="filters" role="group" aria-label="Filter tasks">
        {[["all", "All"], ["needs", "Needs you"], ["working", "In progress"], ["done", "Done"]].map(([id, label]) => (
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
        <select aria-label="Filter by product" value={productFilter} onChange={(event) => onProductFilter(event.target.value)}>
          <option value="">All products</option>
          {products.map((product) => (
            <option key={product} value={product}>{product}</option>
          ))}
        </select>
        <select aria-label="Filter by source" value={sourceFilter} onChange={(event) => onSourceFilter(event.target.value)}>
          <option value="">All sources</option>
          <option value="manual">A person</option>
          <option value="tracker">Tracker</option>
          <option value="detector">Monitoring</option>
        </select>
      </div>

      {writable ? (
        <button className="btn report-btn" type="button" onClick={onNew}>+ New task</button>
      ) : null}

      <div className="task-list" aria-live="polite">
        {!visible.length ? <p className="muted small" style={{ padding: "16px 12px" }}>No tasks match.</p> : null}
        {groups.map(([id, label, stateList]) => {
          const rows = visible.filter((task) => stateList.includes(task.state));
          if (!rows.length) return null;
          return (
            <div key={id}>
              <div className="group-label">{label}<span>{rows.length}</span></div>
              {rows.map((task) => {
                const active = task.id === selected;
                const risk = task.risk && task.risk !== "low"
                  ? <Pill tone={riskTone(task.risk)}>{riskLabel(task.risk)}</Pill>
                  : null;
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
                      <span className="task-meta">{task.product} · {stateLabel(task.state)}</span>
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
    </aside>
  );
}
