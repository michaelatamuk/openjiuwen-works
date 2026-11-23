import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { postAction, streamAsk } from "../lib/api.js";
import { eventSummary, roleLabel, roleLetter, shortSha, stateLabel, stateTone, timelineLabel } from "../lib/format.js";
import { AiText } from "./ui.jsx";

const REVIEW_TYPES = new Set(["thread.commentary", "thread.discussion"]);

const PHASES = [
  { id: "plan", label: "Plan" },
  { id: "build", label: "Build" },
  { id: "check", label: "Check" },
  { id: "release", label: "Release" },
];

function phaseFor(message) {
  const type = message.type;
  if (type === "task.created" || type?.startsWith("memory.")) return null;
  if (type === "team.verified" || type === "decision.made") return null;
  if (type === "plan.drafted") return "plan";
  if (type === "gate.decided") return /plan/i.test(message.title || "") ? "plan" : "release";
  if (type === "attempt.started") return "build";
  if (type === "risk.rated") return "build";
  if (type === "note") return /proposal/i.test(`${message.title} ${message.body}`) ? "build" : "release";
  if (type === "step.started" || type === "step.finished") {
    const text = `${message.title} ${message.body} ${(message.facts || []).join(" ")}`;
    return /test/i.test(text) ? "check" : "plan";
  }
  if (["challenge.decided", "finding"].includes(type)) return "check";
  if (type === "delivery.finished" || type === "confirmation.finished") return "release";
  if (type?.startsWith("thread.")) return "release";
  return "release";
}

function currentPhase(state) {
  if (["queued", "reproducing", "reproduced", "planning"].includes(state)) return "plan";
  if (["plan_approved", "building"].includes(state)) return "build";
  if (state === "checking") return "check";
  return "release";
}

function phaseState(phase, currentId, taskState) {
  if (["released", "reverted"].includes(taskState)) return "done";
  const order = ["plan", "build", "check", "release"];
  const index = order.indexOf(phase);
  const current = order.indexOf(currentId);
  if (index < current) return "done";
  if (index === current) return taskState === "blocked" ? "blocked" : "current";
  return "pending";
}

function phaseSummary(id, detail, items) {
  if (!items.length) return "Not started";
  if (id === "plan") {
    const plan = items.find((item) => item.type === "plan.drafted");
    const rows = plan?.card?.rows || [];
    return rows[0]?.[1] ? `${rows[0][1]} scenarios` : "Plan drafted";
  }
  if (id === "build") {
    const files = detail.evidence?.files_changed?.length || 0;
    return files ? `${files} file${files === 1 ? "" : "s"} changed` : "Build recorded";
  }
  if (id === "check") {
    const outcomes = detail.evidence?.verdict?.outcomes || [];
    const passed = outcomes.filter((item) => item.passed).length;
    return outcomes.length ? `${passed}/${outcomes.length} checks passed` : "Check recorded";
  }
  if (detail.release?.released) return "Released";
  if (detail.task.state === "proved") return "Needs your approval";
  if (detail.task.state === "blocked") return "Blocked";
  return "Waiting";
}

