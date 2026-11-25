import { useCallback, useEffect, useRef, useState } from "react";
import { api, isUnauthorized, waitForJob } from "../api/client";
import type { Health, Job, TaskDetail, TaskSummary } from "../api/client";
import type { BuilderSettings } from "../features/settings/types";
import type { EvidenceDetail, EvidenceTimelineEvent } from "../features/evidence/Evidence";
import type { QueueTask } from "../features/queue/Queue";
import type { ReleaseDetail } from "../features/release/Release";
import type { SessionDetail } from "../features/session/types";
import type { StoryDetail } from "../features/story/Story";
import {
  CompareDialog, EventDialog, FactoryDialog, HelpDialog, ImportDialog,
  Lightbox, NewTaskDialog, Palette, RunDialog, SettingsDialog,
} from "../features/dialogs/Dialogs";
import { Evidence } from "../features/evidence/Evidence";
import { SignIn } from "../features/auth/SignIn";
import { Queue } from "../features/queue/Queue";
import { Release } from "../features/release/Release";
import { Story } from "../features/story/Story";
import { Thread } from "../features/session/Thread";
import { Toast } from "../ui/primitives";
import { AppHeader } from "./AppHeader";
import { MainHead } from "./MainHead";
import { stateLabel, timeAgo } from "../lib/format";
import { crumbFor, isViewId, parseHash, taskHash } from "./routing";
import type { ViewId } from "./routing";

/** The fields App and the detail screens read from `detail.task`. */
type AppSource = {
  kind?: string;
  ref?: string;
  title?: string;
};

type AppTask = {
  id: string;
  state: string;
  product: string;
  flow?: string;
  created_at?: string;
  source: AppSource;
};

/**
 * A task detail payload is shared by every detail screen, so App types it as the
 * intersection of the shapes those screens consume.
 */
type AppDetail = Omit<StoryDetail, "task"> &
  Omit<EvidenceDetail, "task"> &
  Omit<ReleaseDetail, "task"> &
  Omit<SessionDetail, "task"> & { task: AppTask };

type AppAi = { available?: boolean } & Record<string, unknown>;

type AppHealth = {
  ok: boolean;
  readonly: boolean;
  root: string;
  version: string;
  write: boolean;
  ai: AppAi;
  builder: BuilderSettings | null;
};

type Detector = {
  name: string;
  product: string;
};

type LightboxImage = {
  url: string;
  alt?: string;
};

type DialogName = "new" | "import" | "factory" | "settings" | "help" | "palette";

type ActionResult = {
  messages?: unknown[];
  status?: string;
  event?: { type?: string } | null;
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function appSource(value: unknown): AppSource {
  if (!isRecord(value)) return {};
  return {
    kind: typeof value.kind === "string" ? value.kind : undefined,
    ref: typeof value.ref === "string" ? value.ref : undefined,
    title: typeof value.title === "string" ? value.title : undefined,
  };
}

function appTask(value: Record<string, unknown>): AppTask | null {
  if (typeof value.id !== "string" || typeof value.state !== "string") return null;
  return {
    ...value,
    id: value.id,
    state: value.state,
    product: typeof value.product === "string" ? value.product : "",
    source: appSource(value.source),
  };
}

/**
 * The generated TaskDetail leaves nested payloads as unknown records; the detail
 * screens narrow the fields they read and trust the payload once the task identity
 * is present.
 */
function appDetail(payload: TaskDetail): AppDetail | null {
  const task = appTask(payload.task);
  if (!task) return null;
  return { ...payload, task } as unknown as AppDetail;
}

function appBuilder(value: Record<string, unknown> | null | undefined): BuilderSettings | null {
  return value ? (value as BuilderSettings) : null;
}

function appHealth(health: Health): AppHealth {
  return {
    ...health,
    ai: { ...health.ai, available: health.ai.available === true },
    builder: appBuilder(health.builder),
  };
}

function productNames(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) =>
    isRecord(item) && typeof item.name === "string" ? [item.name] : [],
  );
}

function detectorList(value: unknown): Detector[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!isRecord(item) || typeof item.name !== "string") return [];
    return [{
      name: item.name,
      product: typeof item.product === "string" ? item.product : "",
    }];
  });
}

function actionResult(value: unknown): ActionResult {
  if (!isRecord(value)) return {};
  const event = isRecord(value.event) ? value.event : null;
  return {
    messages: Array.isArray(value.messages) ? value.messages : undefined,
    status: typeof value.status === "string" ? value.status : undefined,
    event: event ? { type: typeof event.type === "string" ? event.type : undefined } : null,
  };
}

