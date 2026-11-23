import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./lib/api.js";
import {
  CompareDialog, EventDialog, FactoryDialog, HelpDialog, ImportDialog,
  Lightbox, NewTaskDialog, Palette, RunDialog, SettingsDialog,
} from "./components/Dialogs.jsx";
import { Evidence } from "./components/Evidence.jsx";
import { Queue } from "./components/Queue.jsx";
import { Release } from "./components/Release.jsx";
import { Story } from "./components/Story.jsx";
import { Thread } from "./components/Thread.jsx";
import { Toast } from "./components/ui.jsx";
import { stateLabel, stateTone, timeAgo } from "./lib/format.js";

const viewNames = ["story", "evidence", "release", "thread"];

function parseHash() {
  const match = location.hash.match(/^#\/task\/([^/?]+)(?:\/(story|evidence|release|thread))?/);
  const query = match ? location.hash.split("?").slice(1).join("?") : "";
  const at = new URLSearchParams(query).get("at");
  return {
    taskId: match ? decodeURIComponent(match[1]) : null,
    view: match?.[2] || null,
    at: at != null && at !== "" ? Number(at) : null,
  };
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [view, setView] = useState(localStorage.getItem("works.view.v3") || "story");
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [productFilter, setProductFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [products, setProducts] = useState([]);
  const [detectors, setDetectors] = useState([]);
  const [dialog, setDialog] = useState(null);
  const [runOpen, setRunOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [lightbox, setLightbox] = useState(null);
  const [event, setEvent] = useState(null);
  const [toast, setToast] = useState("");
  const [connected, setConnected] = useState(false);
  const [theme, setTheme] = useState(localStorage.getItem("works.theme") || "light");
  const [density, setDensity] = useState(localStorage.getItem("works.density") || "comfortable");
  const [pollMs, setPollMs] = useState(Number(localStorage.getItem("works.poll") || 15000));
  const selectedRef = useRef(null);
  const detailRef = useRef(null);
  const toastTimer = useRef(null);

  const notify = useCallback((message) => {
    setToast(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 4200);
  }, []);

  const loadTasks = useCallback(async () => {
    try {
      const data = await api("/api/tasks?limit=200");
      setTasks(data.tasks || []);
    } catch (error) {
      notify(`Queue unavailable: ${error.message}`);
    }
  }, [notify]);

  const loadDetail = useCallback(async (id) => {
    if (!id) return;
    try {
      const data = await api(`/api/tasks/${encodeURIComponent(id)}`);
      if (selectedRef.current === id) {
        setDetail(data);
        detailRef.current = data;
      }
    } catch (error) {
      notify(`Task unavailable: ${error.message}`);
    }
  }, [notify]);

  const selectTask = useCallback((id, nextView = view, push = false, at = null) => {
    if (!id) return;
    selectedRef.current = id;
    setSelected(id);
    setDetail((current) => (current?.task?.id === id ? current : null));
    const suffix = nextView === "evidence" ? "/evidence" : nextView === "release" ? "/release" : nextView === "thread" ? "/thread" : "/story";
    const query = nextView === "story" && at != null ? `?at=${at}` : "";
    const hash = `#/task/${encodeURIComponent(id)}${suffix}${query}`;
    if (push) history.pushState(null, "", hash);
    else history.replaceState(null, "", hash);
    loadDetail(id);
  }, [loadDetail, view]);

  const changeView = useCallback((next) => {
    if (!viewNames.includes(next)) return;
    setView(next);
    localStorage.setItem("works.view.v3", next);
    if (selectedRef.current) selectTask(selectedRef.current, next);
  }, [selectTask]);

  const refresh = useCallback(async () => {
    await loadTasks();
    if (selectedRef.current) await loadDetail(selectedRef.current);
  }, [loadTasks, loadDetail]);

  async function runAction(action, body = {}) {
    if (!selectedRef.current) return null;
    try {
      const result = await api("/api/actions", {
        method: "POST",
        headers: { "X-Works-Write": "1" },
        body: { action, task_id: selectedRef.current, ...body },
      });
      const count = (result.messages || []).length;
      if (count) notify(`${count} ${action} message(s) added.`);
      else if (result.event?.type === "thread.note") notify("Context added to the worklog.");
      else notify(`${action} recorded.`);
      await refresh();
      return result;
    } catch (error) {
      notify(`${action} failed: ${error.message}`);
      throw error;
    }
  }

  useEffect(() => {
    const initial = parseHash();
    if (initial.view) setView(initial.view);
    Promise.all([api("/api/health"), api("/api/products"), api("/api/detectors")])
      .then(([h, p, d]) => {
        setHealth(h);
        setProducts((p.products || []).map((item) => item.name));
        setDetectors(d.detectors || []);
      })
      .catch((error) => notify(`Works unavailable: ${error.message}`));
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
    const source = new EventSource("/api/events");
    let timer;
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = () => {
      setConnected(true);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        loadTasks();
        if (selectedRef.current) loadDetail(selectedRef.current);
      }, 160);
    };
    return () => {
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
    function onKey(event) {
      const inField = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
      const modal = Boolean(document.querySelector("dialog[open]"));
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setDialog("palette");
        return;
      }
      if (event.key === "/" && !inField && !modal) {
        event.preventDefault();
        document.querySelector(".search input")?.focus();
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

  const title = detail?.task?.source?.title || "A signal in, a released fix out";
  const subtitle = detail
    ? `${stateLabel(detail.task.state)} / reported ${timeAgo(detail.task.created_at)}`
    : "Select a report to read its story, proof and decision.";
  const crumb = detail ? (view === "evidence" ? "Evidence" : view === "release" ? "Release" : view === "thread" ? "Thread" : "Story") : "Queue";

  return (
    <div className="workspace">
      <header className="appbar">
        <div className="appbar-brand">
          <span className="mark" aria-hidden="true">W</span>
          <div>
            <strong>openJiuwen Works</strong>
            <span>LOCAL FACTORY</span>
          </div>
        </div>
        <div className="appbar-actions">
          <button className="btn ghost" type="button" onClick={() => setDialog("factory")}>Factory</button>
          <button className="btn ghost" type="button" aria-label="Command palette" title="Command palette" onClick={() => setDialog("palette")}>Ctrl K</button>
          <button className="btn ghost" type="button" aria-label="Settings" title="Settings" onClick={() => setDialog("settings")}>Settings</button>
        </div>
      </header>
      <div className="app">
      <Queue
        tasks={tasks}
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
        <div className="sticky-top">
            <header className="main-head">
              <div className="head-copy">
                <div className="crumb">
                  <button type="button" className="crumb-link" onClick={() => { setSelected(null); selectedRef.current = null; setDetail(null); history.replaceState(null, "", "#/"); }}>Queue</button>
                  {detail ? <><span className="crumb-sep">/</span>{crumb}</> : null}
                </div>
                <h1>{title}</h1>
                <p>{subtitle}</p>
              </div>
            </header>
            {detail ? (
              <div className="view-tabs" role="tablist" aria-label="Detail view">
                {[["story", "Story"], ["evidence", "Evidence"], ["release", "Release"], ["thread", "Session"]].map(([id, label]) => (
                  <button key={id} type="button" role="tab" aria-selected={view === id} className={`view-tab ${view === id ? "active" : ""}`} onClick={() => changeView(id)}>{label}</button>
                ))}
                <span className={`cl-live ${connected ? "on" : ""}`} title={connected ? "Live updates connected" : "Reconnecting"} />
              </div>
            ) : null}
        </div>
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

      {dialog === "new" ? <NewTaskDialog products={[...new Set([...products, ...tasks.map((task) => task.product).filter(Boolean)])].sort()} onClose={() => setDialog(null)} onToast={notify} onCreated={(id) => { setDialog(null); loadTasks(); selectTask(id, "story"); }} /> : null}
      {dialog === "import" ? <ImportDialog products={products} detectors={detectors} onClose={() => setDialog(null)} onToast={notify} onImported={() => { setDialog(null); loadTasks(); }} /> : null}
      {dialog === "factory" ? <FactoryDialog onClose={() => setDialog(null)} /> : null}
      {dialog === "settings" ? (
        <SettingsDialog
          theme={theme}
          density={density}
          pollMs={pollMs}
          onClose={() => setDialog(null)}
          onSave={({ theme: nextTheme, density: nextDensity, pollMs: nextPoll, repo }) => {
            setTheme(nextTheme);
            setDensity(nextDensity);
            setPollMs(nextPoll);
            localStorage.setItem("works.theme", nextTheme);
            localStorage.setItem("works.density", nextDensity);
            localStorage.setItem("works.poll", String(nextPoll));
            localStorage.setItem("works.repo", repo.trim());
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
          onSelect={(id) => selectTask(id, view)}
          onAction={(action) => {
            if (action === "theme") { setTheme(theme === "dark" ? "light" : "dark"); setDialog(null); }
            else if (action === "density") { setDensity(density === "compact" ? "comfortable" : "compact"); setDialog(null); }
            else if (action === "refresh") { refresh(); setDialog(null); }
            else setDialog(action);
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
