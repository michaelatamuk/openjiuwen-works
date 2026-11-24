import type { SessionDecision, SessionDetail, SessionMode } from "./types";

export type SessionHeadProps = {
  detail: SessionDetail;
  source: string;
  sessionMode: SessionMode;
  writable: boolean;
  canAsk: boolean;
  aiBusy: string | null;
  decision: SessionDecision | null;
  onMode: (mode: SessionMode) => void;
  onAi: (action: string) => void;
  onDecision: (action: string) => void;
  onView: (view: string) => void;
};

export function SessionHead({
  detail,
  source,
  sessionMode,
  writable,
  canAsk,
  aiBusy,
  decision,
  onMode,
  onAi,
  onDecision,
  onView,
}: SessionHeadProps) {
  return (
    <div className="cl-head">
      <div className="cl-eyebrow">
        {source
          ? <a href={source} target="_blank" rel="noopener noreferrer">{detail.task.source.ref}</a>
          : <span>{detail.task.source.ref}</span>}
        <span>{detail.task.product}</span>
        <span className="cl-live-text"><i /> Live</span>
        <span className="cl-head-actions">
          <span className="cl-mode-switch" role="tablist" aria-label="Session mode">
            <button
              type="button"
              role="tab"
              aria-selected={sessionMode === "pipeline"}
              className={sessionMode === "pipeline" ? "active" : ""}
              onClick={() => onMode("pipeline")}
            >
              Conversation
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={sessionMode === "log"}
              className={sessionMode === "log" ? "active" : ""}
              onClick={() => onMode("log")}
            >
              Run log
            </button>
          </span>
          {writable && canAsk ? (
            <span className="cl-ai-actions">
              <span className="cl-ai-label">Ask AI</span>
              <button
                type="button"
                className="cl-text-btn"
                disabled={Boolean(aiBusy)}
                title="Ask the team for a review of this run"
                onClick={() => onAi("discussion")}
              >
                {aiBusy === "discussion" ? "Reviewing…" : "Review"}
              </button>
              <button
                type="button"
                className="cl-text-btn"
                disabled={Boolean(aiBusy)}
                title="Ask the agents for commentary on this run"
                onClick={() => onAi("commentary")}
              >
                {aiBusy === "commentary" ? "Writing…" : "Commentary"}
              </button>
            </span>
          ) : null}
        </span>
      </div>
      {sessionMode === "pipeline" && decision && (decision.action === "approve-plan" || decision.tone === "red") ? (
        <div className={`cl-decision ${decision.tone}`}>
          <div>
            <span>{decision.label}</span>
            <b>{decision.text}</b>
          </div>
          <button
            type="button"
            onClick={() => (decision.action ? onDecision(decision.action) : onView(decision.view || ""))}
          >
            {decision.button}
          </button>
        </div>
      ) : null}
    </div>
  );
}
