import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { postAction, streamAsk } from "../lib/api.js";
import { roleLabel, roleLetter, stateLabel, stateTone } from "../lib/format.js";
import { AiText } from "./ui.jsx";

function sourceUrl(task) {
  const ref = String(task?.source?.ref || "");
  if (/^https?:\/\//.test(ref)) return ref;
  const match = ref.match(/^([^/]+)\/([^#]+)#(\d+)$/);
  if (match) return `https://github.com/${match[1]}/${match[2]}/issues/${match[3]}`;
  return "";
}

function Message({ message, onThreadAction }) {
  const role = message.role || "system";
  const card = message.type === "thread.agent" ? null : message.card;
  const badge = message.generated ? (
    <span className="cl-ai-badge">{message.generated_label || "AI"}</span>
  ) : null;
  const stance = message.stance ? (
    <span className={`cl-stance ${message.stance}`}>{message.stance}</span>
  ) : null;
  return (
    <article className={`cl-msg ${role} ${message.generated ? "generated" : ""} ${message.tone || ""}`}>
      <div className="cl-avatar" aria-hidden="true">{roleLetter[role] || "·"}</div>
      <div className="cl-body">
        <div className="cl-meta">
          <span className="cl-name">{roleLabel[role] || role}</span>
          {badge}
          {stance}
          <time>{new Date(message.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
        </div>
        <h3>{message.title}</h3>
        {message.body ? (
          <p>{message.generated ? <AiText text={message.body} /> : message.body}</p>
        ) : null}
        {message.facts?.length ? (
          <div className="cl-facts">
            {message.facts.map((fact) => <span key={fact}>{fact}</span>)}
          </div>
        ) : null}
        {card ? <ThreadCard card={card} onAction={onThreadAction} /> : null}
      </div>
    </article>
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

function Rail({ rail }) {
  if (!rail) return null;
  const usable = (value) => {
    const text = String(value ?? "").trim();
    return text && !["—", "-", "not run", "None"].includes(text);
  };
  const topSections = [
    ["Task", [["State", rail.task?.state ? stateLabel(rail.task.state) : ""], ["Product", rail.task?.product], ["Source", rail.task?.source]]],
    ["Run", [["Flow", rail.factory?.flow], ["Run", rail.factory?.run], ["Commit", rail.factory?.base_commit], ["Checks", rail.factory?.checks_sha]]],
    ["People", (rail.people || []).map((person) => ["Approver", person])],
  ];
  const moreSections = [
    ["Agents", (rail.agents || []).filter((agent) => usable(agent.name)).map((agent) => [agent.role, [agent.name, agent.detail].filter(usable).join(" · ")])],
    ["Deliverables", (rail.deliverables || []).filter((item) => usable(item.value)).map((item) => [item.label, item.value])],
    ["Checks", (rail.checks || []).filter((item) => usable(item.value)).map((item) => [item.label, item.value])],
    ["Cost", rail.cost?.tokens || rail.cost?.usd ? [["Tokens", rail.cost?.tokens], ["USD", rail.cost?.usd != null ? `$${Number(rail.cost.usd).toFixed(4)}` : ""]] : []],
  ];
  const renderSection = ([title, rows]) => {
    const visible = rows.filter((row) => usable(row[1]));
    if (!visible.length) return null;
    return (
      <section key={title}>
        <h3>{title}</h3>
        {visible.map(([label, value]) => (
          <div className="cl-rail-row" key={`${title}-${label}-${value}`}>
            <span>{label}</span>
            <b>{String(value)}</b>
          </div>
        ))}
      </section>
    );
  };
  const hasMore = moreSections.some(([, rows]) => rows.some((row) => usable(row[1])));
  return (
    <aside className="cl-rail" aria-label="Task context">
      {topSections.map(renderSection)}
      {hasMore ? (
        <details className="cl-rail-more">
          <summary>Agents, deliverables & cost</summary>
          {moreSections.map(renderSection)}
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
  const [busy, setBusy] = useState(false);
  const formRef = useRef(null);
  const lineRef = useRef(null);
  const stickRef = useRef(true);
  const [atLatest, setAtLatest] = useState(true);
  const messages = detail.thread || [];
  const canAsk = Boolean(ai?.available);
  const activeMode = canAsk ? mode : "note";
  const source = sourceUrl(detail.task);
  const rail = useMemo(() => detail.rail || {}, [detail]);

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
            <span className={`cl-state ${stateTone(detail.task.state)}`}>{stateLabel(detail.task.state)}</span>
            {source
              ? <a href={source} target="_blank" rel="noopener noreferrer">{detail.task.source.ref}</a>
              : <span>{detail.task.source.ref}</span>}
            <span>{detail.task.product}</span>
          </div>
          {writable && canAsk ? (
            <div className="cl-head-actions">
              <button type="button" className="cl-text-btn" onClick={() => onAction("discussion")}>Team discussion</button>
              <button type="button" className="cl-text-btn" onClick={() => onAction("commentary")}>Generate commentary</button>
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
          {messages.length ? messages.map((message) => {
            const question = message.type === "thread.agent"
              ? (message.card?.rows || []).find(([label]) => String(label).toLowerCase() === "question")?.[1]
              : null;
            return (
              <Fragment key={message.seq}>
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
              {pendingQuestion ? (
                <div className="cl-user-turn"><p>{pendingQuestion}</p></div>
              ) : null}
              {streamed ? (
                <article className="cl-msg mira generated streaming">
                  <div className="cl-avatar" aria-hidden="true">M</div>
                  <div className="cl-body">
                    <div className="cl-meta"><span className="cl-name">Mira</span><span className="cl-ai-badge">AI answer</span></div>
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
          <button type="button" className="cl-latest" onClick={jumpToLatest}>Latest ?</button>
        ) : null}

        {writable ? (
          <form className="cl-composer" ref={formRef} onSubmit={submit}>
            <div className="cl-modes" role="group" aria-label="Message mode">
              {canAsk ? (
                <button type="button" className={activeMode === "ask" ? "active" : ""} onClick={() => setMode("ask")}>Ask Mira</button>
              ) : null}
              <button type="button" className={activeMode === "note" ? "active" : ""} onClick={() => setMode("note")}>Add context</button>
            </div>
            <textarea
              rows={1}
              value={text}
              placeholder={activeMode === "ask" ? "Tell Mira more…" : "Add context to this run…"}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) formRef.current?.requestSubmit();
              }}
            />
            <div className="cl-composer-actions">
              <span>
                {activeMode === "ask"
                  ? "Advisory only · Mira remembers earlier answers and cannot open a gate."
                  : "A note, not a command · never opens a gate or starts a run."}
              </span>
              <button type="submit" className="cl-send" disabled={busy || !text.trim()} aria-label={activeMode === "ask" ? "Ask Mira" : "Add context"}>
                ↑
              </button>
            </div>
          </form>
        ) : (
          <p className="cl-readonly">Start <span className="mono">works ui --write</span> to ask Mira or add context.</p>
        )}
      </div>
      <Rail rail={rail} />
    </div>
  );
}
