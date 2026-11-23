import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { postAction, streamAsk } from "../lib/api.js";
import { roleLabel, roleLetter, shortSha, stateLabel } from "../lib/format.js";
import { AiText } from "./ui.jsx";

const REVIEW_TYPES = new Set(["thread.commentary", "thread.discussion"]);

function sourceUrl(task) {
  const ref = String(task?.source?.ref || "");
  if (/^https?:\/\//.test(ref)) return ref;
  const match = ref.match(/^([^/]+)\/([^#]+)#(\d+)$/);
  if (match) return `https://github.com/${match[1]}/${match[2]}/issues/${match[3]}`;
  return "";
}

function decisionFor(detail) {
  const state = detail.task.state;
  const release = detail.release || {};
  if (state === "planning") {
    return {
      tone: "amber",
      label: "Plan gate",
      text: "A person needs to approve the plan before the build starts.",
      action: "approve-plan",
      button: "Approve plan",
    };
  }
  if (state === "proved" && !release.released) {
    return {
      tone: "amber",
      label: "Release gate",
      text: "The proof is ready. A person needs to release it back to the product.",
      action: "release",
      button: "Approve release",
    };
  }
  if (state === "blocked") {
    return {
      tone: "red",
      label: "Blocked",
      text: detail.pipeline?.blocked?.why || "The run stopped and needs a person.",
      action: null,
      view: "evidence",
      button: "Open evidence",
    };
  }
  return null;
}

function ReviewGroup({ items }) {
  const stances = items.map((item) => item.stance).filter(Boolean);
  const concern = stances.includes("concern") || stances.includes("block");
  return (
    <details className="cl-review">
      <summary>
        <span className="cl-review-title">Review</span>
        <span className="cl-review-meta">
          {items.length} agent{items.length === 1 ? "" : "s"} · {concern ? "has a concern" : "all support"}
        </span>
        <span className="cl-ai-tag">AI</span>
      </summary>
      <div className="cl-review-body">
        {items.map((item) => (
          <div className="cl-review-row" key={item.seq}>
            <div className="cl-review-head">
              <b>{roleLabel[item.role] || item.role}</b>
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

function ThreadCard({ card, onAction }) {
  return (
    <div className="cl-question">
      {card.prompt ? <p className="cl-prompt">{card.prompt}</p> : null}
      {(card.rows || []).map(([label, value]) => {
        const text = String(value ?? "");
        return (
          <div className="cl-row" key={`${label}-${text}`}>
            <span>{label}</span>
            {/^https?:\/\//.test(text)
              ? <a href={text} target="_blank" rel="noopener noreferrer">{text}</a>
              : <span className="mono">{text}</span>}
          </div>
        );
      })}
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

function Rail({ detail, onAction, onView }) {
  const rail = detail.rail || {};
  const release = detail.release || {};
  const decision = decisionFor(detail);
  const approvers = (rail.people || []).filter(Boolean);
  const blocker = release.blockers?.[0] || decision?.text;
  const checks = rail.checks?.find((item) => item.label === "Verdict")?.value || "—";
  const technical = [
    ["Commit", rail.factory?.base_commit],
    ["Checks", rail.factory?.checks_sha],
    ["Proof", rail.deliverables?.find((item) => item.label === "Proof")?.value],
  ].filter(([, value]) => value);
  return (
    <aside className="cl-rail" aria-label="Task context">
      <section>
        <h3>Decision</h3>
        <div className="cl-rail-state">{stateLabel(detail.task.state)}</div>
        {blocker ? <p className="cl-rail-note">{blocker}</p> : null}
      </section>
      <section>
        <h3>Next</h3>
        <div className="cl-rail-next">
          {decision ? decision.button : detail.task.state === "released" ? "Delivered" : "No action needed"}
        </div>
      </section>
      <section>
        <h3>Run</h3>
        <div className="cl-rail-row"><span>Flow</span><b>{rail.factory?.flow || "—"}</b></div>
        <div className="cl-rail-row"><span>Run</span><b className="mono">{shortSha(rail.factory?.run)}</b></div>
        <div className="cl-rail-row"><span>Checks</span><b>{checks}</b></div>
        <div className="cl-rail-row"><span>Cost</span><b>{rail.cost?.usd != null ? `$${Number(rail.cost.usd).toFixed(4)}` : "—"}</b></div>
      </section>
      <section>
        <h3>People</h3>
        {approvers.length ? approvers.map((person) => (
          <div className="cl-person" key={person}><span className="cl-person-dot" />{person}</div>
        )) : <p className="cl-rail-note">No person has acted yet.</p>}
      </section>
      {technical.length || rail.agents?.length ? (
        <details className="cl-rail-tech">
          <summary>Technical</summary>
          {technical.map(([label, value]) => (
            <div className="cl-rail-row" key={label}><span>{label}</span><b className="mono">{value}</b></div>
          ))}
          {(rail.agents || []).filter((agent) => agent.name).map((agent) => (
            <div className="cl-rail-row" key={agent.role}>
              <span>{agent.role}</span><b>{agent.name}{agent.detail ? ` · ${agent.detail}` : ""}</b>
            </div>
          ))}
        </details>
      ) : null}
    </aside>
  );
}

export function Thread({ detail, ai, writable, onAction, onView, onRefresh, onShowRun, onToast }) {
  const [mode, setMode] = useState("ask");
  const [text, setText] = useState("");
  const [streamed, setStreamed] = useState("");
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [focused, setFocused] = useState(false);
  const [busy, setBusy] = useState(false);
  const [atLatest, setAtLatest] = useState(true);
  const formRef = useRef(null);
  const lineRef = useRef(null);
  const stickRef = useRef(true);
  const messages = detail.thread || [];
  const canAsk = Boolean(ai?.available);
  const activeMode = canAsk ? mode : "note";
  const source = sourceUrl(detail.task);
  const decision = decisionFor(detail);
  const blocks = useMemo(() => {
    const out = [];
    for (const message of messages) {
      if (REVIEW_TYPES.has(message.type)) {
        const last = out[out.length - 1];
        if (last?.review) last.review.push(message);
        else out.push({ key: `review-${message.seq}`, review: [message] });
      } else {
        out.push({ key: message.seq, message });
      }
    }
    return out;
  }, [messages]);

  useEffect(() => {
    stickRef.current = true;
    setAtLatest(true);
    const line = lineRef.current;
    if (line) line.scrollTop = line.scrollHeight;
  }, [detail.task.id]);

  useEffect(() => {
    const line = lineRef.current;
    if (line && stickRef.current) {
      line.scrollTop = line.scrollHeight;
      setAtLatest(true);
    }
  }, [messages.length, streamed]);

  function jumpToLatest() {
    const line = lineRef.current;
    if (!line) return;
    line.scrollTop = line.scrollHeight;
    stickRef.current = true;
    setAtLatest(true);
  }

  function threadAction(action) {
    if (action === "open-run") return onShowRun();
    if (action === "open-release") return onView("release");
    if (action === "open-evidence") return onView("evidence");
    return onAction(action);
  }

  async function submit(event) {
    event.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setText("");
    setBusy(true);
    setStreamed("");
    try {
      if (activeMode === "ask" && canAsk) {
        setPendingQuestion(message);
        await streamAsk(detail.task.id, message, (delta) => setStreamed((current) => current + delta));
        setStreamed("");
        await onRefresh();
        setPendingQuestion("");
      } else {
        await postAction("add-context", detail.task.id, { message });
        onToast("Context added to the worklog.");
        await onRefresh();
      }
    } catch (error) {
      setPendingQuestion("");
      onToast(activeMode === "ask" ? `Mira failed: ${error.message}` : `Could not add context: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cl-thread">
      <div className="cl-main">
        <header className="cl-head">
          <div className="cl-eyebrow">
            {source
              ? <a href={source} target="_blank" rel="noopener noreferrer">{detail.task.source.ref}</a>
              : <span>{detail.task.source.ref}</span>}
            <span>{detail.task.product}</span>
            <span className="cl-live-text"><i /> Live</span>
            <span className="cl-head-actions">
              {writable && canAsk ? (
                <>
                  <button type="button" className="cl-text-btn" onClick={() => onAction("discussion")}>Review</button>
                  <button type="button" className="cl-text-btn" onClick={() => onAction("commentary")}>Commentary</button>
                </>
              ) : null}
            </span>
          </div>
          {decision ? (
            <div className={`cl-decision ${decision.tone}`}>
              <div>
                <span>{decision.label}</span>
                <b>{decision.text}</b>
              </div>
              <button
                type="button"
                onClick={() => (decision.action ? onAction(decision.action) : onView(decision.view))}
              >
                {decision.button}
              </button>
            </div>
          ) : null}
        </header>

        <div
          className="cl-line"
          ref={lineRef}
          onScroll={(event) => {
            const node = event.currentTarget;
            const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
            stickRef.current = distance < 80;
            setAtLatest(distance < 80);
          }}
        >
          {blocks.length ? blocks.map((block) => {
            if (block.review) return <ReviewGroup key={block.key} items={block.review} />;
            const message = block.message;
            const question = message.type === "thread.agent"
              ? (message.card?.rows || []).find(([label]) => String(label).toLowerCase() === "question")?.[1]
              : null;
            return (
              <Fragment key={block.key}>
                {question ? (
                  <div className="cl-user-turn">
                    <p>{question}</p>
                    <time>{new Date(message.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
                  </div>
                ) : null}
                <Message message={message} onThreadAction={threadAction} />
              </Fragment>
            );
          }) : <p className="muted small">No events yet.</p>}
          {streamed || pendingQuestion ? (
            <>
              {pendingQuestion ? <div className="cl-user-turn"><p>{pendingQuestion}</p></div> : null}
              {streamed ? (
                <article className="cl-msg mira generated streaming">
                  <div className="cl-avatar" aria-hidden="true">M</div>
                  <div className="cl-body">
                    <div className="cl-meta"><span className="cl-name">Mira</span><span className="cl-ai-tag">AI</span></div>
                    <p>{streamed}<span className="cl-cursor" /></p>
                  </div>
                </article>
              ) : null}
            </>
          ) : null}
          {busy && !streamed ? (
            <div className="cl-working"><span /> Mira is reading the proof…</div>
          ) : null}
        </div>

        {!atLatest ? (
          <button type="button" className="cl-latest" onClick={jumpToLatest}>Jump to latest</button>
        ) : null}

        {writable ? (
          <form className={`cl-composer ${focused ? "focused" : ""}`} ref={formRef} onSubmit={submit}>
            <div className="cl-composer-row">
              {canAsk ? (
                <button
                  type="button"
                  className="cl-mode"
                  onClick={() => setMode(activeMode === "ask" ? "note" : "ask")}
                  title={activeMode === "ask" ? "Switch to Add context" : "Switch to Ask Mira"}
                >
                  {activeMode === "ask" ? "Ask" : "Note"}
                </button>
              ) : <span className="cl-mode">Note</span>}
              <textarea
                rows={1}
                value={text}
                placeholder={activeMode === "ask" ? "Ask Mira…" : "Add context…"}
                onChange={(event) => setText(event.target.value)}
                onFocus={() => setFocused(true)}
                onBlur={() => setFocused(false)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) formRef.current?.requestSubmit();
                }}
              />
              <button type="submit" className="cl-send" disabled={busy || !text.trim()} aria-label={activeMode === "ask" ? "Ask Mira" : "Add context"}>
                ↑
              </button>
            </div>
            {focused || text ? (
              <div className="cl-helper">Ctrl Enter to send · advisory only, never opens a gate</div>
            ) : null}
          </form>
        ) : (
          <p className="cl-readonly">Start <span className="mono">works ui --write</span> to ask Mira or add context.</p>
        )}
      </div>
      <Rail detail={detail} onAction={onAction} onView={onView} />
    </div>
  );
}
