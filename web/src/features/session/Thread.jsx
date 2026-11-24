import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { postAction, streamAsk } from "../../lib/api.js";
import { roleLabel } from "../../lib/format.js";
import { Message } from "./Message.jsx";
import { Rail } from "./Rail.jsx";
import { ReviewGroup } from "./ReviewGroup.jsx";
import {
  PHASES,
  REVIEW_TYPES,
  currentPhase,
  decisionFor,
  groupItems,
  phaseFor,
  phaseState,
  phaseSummary,
  sourceUrl,
} from "./model.js";

export function Thread({ detail, ai, writable, onAction, onView, onRefresh, onShowRun, onToast }) {
  const [mode, setMode] = useState("ask");
  const [text, setText] = useState("");
  const [streamed, setStreamed] = useState("");
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [focused, setFocused] = useState(false);
  const [busy, setBusy] = useState(false);
  const [atLatest, setAtLatest] = useState(true);
  const [showAll, setShowAll] = useState(false);
  const [selectedPhase, setSelectedPhase] = useState(null);
  const [sessionMode, setSessionMode] = useState("pipeline");
  const [aiBusy, setAiBusy] = useState(null);
  const formRef = useRef(null);
  const lineRef = useRef(null);
  const stickRef = useRef(true);
  const messages = detail.thread || [];
  const canAsk = Boolean(ai?.available);
  const activeMode = canAsk ? mode : "note";
  const source = sourceUrl(detail.task);
  const decision = decisionFor(detail);
  const currentId = currentPhase(detail.task.state);
  const origin = messages.find((message) => message.type === "task.created");
  const phases = useMemo(() => {
    const groups = Object.fromEntries(PHASES.map((phase) => [phase.id, []]));
    for (const message of messages) {
      const phase = phaseFor(message);
      if (phase) groups[phase].push(message);
    }
    return PHASES.map((phase) => ({
      ...phase,
      state: phaseState(phase.id, currentId, detail.task.state),
      summary: phaseSummary(phase.id, detail, groups[phase.id]),
      items: groups[phase.id],
      blocks: groupItems(groups[phase.id]),
    }));
  }, [messages, currentId, detail]);
  const visiblePhases = showAll ? phases : phases.filter((phase) => phase.id === (selectedPhase || currentId));
  const pipelineBlocks = useMemo(() => {
    let lastPhase = null;
    const out = [];
    for (const message of messages) {
      if (message.type.startsWith("memory.")) continue;
      if (message.type === "team.verified" || message.type === "decision.made") continue;
      const phase = message.type === "task.created" ? "reported" : phaseFor(message);
      if (phase && phase !== lastPhase) {
        out.push({ key: `divider-${message.seq}`, divider: phase });
        lastPhase = phase;
      }
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

  async function runAi(action) {
    if (aiBusy) return;
    setAiBusy(action);
    try {
      await onAction(action);
      setSessionMode("pipeline");
      setShowAll(false);
      stickRef.current = true;
      window.requestAnimationFrame(() => {
        if (lineRef.current) lineRef.current.scrollTop = lineRef.current.scrollHeight;
      });
    } catch {
      /* App already surfaces the failure as a toast. */
    } finally {
      setAiBusy(null);
    }
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

  function renderBlock(block) {
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
  }

  return (
    <div className={`cl-thread ${sessionMode === "pipeline" ? "conversation" : "log"}`}>
      <div className="cl-main">
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
                  onClick={() => setSessionMode("pipeline")}
                >
                  Conversation
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={sessionMode === "log"}
                  className={sessionMode === "log" ? "active" : ""}
                  onClick={() => setSessionMode("log")}
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
                    onClick={() => runAi("discussion")}
                  >
                    {aiBusy === "discussion" ? "Reviewing…" : "Review"}
                  </button>
                  <button
                    type="button"
                    className="cl-text-btn"
                    disabled={Boolean(aiBusy)}
                    title="Ask the agents for commentary on this run"
                    onClick={() => runAi("commentary")}
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
                onClick={() => (decision.action ? threadAction(decision.action) : onView(decision.view))}
              >
                {decision.button}
              </button>
            </div>
          ) : null}
        </div>

        <div className="cl-work">
          <div className="cl-chat">
            {sessionMode === "log" ? (
              <nav className="cl-chapter-bar" aria-label="Run chapters">
                {phases.map((phase) => (
                  <button
                    key={phase.id}
                    type="button"
                    className={`cl-chapter-chip ${phase.state} ${!showAll && (selectedPhase || currentId) === phase.id ? "active" : ""}`}
                    onClick={() => {
                      setShowAll(false);
                      setSelectedPhase(phase.id === currentId ? null : phase.id);
                      if (lineRef.current) lineRef.current.scrollTop = 0;
                    }}
                  >
                    <span className="cl-phase-dot" aria-hidden="true" />
                    {phase.label}
                    <span className="cl-chapter-chip-count">{phase.items.length}</span>
                  </button>
                ))}
                <label className="cl-chapter-all">
                  <input
                    type="checkbox"
                    checked={showAll}
                    onChange={(event) => {
                      setShowAll(event.target.checked);
                      setSelectedPhase(null);
                    }}
                  />
                  All chapters
                </label>
                {selectedPhase ? (
                  <button type="button" className="cl-chapter-reset" onClick={() => setSelectedPhase(null)}>
                    Back to current
                  </button>
                ) : null}
              </nav>
            ) : null}
            {sessionMode === "log" && origin ? (
              <div className="cl-origin">
                <span>Reported</span>
                <b>{origin.body || detail.task.source.title}</b>
                <time>{new Date(origin.at).toLocaleDateString([], { month: "short", day: "numeric" })}</time>
              </div>
            ) : null}

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
              {sessionMode === "log" ? visiblePhases.map((phase) => (
                <section className={`cl-chapter ${phase.state}`} key={phase.id}>
                  <header>
                    <span className="cl-phase-dot" aria-hidden="true" />
                    <h3>{phase.label}</h3>
                    <span className="cl-chapter-summary">{phase.summary}</span>
                    <span className="cl-chapter-count">{phase.items.length}</span>
                  </header>
                  <div className="cl-chapter-body">
                    {phase.items.length
                      ? phase.blocks.map(renderBlock)
                      : <p className="cl-phase-empty">No events in this chapter.</p>}
                  </div>
                </section>
              )) : pipelineBlocks.map((block) => {
                if (block.divider) {
                  return (
                    <div className="cl-divider" key={block.key}>
                      <span>{{ reported: "Reported", plan: "Plan", build: "Build", check: "Check", release: "Release" }[block.divider] || block.divider}</span>
                    </div>
                  );
                }
                if (block.review) return <ReviewGroup key={block.key} items={block.review} />;
                const message = block.message;
                if (message.role === "person") {
                  const body = message.type === "gate.decided" ? "Approved by a person." : message.body;
                  return (
                    <div className="cl-user-turn" key={block.key}>
                      <div className="cl-user-meta"><b>{roleLabel.person}</b><time>{new Date(message.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></div>
                      {message.title && message.title !== "Reported" ? <b className="cl-user-title">{message.title}</b> : null}
                      <p>{body}</p>
                    </div>
                  );
                }
                return renderBlock({ key: block.key, message });
              })}
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
                <div className="cl-working"><span /> Mira is reading the proof.</div>
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
                placeholder={activeMode === "ask" ? "Ask about this run..." : "Add context to this run..."}
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
        </div>
      </div>
      <Rail detail={detail} onAction={onAction} onView={onView} />
    </div>
  );
}
