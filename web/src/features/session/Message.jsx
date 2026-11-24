import { roleLabel, roleLetter } from "../../lib/format.js";
import { AiText } from "../../ui/primitives.jsx";
import { ThreadCard } from "./ThreadCard.jsx";

function Message({ message, onThreadAction }) {
  const role = message.role || "system";
  const card = message.type === "thread.agent" ? null : message.card;
  const hideTitle = message.generated || message.type === "thread.agent" || message.type === "thread.note";
  const details = message.generated ? (message.facts || []) : [];
  return (
    <article className={`cl-msg ${role} ${message.generated ? "generated" : ""} ${message.tone || ""}`}>
      <div className="cl-avatar" aria-hidden="true">{roleLetter[role] || "·"}</div>
      <div className="cl-body">
        <div className="cl-meta">
          <span className="cl-name">{roleLabel[role] || role}</span>
          {message.generated ? <span className="cl-ai-tag">AI</span> : null}
          {message.stance ? <span className={`cl-stance ${message.stance}`}>{message.stance}</span> : null}
          <time>{new Date(message.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
        </div>
        {!hideTitle && message.title ? <h3>{message.title}</h3> : null}
        {message.body ? (
          <p>{message.generated ? <AiText text={message.body} /> : message.body}</p>
        ) : null}
        {!message.generated && message.facts?.length ? (
          <div className="cl-facts">
            {message.facts.map((fact) => <span key={fact}>{fact}</span>)}
          </div>
        ) : null}
        {details.length ? (
          <details className="cl-tech">
            <summary>Details</summary>
            <span>{details.join(" · ")}</span>
          </details>
        ) : null}
        {card ? <ThreadCard card={card} onAction={onThreadAction} /> : null}
      </div>
    </article>
  );
}

export { Message };
