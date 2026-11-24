import { roleLabel } from "../../lib/format.js";
import type { ThreadMessage } from "./types";

export type ReviewGroupProps = {
  items: ThreadMessage[];
};

const ROLE_LABELS = roleLabel as Record<string, string>;

function ReviewGroup({ items }: ReviewGroupProps) {
  const stances = items.map((item) => item.stance).filter(Boolean);
  const concern = stances.includes("concern") || stances.includes("block");
  const agents = new Set(items.map((item) => item.role)).size;
  return (
    <details className="cl-review">
      <summary>
        <span className="cl-review-title">Review</span>
        <span className="cl-review-meta">
          {agents} agent{agents === 1 ? "" : "s"} · {concern ? "has a concern" : "all support"}
        </span>
        <span className="cl-ai-tag">AI</span>
      </summary>
      <div className="cl-review-body">
        {items.map((item) => (
          <div className="cl-review-row" key={item.seq}>
            <div className="cl-review-head">
              <b>{ROLE_LABELS[item.role ?? ""] || item.role}</b>
              {item.stance ? <span className={`cl-stance ${item.stance}`}>{item.stance}</span> : null}
            </div>
            <p>{item.body}</p>
            <details className="cl-tech">
              <summary>Details</summary>
              <span>{item.facts?.join(" · ")}</span>
            </details>
          </div>
        ))}
      </div>
    </details>
  );
}

export { ReviewGroup };