function groupItems(items) {
  const out = [];
  for (const message of items) {
    if (REVIEW_TYPES.has(message.type)) {
      const last = out[out.length - 1];
      if (last?.review) last.review.push(message);
      else out.push({ key: `review-${message.seq}`, review: [message] });
    } else {
      out.push({ key: message.seq, message });
    }
  }
  return out;
}

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
  const inlineRelease = message.type === "note" && /release this commit/i.test(message.card?.prompt || "");
  const card = message.type === "thread.agent" || inlineRelease ? null : message.card;
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
        <p className="cl-rail-note">{blocker || "No blocker recorded."}</p>
      </section>
      <section>
        <h3>Activity</h3>
        {(detail.timeline || []).slice(-4).reverse().map((item) => (
          <div className="cl-activity" key={item.seq}>
            <time>{new Date(item.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
            <span>{timelineLabel(item.type)}</span>
            <b>{eventSummary(item).slice(0, 70)}</b>
          </div>
        ))}
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
  const [showAll, setShowAll] = useState(false);
  const [openPhase, setOpenPhase] = useState(null);
  const formRef = useRef(null);
  const lineRef = useRef(null);
  const stickRef = useRef(true);
  const phaseRefs = useRef({});
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
  const outcomes = detail.evidence?.verdict?.outcomes || [];
  const passed = outcomes.filter((item) => item.passed).length;
  const files = detail.evidence?.files_changed || [];
  const decisionStats = [
    outcomes.length ? `${passed}/${outcomes.length} checks` : null,
    files.length ? `${files.length} file${files.length === 1 ? "" : "s"}` : null,
    detail.summary?.risk ? `${detail.summary.risk} risk` : null,
  ].filter(Boolean);

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

  function jumpToPhase(id) {
    setShowAll(false);
    setOpenPhase(id);
    window.requestAnimationFrame(() => {
      phaseRefs.current[id]?.scrollIntoView({ block: "start", behavior: "smooth" });
    });
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
    <div className="cl-thread">
      <div className="cl-main">
        <div className="cl-head">
          <div className="cl-eyebrow">
            {source
              ? <a href={source} target="_blank" rel="noopener noreferrer">{detail.task.source.ref}</a>
              : <span>{detail.task.source.ref}</span>}
            <span>{detail.task.product}</span>
            <span className="cl-live-text"><i /> Live</span>
            <span className="cl-head-actions">
              <button type="button" className="cl-text-btn" onClick={() => { setShowAll((value) => !value); setOpenPhase(null); }}>
                {showAll ? "Digest" : "Full log"}
              </button>
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
                {decisionStats.length ? <em>{decisionStats.join(" / ")}</em> : null}
              </div>
              <button type="button" onClick={() => (decision.action ? onAction(decision.action) : onView(decision.view))}>
                {decision.button}
              </button>
            </div>
          ) : null}
        </div>

        {origin ? (
          <div className="cl-origin">
            <span>Reported</span>
            <b>{origin.body || detail.task.source.title}</b>
            <time>{new Date(origin.at).toLocaleDateString([], { month: "short", day: "numeric" })}</time>
          </div>
        ) : null}

        <div className="cl-phases" role="tablist" aria-label="Session phases">
          {phases.map((phase) => (
            <button
              key={phase.id}
              type="button"
              role="tab"
              aria-selected={phase.id === currentId}
              className={`cl-phase ${phase.state}`}
              onClick={() => jumpToPhase(phase.id)}
            >
              <i aria-hidden="true" />
              <span>{phase.label}</span>
            </button>
          ))}
        </div>

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
          {phases.map((phase) => {
            const isOpen = showAll || openPhase === phase.id || (openPhase === null && phase.id === currentId);
            return (
              <details
                key={phase.id}
                id={`phase-${phase.id}`}
                ref={(node) => { phaseRefs.current[phase.id] = node; }}
                className={`cl-phase-block ${phase.state}`}
                open={isOpen}
                onToggle={(event) => {
                  if (showAll) return;
                  if (event.currentTarget.open) setOpenPhase(phase.id);
                  else setOpenPhase(phase.id === currentId ? "none" : currentId);
                }}
              >
                <summary>
                  <span className="cl-phase-dot" aria-hidden="true" />
                  <span className="cl-phase-title">{phase.label}</span>
                  <span className="cl-phase-summary">{phase.summary}</span>
                  <span className="cl-phase-count">{phase.items.length}</span>
                </summary>
                <div className="cl-phase-body">
                  {phase.items.length
                    ? phase.blocks.map(renderBlock)
                    : <p className="cl-phase-empty">Not reached yet.</p>}
                </div>
              </details>
            );
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
            <div className="cl-working"><span /> Mira is reading the proof…</div>
          ) : null}
          {writable && canAsk ? (
            <div className="cl-suggest">
              <span>Ask about this run</span>
              {["What changed?", "Is it released?", "What was not tested?"].map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => {
                    setMode("ask");
                    setText(prompt);
                    formRef.current?.querySelector("textarea")?.focus();
                  }}
                >
                  {prompt}
                </button>
              ))}
            </div>
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
