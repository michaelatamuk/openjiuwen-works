import type { ThreadCardData } from "./types";

export type ThreadCardProps = {
  card: ThreadCardData;
  onAction: (action: string) => void;
};

function ThreadCard({ card, onAction }: ThreadCardProps) {
  const rows = (card.rows || []).map(([label, value]) => {
    const text = String(value ?? "");
    return (
      <div className="cl-row" key={`${label}-${text}`}>
        <span>{label}</span>
        {/^https?:\/\//.test(text)
          ? <a href={text} target="_blank" rel="noopener noreferrer">{text}</a>
          : <span className="mono">{text}</span>}
      </div>
    );
  });
  return (
    <div className="cl-question">
      {card.prompt ? <p className="cl-prompt">{card.prompt}</p> : null}
      {card.kind === "question" ? rows : (
        <details className="cl-tech">
          <summary>Details</summary>
          {rows}
        </details>
      )}
      {card.options?.length ? (
        <div className="cl-options">
          {card.options.map((option) => (
            <button
              key={`${option.action}-${option.label}`}
              type="button"
              className={`btn ${option.tone === "primary" ? "" : "ghost"}`}
              onClick={() => onAction(option.action)}
            >
              {option.label}{option.recommended ? " · recommended" : ""}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export { ThreadCard };