function queueTask(task: TaskSummary): QueueTask {
  return {
    id: task.id,
    state: task.state,
    title: task.title,
    product: task.product,
    source: task.source,
    flow: task.flow,
    risk: task.risk ?? undefined,
    updated_at: task.updated_at,
  };
}

export default function App() {
  const [health, setHealth] = useState<AppHealth | null>(null);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<AppDetail | null>(null);
  const [view, setView] = useState<ViewId>(() => {
    const stored = localStorage.getItem("works.view.v3");
    return stored && isViewId(stored) ? stored : "story";
  });
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [productFilter, setProductFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [products, setProducts] = useState<string[]>([]);
  const [detectors, setDetectors] = useState<Detector[]>([]);
  const [dialog, setDialog] = useState<DialogName | null>(null);
  const [runOpen, setRunOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [lightbox, setLightbox] = useState<LightboxImage | null>(null);
  const [event, setEvent] = useState<EvidenceTimelineEvent | null>(null);
  const [toast, setToast] = useState("");
  const [connected, setConnected] = useState(false);
  const [authNeeded, setAuthNeeded] = useState(false);
  const [theme, setTheme] = useState(localStorage.getItem("works.theme") || "light");
  const [density, setDensity] = useState(localStorage.getItem("works.density") || "comfortable");
  const [pollMs, setPollMs] = useState(Number(localStorage.getItem("works.poll") || 15000));
  const selectedRef = useRef<string | null>(null);
  const detailRef = useRef<AppDetail | null>(null);
  const toastTimer = useRef<number | null>(null);

  const notify = useCallback((message: string) => {
    setToast(message);
    window.clearTimeout(toastTimer.current ?? undefined);
    toastTimer.current = window.setTimeout(() => setToast(""), 4200);
  }, []);

  const loadTasks = useCallback(async () => {
    try {
      const data = await api.tasks(200);
      setTasks(data.tasks || []);
    } catch (error) {
      if (isUnauthorized(error)) {
        setAuthNeeded(true);
        return;
      }
      notify(`Queue unavailable: ${errorMessage(error)}`);
    }
  }, [notify]);

  const loadDetail = useCallback(async (id: string | null) => {
    if (!id) return;
    try {
      const data = await api.task(id);
      const next = appDetail(data);
      if (next && selectedRef.current === id) {
        setDetail(next);
        detailRef.current = next;
      }
    } catch (error) {
      notify(`Task unavailable: ${errorMessage(error)}`);
    }
  }, [notify]);

  const selectTask = useCallback((id: string, nextView: ViewId = view, push = false, at: number | null = null) => {
    if (!id) return;
    selectedRef.current = id;
    setSelected(id);
    setDetail((current) => (current?.task.id === id ? current : null));
    const hash = taskHash(id, nextView, at);
    if (push) history.pushState(null, "", hash);
    else history.replaceState(null, "", hash);
    loadDetail(id);
  }, [loadDetail, view]);

  const changeView = useCallback((next: string) => {
    if (!isViewId(next)) return;
    setView(next);
    localStorage.setItem("works.view.v3", next);
    if (selectedRef.current) selectTask(selectedRef.current, next);
  }, [selectTask]);

  const refresh = useCallback(async () => {
    await loadTasks();
    if (selectedRef.current) await loadDetail(selectedRef.current);
  }, [loadTasks, loadDetail]);

  async function runAction(action: string, body: Record<string, unknown> = {}): Promise<ActionResult | null> {
    const taskId = selectedRef.current;
    if (!taskId) return null;
    try {
      const response =
        action === "run-readiness"
          ? await api.readiness({ task_id: taskId })
          : await api.action({ action, task_id: taskId, ...body });
      let result = actionResult(response);
      if (response.job) {
        const job: Job = await waitForJob(response.job.id);
        if (job.status !== "succeeded") {
          throw new Error(job.error || `${action} did not finish`);
        }
        result = actionResult(job.result);
      }
      const count = result.messages?.length ?? 0;
      if (action === "discussion") notify("Team review added to the conversation.");
      else if (action === "commentary") notify("Agent commentary added to the conversation.");
      else if (action === "run-readiness") notify(`Readiness: ${result.status ?? "done"}.`);
      else if (count) notify(`${count} ${action} message(s) added.`);
      else if (result.event?.type === "thread.note") notify("Context added to the worklog.");
      else notify(`${action} recorded.`);
      await refresh();
      return result;
    } catch (error) {
      notify(`${action} failed: ${errorMessage(error)}`);
      throw error;
    }
  }

  useEffect(() => {
    const initial = parseHash();
    if (initial.view) setView(initial.view);
    Promise.all([api.health(), api.products(), api.detectors()])
      .then(([h, p, d]) => {
        setHealth(appHealth(h));
        setProducts(productNames(p.products));
        setDetectors(detectorList(d.detectors));
      })
      .catch((error: unknown) => {
        if (isUnauthorized(error)) {
          setAuthNeeded(true);
          return;
        }
        notify(`Works unavailable: ${errorMessage(error)}`);
      });
    loadTasks().then(() => {
      if (initial.taskId) selectTask(initial.taskId, initial.view || view, false, initial.at);
    });
  }, []);

  useEffect(() => {
    selectedRef.current = selected;
  }, [selected]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.density = density;
  }, [theme, density]);

  useEffect(() => {
    function applyHash() {
      const next = parseHash();
      if (!next.taskId) {
        setSelected(null);
        selectedRef.current = null;
        setDetail(null);
        return;
      }
      if (next.view) setView(next.view);
      selectTask(next.taskId, next.view || view, false, next.at);
    }
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, [selectTask, view]);

  useEffect(() => {
    const source = new EventSource("/api/v1/events");
    let timer: number | undefined;
    const schedule = () => {
      setConnected(true);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        loadTasks();
        if (selectedRef.current) loadDetail(selectedRef.current);
      }, 160);
    };
    const names = [
      "queue.changed",
      "task.changed",
      "run.changed",
      "job.changed",
      "settings.changed",
      "resync",
    ] as const;
    for (const name of names) source.addEventListener(name, schedule);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    return () => {
      for (const name of names) source.removeEventListener(name, schedule);
      source.close();
      window.clearTimeout(timer);
    };
  }, [loadTasks, loadDetail]);

  useEffect(() => {
    if (!pollMs) return undefined;
    const timer = window.setInterval(() => {
      loadTasks();
      if (selectedRef.current) loadDetail(selectedRef.current);
    }, pollMs);
    return () => window.clearInterval(timer);
  }, [pollMs, loadTasks, loadDetail]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const tag = document.activeElement?.tagName ?? "";
      const inField = ["INPUT", "TEXTAREA", "SELECT"].includes(tag);
      const modal = Boolean(document.querySelector("dialog[open]"));
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setDialog("palette");
        return;
      }
      if (event.key === "/" && !inField && !modal) {
        event.preventDefault();
        document.querySelector<HTMLInputElement>(".search input")?.focus();
        return;
      }
      if (!inField && !modal && event.key === "t") {
        setTheme((current) => current === "dark" ? "light" : "dark");
        return;
      }
      if (!inField && !modal && event.key === "?") {
        setDialog("help");
        return;
      }
      if (!inField && !modal && (event.key === "j" || event.key === "k") && tasks.length) {
        const index = tasks.findIndex((task) => task.id === selectedRef.current);
        const step = event.key === "j" ? 1 : -1;
        const next = tasks[(index + step + tasks.length) % tasks.length];
        if (next) selectTask(next.id, view);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tasks, view, selectTask]);

  const title = detail?.task.source.title || "A signal in, a released fix out";
  const subtitle = detail
    ? `${stateLabel(detail.task.state)} / reported ${timeAgo(detail.task.created_at)}`
    : "Select a report to read its story, proof and decision.";
  const crumb = detail ? crumbFor(view) : "Queue";

  if (authNeeded) {
    return <SignIn onSignedIn={() => window.location.reload()} />;
  }

  return (
    <div className="workspace">
      <AppHeader
        onFactory={() => setDialog("factory")}
        onPalette={() => setDialog("palette")}
        onSettings={() => setDialog("settings")}
      />
      <div className="app">
      <Queue
        tasks={tasks.map(queueTask)}
        selected={selected}
        onSelect={(id) => selectTask(id, view)}
        filter={filter}
        onFilter={setFilter}
        productFilter={productFilter}
        onProductFilter={setProductFilter}
        sourceFilter={sourceFilter}
        onSourceFilter={setSourceFilter}
        query={query}
        onQuery={setQuery}
        writable={Boolean(health?.write)}
        onNew={() => setDialog("new")}
      />
      <main className="main">
        <MainHead
          detail={detail}
          view={view}
          connected={connected}
          crumb={crumb}
          title={title}
          subtitle={subtitle}
          onQueue={() => {
            setSelected(null);
            selectedRef.current = null;
            setDetail(null);
            history.replaceState(null, "", "#/");
          }}
          onView={changeView}
        />
        <section className={`content ${view === "thread" ? "content-session" : ""}`}>
          {!detail ? (
            <div className="empty">
              <img src="/mira.svg" alt="" width="132" height="132" />
              <h2>Start with a report</h2>
              <p>Choose one on the left; its story, proof and next step open here.</p>
            </div>
          ) : (
            view === "thread" ? (
              <Thread
                key={detail.task.id}
                detail={detail}
                ai={health?.ai}
                writable={Boolean(health?.write)}
                onAction={runAction}
                onView={changeView}
                onRefresh={() => loadDetail(selectedRef.current)}
                onShowRun={() => setRunOpen(true)}
                onToast={notify}
              />
            ) : view === "evidence" ? (
              <Evidence
                key={detail.task.id}
                detail={detail}
                onShowRun={() => setRunOpen(true)}
                onAction={runAction}
                onLightbox={(url, alt) => setLightbox({ url, alt })}
                onOpenEvent={setEvent}
                onToast={notify}
              />
            ) : view === "release" ? (
              <Release
                key={detail.task.id}
                detail={detail}
                onAction={runAction}
                onShowRuns={() => setCompareOpen(true)}
                onShowRun={() => setRunOpen(true)}
                onToast={notify}
              />
            ) : (
              <Story
                key={detail.task.id}
                detail={detail}
                onView={changeView}
                onToast={notify}
                onShowRun={() => setRunOpen(true)}
              />
            )
          )}
        </section>
      </main>
      </div>

      {health?.write ? (
        <button className="btn report-btn mobile-new" type="button" onClick={() => setDialog("new")}>+ New task</button>
      ) : null}

      {dialog === "new" ? <NewTaskDialog products={[...new Set([...products, ...tasks.map((task) => task.product).filter(Boolean)])].sort()} onClose={() => setDialog(null)} onToast={notify} onCreated={(id: string) => { setDialog(null); loadTasks(); selectTask(id, "story"); }} /> : null}
      {dialog === "import" ? <ImportDialog products={products} detectors={detectors} onClose={() => setDialog(null)} onToast={notify} onImported={() => { setDialog(null); loadTasks(); }} /> : null}
      {dialog === "factory" ? <FactoryDialog onClose={() => setDialog(null)} /> : null}
      {dialog === "settings" ? (
        <SettingsDialog
          theme={theme}
          density={density}
          pollMs={pollMs}
          builder={health?.builder}
          writable={Boolean(health?.write)}
          onClose={() => setDialog(null)}
          onSave={async ({ theme: nextTheme, density: nextDensity, pollMs: nextPoll, repo, builder }) => {
            setTheme(nextTheme);
            setDensity(nextDensity);
            setPollMs(nextPoll);
            localStorage.setItem("works.theme", nextTheme);
            localStorage.setItem("works.density", nextDensity);
            localStorage.setItem("works.poll", String(nextPoll));
            localStorage.setItem("works.repo", repo.trim());
            if (builder && health?.write) {
              const result = await api.saveSettings(builder);
              setHealth((current) => current ? { ...current, builder: appBuilder(result.builder) } : current);
            }
            setDialog(null);
            notify("Settings saved.");
          }}
        />
      ) : null}
      {dialog === "help" ? <HelpDialog onClose={() => setDialog(null)} /> : null}
      {dialog === "palette" ? (
        <Palette
          tasks={tasks}
          writable={Boolean(health?.write)}
          onClose={() => setDialog(null)}
          onSelect={(id: string) => selectTask(id, view)}
          onAction={(action: string) => {
            if (action === "theme") { setTheme(theme === "dark" ? "light" : "dark"); setDialog(null); }
            else if (action === "density") { setDensity(density === "compact" ? "comfortable" : "compact"); setDialog(null); }
            else if (action === "refresh") { refresh(); setDialog(null); }
            else if (action === "new" || action === "import" || action === "factory" || action === "settings" || action === "help") setDialog(action);
          }}
        />
      ) : null}
      {runOpen ? <RunDialog detail={detail} onClose={() => setRunOpen(false)} /> : null}
      {compareOpen ? <CompareDialog detail={detail} onClose={() => setCompareOpen(false)} /> : null}
      {lightbox ? <Lightbox image={lightbox} onClose={() => setLightbox(null)} /> : null}
      {event ? <EventDialog event={event} onClose={() => setEvent(null)} /> : null}
      <Toast message={toast} />
    </div>
  );
}
