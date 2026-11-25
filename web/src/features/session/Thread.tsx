import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, askStream } from "../../api/client";
import { roleLabel } from "../../lib/format.js";
import { ChapterBar } from "./ChapterBar";
import { Composer } from "./Composer";
import { Message } from "./Message";
import { Rail } from "./Rail";
import { ReviewGroup } from "./ReviewGroup";
import { SessionHead } from "./SessionHead";
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
} from "./model";
import type {
  ComposerMode,
  Phase,
  PhaseId,
  PhaseView,
  SessionDecision,
  SessionDetail,
  SessionMode,
  ThreadBlock,
  ThreadMessage,
} from "./types";

export type ThreadProps = {
  detail: SessionDetail;
  ai?: { available?: boolean } | null;
  writable: boolean;
  onAction: (action: string, body?: Record<string, unknown>) => unknown;
  onView: (view: string) => void;
  onRefresh: () => unknown;
  onShowRun: () => void;
  onToast: (message: string) => void;
};

const PHASE_LIST = PHASES as Phase[];

const DIVIDER_LABELS: Record<string, string> = {
  reported: "Reported",
  plan: "Plan",
  build: "Build",
  check: "Check",
  release: "Release",
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function Thread({ detail, ai, writable, onAction, onView, onRefresh, onShowRun, onToast }: ThreadProps) {
  const [mode, setMode] = useState<ComposerMode>("ask");
  const [text, setText] = useState("");
  const [streamed, setStreamed] = useState("");
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [focused, setFocused] = useState(false);
  const [busy, setBusy] = useState(false);
  const [atLatest, setAtLatest] = useState(true);
  const [showAll, setShowAll] = useState(false);
  const [selectedPhase, setSelectedPhase] = useState<PhaseId | null>(null);
  const [sessionMode, setSessionMode] = useState<SessionMode>("pipeline");
  const [aiBusy, setAiBusy] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const lineRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);
  const messages: ThreadMessage[] = detail.thread || [];
  const canAsk = Boolean(ai?.available);
  const activeMode: ComposerMode = canAsk ? mode : "note";
  const source: string = sourceUrl(detail.task);
  const decision = decisionFor(detail) as SessionDecision | null;
  const currentId = currentPhase(detail.task.state) as PhaseId;
  const origin = messages.find((message) => message.type === "task.created");
  const phases = useMemo<PhaseView[]>(() => {
    const groups = Object.fromEntries(
      PHASE_LIST.map((phase) => [phase.id, [] as ThreadMessage[]]),
    ) as Record<PhaseId, ThreadMessage[]>;
    for (const message of messages) {
      const phase = phaseFor(message) as PhaseId | null;
      if (phase) groups[phase].push(message);
    }
    return PHASE_LIST.map((phase) => ({
      ...phase,
      state: phaseState(phase.id, currentId, detail.task.state),
      summary: phaseSummary(phase.id, detail, groups[phase.id]),
      items: groups[phase.id],
      blocks: groupItems(groups[phase.id]),
    }));
  }, [messages, currentId, detail]);
  const visiblePhases = showAll ? phases : phases.filter((phase) => phase.id === (selectedPhase || currentId));
  const pipelineBlocks = useMemo<ThreadBlock[]>(() => {
    let lastPhase: string | null = null;
    const out: ThreadBlock[] = [];
    for (const message of messages) {
      if (message.type.startsWith("memory.")) continue;
      if (message.type === "team.verified" || message.type === "decision.made") continue;
      const phase = message.type === "task.created" ? "reported" : (phaseFor(message) as string | null);
      if (phase && phase !== lastPhase) {
        out.push({ key: `divider-${message.seq}`, divider: phase });
        lastPhase = phase;
      }
      if (REVIEW_TYPES.has(message.type)) {
        const last = out[out.length - 1];
        if (last && "review" in last) last.review.push(message);
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

  function threadAction(action: string) {
    if (action === "open-run") return onShowRun();
    if (action === "open-release") return onView("release");
    if (action === "open-evidence") return onView("evidence");
    return onAction(action);
  }

  async function runAi(action: string) {
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setText("");
    setBusy(true);
    setStreamed("");
    try {
      if (activeMode === "ask" && canAsk) {
        setPendingQuestion(message);
        await askStream(detail.task.id, message, (event) => {
          if (event.type === "delta") setStreamed((current) => current + String(event.text || ""));
        });
        setStreamed("");
        await onRefresh();
        setPendingQuestion("");
      } else {
        await api.action({ action: "add-context", task_id: detail.task.id, message });
        onToast("Context added to the worklog.");
        await onRefresh();
      }
    } catch (error) {
      setPendingQuestion("");
      onToast(activeMode === "ask" ? `Mira failed: ${errorMessage(error)}` : `Could not add context: ${errorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  }

  function renderBlock(block: ThreadBlock) {
    if ("review" in block) return <ReviewGroup key={block.key} items={block.review} />;
    if (!("message" in block)) return null;
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
        <SessionHead
          detail={detail}
          source={source}
          sessionMode={sessionMode}
          writable={writable}
          canAsk={canAsk}
          aiBusy={aiBusy}
          decision={decision}
          onMode={setSessionMode}
          onAi={runAi}
          onDecision={threadAction}
          onView={onView}
        />

        <div className="cl-work">
          <div className="cl-chat">
            {sessionMode === "log" ? (
              <ChapterBar
                phases={phases}
                showAll={showAll}
                selectedPhase={selectedPhase}
                currentId={currentId}
                onSelect={(id) => {
                  setShowAll(false);
                  setSelectedPhase(id === currentId ? null : id);
                  if (lineRef.current) lineRef.current.scrollTop = 0;
                }}
                onShowAll={(checked) => {
                  setShowAll(checked);
                  setSelectedPhase(null);
                }}
                onReset={() => setSelectedPhase(null)}
              />
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
                if ("divider" in block) {
                  return (
                    <div className="cl-divider" key={block.key}>
                      <span>{DIVIDER_LABELS[block.divider] || block.divider}</span>
                    </div>
                  );
                }
                if ("review" in block) return <ReviewGroup key={block.key} items={block.review} />;
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
          <Composer
            canAsk={canAsk}
            activeMode={activeMode}
            text={text}
            busy={busy}
            focused={focused}
            formRef={formRef}
            onText={setText}
            onFocus={setFocused}
            onToggleMode={() => setMode(activeMode === "ask" ? "note" : "ask")}
            onSubmit={submit}
          />
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
