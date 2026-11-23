const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  tasks: [],
  selected: null,
  detail: null,
  filter: "all",
  productFilter: "",
  sourceFilter: "",
  query: "",
  view: localStorage.getItem("works.view.v3") || "story",
  storyAt: null,
  storySelected: null,
  storyTimer: null,
  writable: false,
  ai: null,
  composeMode: "ask",
  pollMs: Number(localStorage.getItem("works.poll") || 15000),
  pollTimer: null,
  timelineFilter: "all",
  products: null,
  detectors: null,
};

const stateHuman = {
  queued: "Waiting in queue",
  reproducing: "Confirming the problem",
  reproduced: "Problem confirmed",
  planning: "Planning the fix",
  plan_approved: "Plan approved",
  building: "Fixing it now",
  checking: "Checking it now",
  proved: "Ready for release",
  waiting_review: "Waiting for a person",
  waiting_ci: "Running checks",
  waiting_deploy: "Delivering the fix",
  releasing: "Delivering the fix",
  released: "Delivered",
  reverted: "Reverted",
  blocked: "Needs attention",
  done: "Done",
  active: "In progress",
  pending: "Not yet",
};

const timelineHuman = {
  "task.created": "Reported",
  "state.changed": "Stage changed",
  "step.started": "Step started",
  "step.finished": "Step finished",
  "plan.drafted": "Plan drafted",
  "gate.decided": "Approval recorded",
  "attempt.started": "Attempt started",
  "challenge.decided": "Independent check",
  "risk.rated": "Risk assessed",
  "decision.made": "Decision recorded",
  "decision.shadow": "Shadow comparison",
  "would_block": "Observed block",
  flake: "Flake recorded",
  "wait.started": "Waiting",
  "wait.woken": "Woke up",
  "wait.expired": "Wait expired",
  finding: "Finding recorded",
  note: "Run finished",
  "memory.reported": "PPMA memory",
  "memory.failed": "PPMA memory failed",
  "memory.recalled": "Memory recall",
  "memory.recall_failed": "Memory recall failed",
  "readiness.checked": "Readiness checked",
  "team.verified": "Verification team",
  "delivery.finished": "Delivered",
  "confirmation.finished": "Confirmed",
  "thread.note": "Context added",
  "thread.agent": "Mira answered",
  "thread.commentary": "AI commentary",
};

const groupDefs = [
  ["needs", "Needs you", ["blocked", "waiting_review", "waiting_ci", "waiting_deploy", "proved"]],
  ["working", "In progress", ["reproducing", "reproduced", "planning", "plan_approved", "building", "checking", "releasing"]],
  ["queued", "Queued", ["queued"]],
  ["done", "Done", ["released", "reverted"]],
];

const themeKey = "works.theme";
const densityKey = "works.density";

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmtUsd(value) {
  const number = Number(value ?? 0);
  return `$${number.toFixed(number >= 10 ? 2 : 4)}`;
}

function fmtMs(value) {
  const number = Number(value ?? 0);
  if (number < 1000) return `${number} ms`;
  if (number < 60_000) return `${(number / 1000).toFixed(1)} s`;
  return `${Math.round(number / 60_000)} min`;
}

function timeAgo(iso) {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86_400)}d ago`;
}

function stateLabel(value) {
  return stateHuman[value] || String(value ?? "unknown").replaceAll("_", " ");
}

function sourceLabel(kind) {
  return { manual: "Reported", tracker: "Tracker", detector: "Monitoring" }[kind] || kind;
}

function decisionLabel(verb) {
  return {
    act: "Proceed",
    ask: "A person needs to decide",
    wait: "Wait",
    verify: "Verify again",
    escalate: "Escalate",
    observe: "Observe",
    guide: "Guide",
  }[verb] || verb;
}

function riskLabel(level) {
  return { low: "Low risk", medium: "Medium risk", high: "High risk" }[level] || level;
}

function priorityLabel(priority) {
  return { P0: "Must-pass", P1: "Optional" }[priority] || priority;
}

function gateLabel(gate) {
  return { plan: "Plan approval", release: "Release approval" }[gate] || gate;
}

function timelineLabel(type) {
  return timelineHuman[type] || String(type).replaceAll("_", " ");
}

function stateTone(value) {
  if (["proved", "released"].includes(value)) return "green";
  if (["blocked", "reverted", "flaky_test"].includes(value)) return "red";
  if (["waiting_review", "waiting_ci", "waiting_deploy", "needs_plan_approval"].includes(value)) return "amber";
  if (["planning", "plan_approved", "building", "checking", "reproducing"].includes(value)) return "violet";
  return "";
}

function riskTone(value) {
  if (value === "high") return "red";
  if (value === "medium") return "amber";
  if (value === "low") return "green";
  return "";
}

function pill(text, tone = "") {
  return `<span class="pill ${tone}">${esc(text)}</span>`;
}

function card(title, body, options = {}) {
  const actions = options.actions ? `<div class="small faint">${options.actions}</div>` : "";
  return `<section class="card">
    <header class="card-head"><h2>${esc(title)}</h2>${actions}</header>
    <div class="card-body ${options.tight ? "tight" : ""}">${body}</div>
    ${options.after ?? ""}
  </section>`;
}

function table(headers, rows, numeric = []) {
  if (!rows.length) return `<p class="muted small">Nothing recorded.</p>`;
  const head = headers.map((item) => `<th>${esc(item)}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = row
        .map((cell, index) => {
          const cls = numeric.includes(index) ? ' class="num"' : "";
          return `<td${cls}>${cell}</td>`;
        })
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function commandRows(evidence) {
  return ["reproduce", "test", "preview"]
    .map((key) => evidence?.[key])
    .filter(Boolean)
    .map((command) => [
      esc(command.step),
      `<span class="mono">${esc((command.argv || []).join(" "))}</span>`,
      command.exit_code === 0 ? '<span class="ok">PASS</span>' : '<span class="bad">FAIL</span>',
      esc(fmtMs(command.duration_ms)),
    ]);
}

function diffBlock(diff) {
  if (!diff) return `<p class="muted small">No diff recorded.</p>`;
  const lines = diff.split("\n").map((line) => {
    const cls = line.startsWith("+") && !line.startsWith("+++") ? "add"
      : line.startsWith("-") && !line.startsWith("---") ? "del" : "";
    return `<span class="${cls}">${esc(line)}</span>`;
  });
  return `<pre class="diff">${lines.join("\n")}</pre>`;
}

async function api(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  let body = options.body;
  if (body && typeof body !== "string") {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  const response = await fetch(path, { ...options, headers, body });
  const parsed = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(parsed.error || `${response.status} ${response.statusText}`);
  return parsed;
}

async function performAction(button, action, body, message) {
  button.disabled = true;
  try {
    const result = await api("/api/actions", {
      method: "POST",
      headers: { "X-Works-Write": "1" },
      body: { action, task_id: state.selected, ...body },
    });
    toast(message(result));
    await loadDetail(state.selected);
    await loadTasks();
  } catch (error) {
    toast(`${action} failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

async function loadFactory() {
  const body = $("#factory-body");
  body.innerHTML = `<p class="muted small">Loading factory metrics…</p>`;
  try {
    const [metrics, ledger] = await Promise.all([api("/api/metrics"), api("/api/ledger")]);
    const m = metrics.metrics || {};
    const cards = [
      ["Tasks", m.tasks ?? 0],
      ["Proved", m.proved ?? 0],
      ["Blocked", m.blocked ?? 0],
      ["Human touches", m.human_touches ?? 0],
      ["Runs without human", m.runs_without_human ?? 0],
      ["Median wall", fmtMs(m.median_duration_ms ?? 0)],
      ["Tokens", m.tokens ?? 0],
      ["USD", fmtUsd(m.usd ?? 0)],
    ]
      .map(([label, value]) => `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`)
      .join("");
    const rows = (ledger.rows || [])
      .slice()
      .reverse()
      .slice(0, 30)
      .map((row) => [
        esc(new Date(row.ts).toLocaleString()),
        `<span class="mono">${esc(row.task_id)}</span>`,
        esc(row.state),
        esc(row.verdict || "—"),
        esc(row.tokens ?? 0),
        esc(fmtUsd(row.usd ?? 0)),
      ]);
    body.innerHTML = `<div class="metrics-grid">${cards}</div>
      <h3 class="factory-subtitle">Ledger</h3>
      ${table(["Time", "Task", "State", "Verdict", "Tokens", "USD"], rows, [4, 5])}`;
  } catch (error) {
    body.innerHTML = `<p class="bad small">${esc(error.message)}</p>`;
  }
}

function openFactory() {
  $("#factory-dialog").showModal();
  void loadFactory();
}

function openSettings() {
  const form = $("#settings-form");
  form.elements.theme.value = document.documentElement.dataset.theme || "dark";
  form.elements.density.value = document.documentElement.dataset.density || "comfortable";
  form.elements.poll.value = String(state.pollMs);
  form.elements.repo.value = localStorage.getItem("works.repo") || "";
  $("#settings-dialog").showModal();
}

function saveSettings(event) {
  event.preventDefault();
  const form = event.currentTarget;
  applyTheme(form.elements.theme.value);
  applyDensity(form.elements.density.value);
  state.pollMs = Number(form.elements.poll.value);
  localStorage.setItem("works.poll", String(state.pollMs));
  localStorage.setItem("works.repo", form.elements.repo.value.trim());
  $("#settings-dialog").close();
  startPolling();
  toast("Settings saved.");
}

function startPolling() {
  if (state.pollTimer) window.clearInterval(state.pollTimer);
  state.pollTimer = window.setInterval(() => {
    loadTasks();
    if (state.selected) loadDetail(state.selected);
  }, state.pollMs);
}

function openLightbox(url, alt) {
  const image = $("#lightbox-image");
  image.src = url;
  image.alt = alt || "artifact";
  $("#lightbox").showModal();
}

function openEventDialog(seq) {
  const detail = state.detail;
  if (!detail) return;
  const event = (detail.timeline || []).find((item) => item.seq === seq);
  if (!event) return;
  $("#event-dialog-body").textContent = JSON.stringify(event, null, 2);
  $("#event-dialog").showModal();
}

function openRunDialog() {
  const detail = state.detail;
  if (!detail) return;
  const run = detail.run || {};
  const evidence = detail.evidence || {};
  const verdict = evidence.verdict || {};
  const risk = evidence.risk || {};
  const lines = [
    `Run:          ${run.run_id || "—"}`,
    `Flow:         ${run.flow || "—"}`,
    `Base commit:  ${run.base_commit || "—"}`,
    `Checks SHA:   ${run.checks_sha || "—"}`,
    `Proof SHA:    ${evidence.proof_sha256 || "—"}`,
    `Verdict:      ${verdict.allow ? "allow" : evidence.verdict ? "block" : "—"}`,
    `Risk:         ${risk.level || "—"}`,
    `Files:        ${(evidence.files_changed || []).join(", ") || "—"}`,
    `Not tested:   ${(evidence.not_tested || []).join(", ") || "none recorded"}`,
    `Tokens:       ${evidence.tokens ?? 0}`,
    `USD:          ${fmtUsd(evidence.usd ?? 0)}`,
  ];
  $("#run-dialog-body").textContent = lines.join("\n");
  $("#run-dialog").showModal();
}

async function refreshDetectors() {
  try {
    state.detectors = await api("/api/detectors?refresh=1");
    if (state.detail) renderDetail();
  } catch (error) {
    toast(`Detectors unavailable: ${error.message}`);
  }
}

async function streamAsk(question, button) {
  const line = $(".thread-line");
  if (!line) throw new Error("worklog is not open");
  const id = `ask-live-${Date.now()}`;
  line.insertAdjacentHTML(
    "beforeend",
    `<div class="thread-msg mira" id="${id}">
      <div class="thread-avatar" aria-hidden="true">M</div>
      <div class="thread-body">
        <div class="thread-meta"><b>Mira</b><time>now</time></div>
        <h3>Mira is answering…</h3>
        <p class="ask-live-text"></p>
      </div>
    </div>`,
  );
  const textNode = line.querySelector(`#${id} .ask-live-text`);
  button.disabled = true;
  try {
    const response = await fetch("/api/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Works-Write": "1" },
      body: JSON.stringify({ task_id: state.selected, question }),
    });
    if (!response.ok || !response.body) {
      throw new Error((await response.text()) || `${response.status} ${response.statusText}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finished = false;
    while (!finished) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let index;
      while ((index = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, index);
        buffer = buffer.slice(index + 2);
        for (const raw of block.split("\n")) {
          if (!raw.startsWith("data:")) continue;
          const event = JSON.parse(raw.slice(5).trim());
          if (event.type === "delta") textNode.textContent += event.text || "";
          else if (event.type === "error") throw new Error(event.error || "Mira failed");
          else if (event.type === "done") finished = true;
        }
      }
    }
    if (!finished) throw new Error("stream ended without an answer");
    await loadDetail(state.selected);
  } catch (error) {
    document.getElementById(id)?.remove();
    toast(`Mira: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => node.classList.remove("show"), 4200);
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(themeKey, theme);
}

function applyDensity(density) {
  document.documentElement.dataset.density = density;
  localStorage.setItem(densityKey, density);
}

function renderTasks() {
  const list = $("#task-list");
  const query = state.query.trim().toLowerCase();
  const states = Object.fromEntries(groupDefs.map(([id, , group]) => [id, group]));
  const tasks = state.tasks.filter((task) => {
    if (state.filter !== "all" && !(states[state.filter] || []).includes(task.state)) return false;
    if (state.productFilter && task.product !== state.productFilter) return false;
    if (state.sourceFilter && String(task.source || "").split(":")[0] !== state.sourceFilter) return false;
    if (!query) return true;
    return [task.title, task.id, task.source, task.product, task.flow, stateLabel(task.state)]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
  if (!tasks.length) {
    list.innerHTML = `<p class="muted small" style="padding:16px 12px">No tasks match.</p>`;
    return;
  }
  const html = groupDefs
    .map(([id, label, group]) => {
      const rows = tasks.filter((task) => group.includes(task.state));
      if (!rows.length) return "";
      const items = rows
        .map((task) => {
          const active = task.id === state.selected ? " active" : "";
          const risk = task.risk && task.risk !== "low" ? pill(riskLabel(task.risk), riskTone(task.risk)) : "";
          const title = task.title || `Task ${task.id}`;
          const mark = `<span class="product-mark ${esc(task.state)}" aria-hidden="true">${esc((task.product || "?")[0])}</span>`;
          const meta = `${esc(task.product)} · ${esc(stateLabel(task.state))}`;
          return `<button type="button" class="task${active}" data-id="${esc(task.id)}"${
            active ? ' aria-current="true"' : ""
          }>
            ${mark}
            <span class="task-main">
              <span class="task-title">${esc(title)}</span>
              <span class="task-meta">${meta}</span>
            </span>
            <span class="task-side">${risk}<span class="time">${esc(timeAgo(task.updated_at))}</span></span>
          </button>`;
        })
        .join("");
      return `<div class="group-label">${esc(label)}<span>${rows.length}</span></div>${items}`;
    })
    .join("");
  list.innerHTML = html || `<p class="muted small" style="padding:16px 12px">No tasks match.</p>`;
  $$("#task-list .task").forEach((button) => {
    button.addEventListener("click", () => selectTask(button.dataset.id));
  });
}

function renderEmptyProof() {
  return `<div class="card"><div class="card-body">
    <div class="empty" style="margin:10px auto 22px">
      <img src="/mira.svg" alt="" width="64" height="64" />
      <h2>No proof yet</h2>
      <p>This task has not produced a run. The queue is the truth; the proof appears when a run finishes.</p>
    </div>
  </div></div>`;
}

function renderVerdict(evidence) {
  const verdict = evidence?.verdict;
  if (!verdict) return card("Verdict", `<p class="muted small">No verdict was produced.</p>`);
  const rows = (verdict.outcomes || []).map((outcome) => [
    `<span class="mono">${esc(outcome.id)}</span>`,
    esc(outcome.priority),
    outcome.passed ? '<span class="ok">PASS</span>' : '<span class="bad">FAIL</span>',
    esc(outcome.exit_code),
    esc(fmtMs(outcome.duration_ms)),
  ]);
  const tone = verdict.allow ? "green" : "red";
  return card(
    "Verdict",
    `<div class="split" style="margin-bottom:10px">
      ${pill(verdict.allow ? "ALLOW" : "BLOCK", tone)}
      <span class="muted small">${esc(verdict.reason || "")}</span>
    </div>
    ${table(["Scenario", "Priority", "Result", "Exit", "Time"], rows, [3, 4])}`,
    { actions: `p1 rate ${esc((verdict.p1_pass_rate * 100).toFixed(0))}%` },
  );
}

function renderRisk(evidence) {
  const risk = evidence?.risk;
  if (!risk) return card("Risk", `<p class="muted small">No risk rating recorded.</p>`);
  const reasons = (risk.reasons || []).map((reason) => `<li>${esc(reason)}</li>`).join("");
  const owners = (risk.owners || []).map((owner) => `<code>${esc(owner)}</code>`).join(", ");
  return card(
    "Risk",
    `<div class="split">
      ${pill(risk.level.toUpperCase(), riskTone(risk.level))}
      <span class="muted small">${esc(risk.files)} file(s) · ${esc(risk.lines)} line(s)</span>
    </div>
    <ul class="small muted" style="margin:12px 0 10px; padding-left:18px">${reasons}</ul>
    <dl class="kv">
      <dt>Owners</dt><dd>${owners || "—"}</dd>
      <dt>Reviewers</dt><dd>${esc(risk.required_reviewers ?? 1)}${risk.deeper_verification ? " · deeper verification" : ""}</dd>
    </dl>`,
  );
}

function renderDecision(evidence) {
  const decision = evidence?.decision;
  if (!decision) return card("Decision", `<p class="muted small">No gate decision recorded.</p>`);
  const alternatives = (decision.alternatives || []).map((item) => `<code>${esc(item)}</code>`).join(", ");
  return card(
    "Decision",
    `<div class="split">
      ${pill(decision.verb.toUpperCase(), "violet")}
      ${decision.requires_approval ? pill("APPROVAL REQUIRED", "amber") : pill("NO APPROVAL", "green")}
    </div>
    <dl class="kv" style="margin-top:12px">
      <dt>Reason</dt><dd><code>${esc(decision.reason_code)}</code></dd>
      <dt>Confidence</dt><dd>${esc(Number(decision.confidence ?? 0).toFixed(2))}</dd>
      <dt>Source</dt><dd>${esc(decision.source)}</dd>
      <dt>Decision id</dt><dd class="mono">${esc(decision.decision_id || "—")}</dd>
      <dt>Alternatives</dt><dd>${alternatives || "—"}</dd>
    </dl>`,
  );
}

function renderReadiness(detail) {
  const readiness = detail.readiness;
  if (!readiness?.available) return card("Readiness", `<p class="muted small">Not available.</p>`);
  const checks = (readiness.checks || [])
    .map((check) => {
      const stateClass = check.status || (check.ok ? "pass" : "fail");
      const mark = stateClass === "skip" ? "–" : stateClass === "pass" ? "✓" : "!";
      return `<div class="check ${stateClass}">
      <span class="box" aria-hidden="true">${mark}</span>
      <span>${esc(check.label)}</span>
      ${check.detail ? `<span class="check-detail" title="${esc(check.detail)}">${esc(check.detail)}</span>` : ""}
    </div>`;
    })
    .join("");
  const ratio = readiness.total ? Math.round((readiness.passed / readiness.total) * 100) : 0;
  const cycles = (readiness.import_cycles || [])
    .map((cycle) => `<li>${cycle.map((item) => `<span class="mono">${esc(item)}</span>`).join(" → ")} → start</li>`)
    .join("");
  const edges = Object.entries(readiness.import_edges || {})
    .map(([source, targets]) => `<li><span class="mono">${esc(source)}</span> → ${targets.map((item) => `<span class="mono">${esc(item)}</span>`).join(", ")}</li>`)
    .join("");
  const graph = edges
    ? `<details class="graph"><summary>Import graph · ${esc(Object.keys(readiness.import_edges || {}).length)} module(s)</summary><ul class="small muted">${edges}</ul></details>`
    : "";
  const run = state.writable
    ? `<button type="button" class="btn ghost" data-action="run-readiness">Run checks</button>`
    : "";
  return card(
    "Readiness",
    `${checks}
    <div class="progress"><i style="width:${ratio}%"></i></div>
    <p class="muted small" style="margin:10px 0 0">${esc(readiness.note)}</p>
    ${cycles ? `<p class="bad small" style="margin:10px 0 4px">Import cycles</p><ul class="small">${cycles}</ul>` : ""}
    ${graph}
    ${run}`,
    { actions: `${esc(readiness.passed)}/${esc(readiness.total)}` },
  );
}

function renderFeatures(detail) {
  const features = detail.features;
  if (!features?.available) {
    return card("Feature coverage", `<p class="muted small">${esc(features?.note || "No feature map yet.")}</p>`);
  }
  if (features.error) {
    return card("Feature coverage", `<p class="muted small">${esc(features.error)}</p>`);
  }
  const rows = (features.features || [])
    .map((feature) => {
      const stateClass = feature.passed ? "pass" : feature.covered ? "fail" : "skip";
      const mark = feature.passed ? "✓" : feature.covered ? "!" : "–";
      const status = feature.passed ? "covered" : feature.covered ? "failed" : "not covered";
      return `<div class="check ${stateClass}">
        <span class="box" aria-hidden="true">${mark}</span>
        <span class="feature-copy"><strong>${esc(feature.name)}</strong><em>${esc(feature.expected)}</em></span>
        <span class="check-detail">${esc(status)}</span>
      </div>`;
    })
    .join("");
  const ratio = features.total ? Math.round((features.covered / features.total) * 100) : 0;
  return card(
    "Feature coverage",
    `${rows}
    <div class="progress"><i style="width:${ratio}%"></i></div>
    <p class="muted small" style="margin:10px 0 0">${esc(features.note)}</p>`,
    { actions: `${features.covered}/${features.total}` },
  );
}

function renderArtifacts(detail) {
  const artifacts = detail.artifacts || [];
  if (!artifacts.length) {
    return card("Runtime artifacts", `<p class="muted small">No screenshot, log, video or trace was attached to this proof.</p>`);
  }
  const images = artifacts.filter((item) => item.kind === "image");
  const before = images.find((item) => /before/i.test(item.name || item.path));
  const after = images.find((item) => /after/i.test(item.name || item.path));
  const compare =
    before && after
      ? `<div class="artifact-compare-wrap" style="--pos:50%">
           <div class="artifact-compare-stage">
             <img src="${esc(before.url)}" alt="before the fix" loading="lazy" />
             <img class="compare-after" src="${esc(after.url)}" alt="after the fix" loading="lazy" />
           </div>
           <input type="range" min="0" max="100" value="50" data-compare aria-label="Before and after" />
           <div class="compare-labels"><span>Before</span><span>After</span></div>
         </div>`
      : "";
  const rows = artifacts
    .map((item) => {
      const sha = item.sha256 ? ` · ${esc(shortSha(item.sha256))}` : "";
      let preview = "";
      if (item.kind === "image") {
        preview = `<img class="artifact-thumb" src="${esc(item.url)}" data-lightbox="${esc(item.url)}" alt="${esc(item.name)}" loading="lazy" />`;
      } else if (item.kind === "video") {
        preview = `<video class="artifact-video" controls preload="metadata" src="${esc(item.url)}"></video>`;
      } else if (item.kind === "log" || item.kind === "trace") {
        preview = `<details class="artifact-text" data-artifact-url="${esc(item.url)}"><summary>${esc(item.kind)}</summary><pre>Loading…</pre></details>`;
      }
      return `<div class="artifact-row">
        <div class="artifact-main"><strong>${esc(item.kind)}</strong><span class="mono small">${esc(item.path)}</span></div>
        ${preview || `<a href="${esc(item.url)}" target="_blank" rel="noopener">open</a>`}
        <span class="check-detail">${sha || ""}</span>
      </div>`;
    })
    .join("");
  return card("Runtime artifacts", `${compare}${rows}`, { actions: `${artifacts.length}` });
}

function renderMemoryRecall(evidence) {
  const statements = evidence?.memory_recall || [];
  if (!statements.length) {
    return card("Memory recall", `<p class="muted small">No memory statements were used for this run.</p>`);
  }
  return card(
    "Memory recall",
    `<ul class="big-list">${statements.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`,
    { actions: `${statements.length}` },
  );
}

function renderFindings(evidence) {
  const rows = (evidence?.findings || []).map((finding) => [
    esc(finding.step || "—"),
    esc(finding.summary),
    finding.confidence == null ? "—" : esc(Number(finding.confidence).toFixed(2)),
    esc(finding.uncertainty || "—"),
  ]);
  return card("Findings", table(["Step", "Finding", "Confidence", "Uncertainty"], rows, [2]));
}

function renderChallenge(evidence) {
  const challenge = evidence?.challenge;
  if (!challenge) return card("Challenge", `<p class="muted small">No independent challenge was run.</p>`);
  const concerns = (challenge.concerns || []).map((item) => `<li>${esc(item)}</li>`).join("");
  return card(
    "Challenge",
    `<div class="split" style="margin-bottom:10px">
      ${pill(challenge.allow ? "ALLOW" : "BLOCK", challenge.allow ? "green" : "red")}
      <span class="muted small">${esc(challenge.reason || "")}</span>
    </div>
    ${concerns ? `<ul class="small muted" style="margin:0; padding-left:18px">${concerns}</ul>` : ""}
    <p class="faint small mono" style="margin:10px 0 0">${esc(challenge.model)} · ${esc(challenge.provider)}</p>`,
  );
}

function renderCommands(evidence) {
  const rows = commandRows(evidence);
  return card("Commands", table(["Step", "Command", "Result", "Time"], rows, [3]), {
    actions: "reproduce must fail on base; test must pass after",
  });
}

function renderChange(evidence) {
  const rows = (evidence?.diff_stat || []).map((row) => [
    `<span class="mono">${esc(row.path)}</span>`,
    row.added < 0 ? "binary" : esc(row.added),
    row.removed < 0 ? "binary" : esc(row.removed),
  ]);
  const diff = evidence?.diff || "";
  const body = rows.length
    ? table(["File", "+", "-"], rows, [1, 2]) + diffBlock(diff)
    : `<p class="muted small">No change was produced.</p>`;
  return card("Change", body, { actions: `${esc((evidence?.files_changed || []).length)} files` });
}

function renderPolicy(evidence) {
  const policy = evidence?.policy;
  if (!policy) return card("Policy", `<p class="muted small">No policy report.</p>`);
  if (policy.ok) return card("Policy", `<p class="ok small">No violations.</p>`);
  const rows = (policy.violations || []).map((violation) => [
    `<span class="mono">${esc(violation.path)}</span>`,
    esc(violation.reason),
  ]);
  return card("Policy", table(["Path", "Reason"], rows));
}

function renderResidual(evidence) {
  const notTested = (evidence?.not_tested || []).map((item) => `<li>${esc(item)}</li>`).join("");
  const would = (evidence?.would_block || [])
    .map((item) => `<li>Observe mode would block: ${esc(item)}</li>`)
    .join("");
  return card(
    "Residual risk",
    `<ul class="small muted" style="margin:0; padding-left:18px">
      ${notTested || "<li>Not tested: none recorded.</li>"}
      ${would}
    </ul>`,
  );
}

function renderCost(evidence) {
  if (!evidence) return card("Cost", `<p class="muted small">No cost recorded.</p>`);
  return card(
    "Cost",
    `<div class="summary" style="grid-template-columns:1fr 1fr; margin:0">
      <div><div class="label">Tokens</div><div class="big">${esc(evidence.tokens)}</div></div>
      <div><div class="label">USD</div><div class="big">${esc(fmtUsd(evidence.usd))}</div></div>
      <div><div class="label">Wall</div><div class="big">${esc(fmtMs(evidence.duration_ms))}</div></div>
      <div><div class="label">Model</div><div class="small muted" style="margin-top:8px">${esc(evidence.model || "—")}</div></div>
    </div>`,
  );
}

function shortSha(value) {
  const text = String(value || "");
  return text ? text.slice(0, 12) : "—";
}

function externalLink(url, label = "open") {
  if (!url) return "";
  return `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a>`;
}

function renderReleasePacket(detail) {
  const release = detail.release || {};
  const blockers = (release.blockers || [])
    .map((item) => `<li>${esc(item)}</li>`)
    .join("");
  const commit = release.commit || detail.evidence?.base_commit || "—";
  const rows = [
    ["Commit", `<span class="mono">${esc(shortSha(commit))}</span>`],
    ["Proof SHA-256", `<span class="mono">${esc(shortSha(release.proof_sha256))}</span>`],
    ["Plan gate", release.plan_gate ? pill("APPROVED", "green") : pill("MISSING", "red")],
    ["Release gate", release.released ? pill("RELEASED", "green") : pill("NOT YET", "")],
    ["Packet", release.ready ? pill("READY", "green") : pill("BLOCKED", "red")],
  ];
  const action =
    state.writable && release.ready && !release.released
      ? `<button type="button" class="btn" data-action="release">Release this commit</button>`
      : release.released
        ? `<p class="ok small" style="margin:0">Gate 2 is open. Delivery is the next step.</p>`
        : state.writable
          ? `<p class="muted small" style="margin:0">A blocker must be resolved before a person can release this commit.</p>`
          : "";
  return card(
    "Release packet",
    `${table(["Field", "Value"], rows)}
     ${blockers ? `<ul class="small bad-list">${blockers}</ul>` : ""}
     ${action}`,
    { actions: release.ready ? "ready" : "blocked" },
  );
}

function renderDelivery(detail) {
  const delivery = detail.delivery;
  const released = detail.task.state === "released";
  if (!delivery) {
    const form = state.writable && released
      ? `<div class="form-row">
           <label>Forge
             <select id="deliver-provider">
               <option value="none">branch only</option>
               <option value="github">GitHub pull request</option>
               <option value="gitlab">GitLab merge request</option>
             </select>
           </label>
           <label>Tracker
             <select id="deliver-tracker">
               <option value="">follow the forge</option>
               <option value="none">no comment</option>
               <option value="github">GitHub issue</option>
               <option value="gitlab">GitLab issue</option>
               <option value="jira">Jira issue</option>
             </select>
           </label>
           <label class="inline"><input type="checkbox" id="deliver-dry" /> dry run</label>
         </div>
         <button type="button" class="btn" data-action="deliver">Deliver</button>`
      : `<p class="muted small" style="margin:0">${
          released
            ? "Gate 2 is open. Start the write UI to deliver."
            : "Delivery waits for the release gate."
        }</p>`;
    return card("Delivery", `<p class="muted small" style="margin:0 0 10px">No branch has been pushed for this run.</p>${form}`);
  }
  const rows = [
    ["Branch", `<span class="mono">${esc(delivery.branch || "—")}</span>`],
    ["Commit", `<span class="mono">${esc(shortSha(delivery.commit))}</span>`],
    ["Forge", esc(delivery.provider || "none")],
    ["Tracker", esc(delivery.tracker || "none")],
    ["Pull / merge request", externalLink(delivery.pr_url, delivery.provider === "gitlab" ? "merge request" : "pull request") || "—"],
    ["Source comment", externalLink(delivery.comment_url) || "—"],
    ["Pushed", delivery.pushed ? pill("YES", "green") : pill("NO", "")],
  ];
  const notes = (delivery.notes || []).map((note) => `<li>${esc(note)}</li>`).join("");
  const again =
    state.writable && delivery.dry_run
      ? `<div class="form-row">
           <input type="hidden" id="deliver-provider" value="${esc(delivery.provider || "none")}" />
           <input type="hidden" id="deliver-tracker" value="${esc(delivery.tracker || "")}" />
           <input type="hidden" id="deliver-dry" value="0" />
         </div>
         <button type="button" class="btn" data-action="deliver">Push this commit</button>`
      : "";
  return card(
    "Delivery",
    `${table(["Field", "Value"], rows)}
     ${notes ? `<ul class="small muted">${notes}</ul>` : ""}
     ${delivery.dry_run ? `<p class="warn small">This was a dry run; nothing was pushed.</p>` : ""}
     ${again}`,
    { actions: delivery.dry_run ? "dry run" : "delivered" },
  );
}

function renderConfirmation(detail) {
  const confirmation = detail.confirmation;
  const delivery = detail.delivery;
  if (!confirmation) {
    if (!delivery) {
      return card("Confirmation", `<p class="muted small" style="margin:0">Deliver the fix before confirming it.</p>`);
    }
    const form = state.writable
      ? `<div class="form-row">
           <label>HTTP check
             <input id="confirm-url" placeholder="https://app.example/health" autocomplete="off" />
           </label>
           <label>or command
             <input id="confirm-command" placeholder='["python","-m","pytest"]' autocomplete="off" />
           </label>
         </div>
         <div class="form-row">
           <label>Tracker
             <select id="confirm-tracker">
               <option value="">none</option>
               <option value="github">GitHub issue</option>
               <option value="gitlab">GitLab issue</option>
               <option value="jira">Jira issue</option>
             </select>
           </label>
           <label class="inline"><input type="checkbox" id="confirm-close" /> close on success</label>
         </div>
         <p class="muted small" style="margin:0 0 10px">No target: the plan's scenario set is re-run.</p>
         <button type="button" class="btn" data-action="confirm">Confirm</button>`
      : `<p class="muted small" style="margin:0">No confirmation was recorded.</p>`;
    return card("Confirmation", form);
  }
  const rows = [
    ["Result", confirmation.ok ? pill("PASS", "green") : pill("FAIL", "red")],
    ["Target", `<span class="mono">${esc(confirmation.target || "—")}</span>`],
    ["Exit code", `<span class="mono">${esc(confirmation.exit_code)}</span>`],
    ["Output SHA-256", `<span class="mono">${esc(shortSha(confirmation.output_sha256))}</span>`],
    ["Source comment", externalLink(confirmation.comment_url) || "—"],
  ];
  const notes = (confirmation.notes || []).map((note) => `<li>${esc(note)}</li>`).join("");
  const rerun = state.writable
    ? `<div class="form-row">
         <label>HTTP check
           <input id="confirm-url" value="${esc(confirmation.url || "")}" placeholder="https://app.example/health" />
         </label>
         <label>or command
           <input id="confirm-command" value="${esc(confirmation.command ? JSON.stringify(confirmation.command) : "")}" placeholder='["python","-m","pytest"]' />
         </label>
       </div>
       <button type="button" class="btn ghost" data-action="confirm" data-force="1">Confirm again</button>`
    : "";
  return card(
    "Confirmation",
    `${table(["Field", "Value"], rows)}
     ${notes ? `<ul class="small muted">${notes}</ul>` : ""}
     ${rerun}`,
    { actions: confirmation.ok ? "confirmed" : "failed" },
  );
}

function renderTeam(detail) {
  const team = detail.team || {};
  const latest = team.latest;
  const button =
    state.writable && detail.evidence
      ? `<button type="button" class="btn ghost" data-action="team-verify">Verify with team</button>`
      : "";
  if (!latest) {
    return card(
      "Verification team",
      `<p class="muted small" style="margin:0 0 10px">Inspector, challenger and reporter have not run on this proof yet.</p>${button}`,
    );
  }
  const inspector = latest.inspector || {};
  const challenger = latest.challenger || {};
  const checks = Object.entries(inspector.checks || {})
    .map(([key, value]) => `<li><span class="mono">${esc(key)}</span> · ${value ? "pass" : "fail"}</li>`)
    .join("");
  const gaps = (challenger.gaps || []).map((gap) => `<li>${esc(gap)}</li>`).join("");
  const history = (team.history || [])
    .map((item) => `<li>${esc(item.verdict || "?")} · ${esc((item.blockers || []).join("; ") || "no blockers")}</li>`)
    .join("");
  return card(
    "Verification team",
    `<div class="split" style="margin-bottom:10px">
       ${pill(latest.verdict === "allow" ? "ALLOW" : "BLOCK", latest.verdict === "allow" ? "green" : "red")}
       <span class="muted small">${esc(latest.team || "inspector + challenger + reporter")}</span>
     </div>
     ${checks ? `<ul class="small muted">${checks}</ul>` : ""}
     ${gaps ? `<p class="small muted" style="margin:0">Challenger gaps</p><ul class="small muted">${gaps}</ul>` : ""}
     ${(latest.blockers || []).length ? `<ul class="small bad-list">${latest.blockers.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}
     ${history ? `<p class="faint small" style="margin:12px 0 4px">History</p><ul class="small muted">${history}</ul>` : ""}
     ${button}`,
  );
}

function renderVerifier(detail) {
  const verifier = detail.verifier || {};
  const name = verifier.name || "local";
  const isolation = verifier.isolation || "process";
  return card(
    "Verifier",
    `<div class="split" style="margin-bottom:8px">
       ${pill(name.toUpperCase(), name === "docker" ? "green" : "")}
       ${pill(isolation)}
     </div>
     <p class="muted small" style="margin:0">${
       name === "docker"
         ? "The verifier runs in a container with no network, dropped capabilities and only the worktree mounted."
         : "The verifier runs as a separate process; builder credentials are removed from its environment."
     }</p>`,
  );
}

function renderLaix(detail) {
  const events = detail.laix || [];
  if (!events.length) {
    return card(
      "LAIX shadow",
      `<p class="muted small" style="margin:0">LAIX is off, or no shadow decision was recorded for this run.</p>`,
    );
  }
  const rows = events.map((event) => [
    esc(event.agrees == null ? "—" : event.agrees ? "agree" : "disagree"),
    esc(event.deterministic?.verb || event.deterministic || "—"),
    esc(event.candidate?.verb || event.candidate || "—"),
    esc((event.reason_codes || event.reasons || []).join(", ") || "—"),
  ]);
  return card("LAIX shadow", table(["Comparison", "Deterministic", "LAIX", "Reason codes"], rows));
}

function renderProducts() {
  const products = state.products;
  if (!products) return card("Product map", `<p class="muted small">Loading.</p>`);
  if (!products.configured) {
    return card(
      "Product map",
      `<p class="muted small" style="margin:0">No <span class="mono">${esc(products.path || ".works/products.yaml")}</span> yet. A product name still falls back to the working directory.</p>`,
    );
  }
  const rows = (products.products || []).map((item) => [
    `<strong>${esc(item.name)}</strong>`,
    `<span class="mono">${esc(item.repo)}</span>`,
    item.exists ? pill("EXISTS", "green") : pill("MISSING", "red"),
    item.git ? pill("GIT", "green") : pill("NOT GIT", "red"),
  ]);
  return card("Product map", table(["Product", "Repository", "Path", "Git"], rows), {
    actions: esc(products.path),
  });
}

function renderDetectors() {
  const detectors = state.detectors;
  if (!detectors) return card("Detectors", `<p class="muted small">Loading.</p>`);
  if (!detectors.configured) {
    return card(
      "Detectors",
      `<p class="muted small" style="margin:0">No <span class="mono">${esc(detectors.path || ".works/detectors.yaml")}</span> yet. Firing alerts can still be imported from the CLI.</p>`,
    );
  }
  const body = (detectors.detectors || [])
    .map((detector) => {
      const alerts = (detector.alerts || [])
        .map(
          (alert) => `<div class="check ${alert.severity === "critical" ? "fail" : "skip"}">
            <span class="box" aria-hidden="true">!</span>
            <span class="feature-copy"><strong>${esc(alert.title)}</strong><em>${esc(alert.severity || "alert")} · ${esc(alert.ref)}</em></span>
            <span class="check-detail">${state.writable ? `<button type="button" class="btn ghost" data-action="detector-create" data-name="${esc(detector.name)}">Create task</button>` : ""}</span>
          </div>`,
        )
        .join("");
      const note = detector.error
        ? `<p class="bad small" style="margin:8px 0 0">${esc(detector.error)}</p>`
        : detector.needs_refresh
          ? `<p class="muted small" style="margin:8px 0 0">Remote alerts are fetched on refresh.</p>`
          : "";
      return `<div class="detector">
        <div class="split"><strong>${esc(detector.name)}</strong>${pill(detector.product || "—")}</div>
        ${alerts || `<p class="muted small" style="margin:8px 0 0">No firing alerts.</p>`}
        ${note}
      </div>`;
    })
    .join("");
  return card("Detectors", body, {
    actions: state.writable
      ? `<button type="button" class="btn ghost" data-action="refresh-detectors">Refresh alerts</button>`
      : `${(detectors.detectors || []).length} configured`,
  });
}

function renderRunHistory(detail) {
  const runs = detail.runs || [];
  if (!runs.length) {
    return card("Run history", `<p class="muted small" style="margin:0">No finished runs yet.</p>`);
  }
  const rows = runs
    .slice()
    .reverse()
    .map((run) => [
      `<span class="mono">${esc(run.run_id)}</span>`,
      `<span class="mono">${esc(shortSha(run.base_commit))}</span>`,
      pill(run.verdict, run.verdict === "allow" ? "green" : run.verdict === "block" ? "red" : ""),
      esc(run.risk),
      esc(fmtMs(run.duration_ms)),
      esc(fmtUsd(run.usd)),
      `<button type="button" class="btn ghost" data-action="compare-runs">Compare</button>`,
    ]);
  return card(
    "Run history",
    table(["Run", "Commit", "Verdict", "Risk", "Wall", "USD", ""], rows, [4, 5]),
    { actions: `${runs.length} run(s)` },
  );
}

function openRunsDialog() {
  const detail = state.detail;
  if (!detail) return;
  const runs = (detail.runs || []).slice().reverse();
  const fill = (selector) => {
    const node = $(selector);
    node.innerHTML = runs
      .map((run) => `<option value="${esc(run.run_id)}">${esc(run.run_id)} · ${esc(run.verdict)}</option>`)
      .join("");
    return node;
  };
  const selects = $("#runs-dialog .form-row");
  selects.hidden = runs.length < 2;
  if (runs.length < 2) {
    $("#run-compare-body").innerHTML = `<p class="muted small">Comparison needs at least two finished runs. This task has ${runs.length}.</p>`;
  } else {
    fill("#run-a");
    fill("#run-b").value = runs[1].run_id;
    renderRunComparison();
  }
  $("#runs-dialog").showModal();
}

function renderRunComparison() {
  const detail = state.detail;
  if (!detail) return;
  const runs = detail.runs || [];
  const find = (id) => runs.find((run) => run.run_id === id);
  const a = find($("#run-a").value);
  const b = find($("#run-b").value);
  if (!a || !b) {
    $("#run-compare-body").innerHTML = `<p class="muted small">Choose two runs.</p>`;
    return;
  }
  const fields = [
    ["State", "state", (value) => esc(value)],
    ["Base commit", "base_commit", (value) => `<span class="mono">${esc(shortSha(value))}</span>`],
    ["Proof SHA-256", "proof_sha256", (value) => `<span class="mono">${esc(shortSha(value))}</span>`],
    ["Verdict", "verdict", (value) => pill(value, value === "allow" ? "green" : "red")],
    ["Risk", "risk", (value) => esc(value)],
    ["Files", "files", (value) => esc((value || []).join(", ") || "—")],
    ["Not tested", "not_tested", (value) => esc((value || []).join(", ") || "none")],
    ["Tokens", "tokens", (value) => esc(value)],
    ["USD", "usd", (value) => esc(fmtUsd(value))],
    ["Wall", "duration_ms", (value) => esc(fmtMs(value))],
    ["Delivered", "delivered", (value) => (value ? pill("yes", "green") : pill("no", ""))],
    ["Confirmed", "confirmed", (value) => (value ? pill("pass", "green") : pill("no", ""))],
  ];
  const rows = fields.map(([label, key, render]) => [
    esc(label),
    render(a[key]),
    render(b[key]),
  ]);
  $("#run-compare-body").innerHTML = table(["Field", a.run_id, b.run_id], rows);
}

function renderReleaseView(detail) {
  return `<div class="grid">
    <div class="stack">
      ${renderReleasePacket(detail)}
      ${renderDelivery(detail)}
      ${renderConfirmation(detail)}
      ${renderRunHistory(detail)}
    </div>
    <div class="stack">
      ${renderTeam(detail)}
      ${renderVerifier(detail)}
      ${renderLaix(detail)}
      ${renderProducts()}
      ${renderDetectors()}
    </div>
  </div>`;
}

function eventSummary(event) {
  const data = event.data || {};
  if (event.type === "state.changed") return stateLabel(data.to);
  if (event.type === "gate.decided") return `${gateLabel(data.gate)}: ${data.decision}`;
  if (event.type === "risk.rated") return `${riskLabel(data.level)} · ${(data.owners || []).join(", ") || "no owner"}`;
  if (event.type === "decision.made") return `${decisionLabel(data.verb)} · ${data.reason_code || ""}`;
  if (event.type === "would_block") return `${data.gate}: ${data.reason}`;
  if (event.type === "flake") return `Flake: ${data.scenario_id} (${data.owner})`;
  if (event.type === "wait.started") return `Waiting for ${data.wake_on}`;
  if (event.type === "wait.woken") return "Woke on its event";
  if (event.type === "memory.reported") return `PPMA synced · ${data.via || "run"} · ${data.run_id || ""}`;
  if (event.type === "memory.failed") return `PPMA failed · ${data.error || "unknown error"}`;
  if (event.type === "memory.recalled") return `recalled ${ (data.statements || []).length } statement(s)`;
  if (event.type === "memory.recall_failed") return `recall failed · ${data.error || "unknown error"}`;
  if (event.type === "readiness.checked") return `readiness ${data.status} · ${data.passed}/${data.total}`;
  if (event.type === "team.verified") return `team ${data.verdict} · ${data.team || "inspector+challenger+reporter"}`;
  if (event.type === "delivery.finished") return `${data.branch || "branch"} · ${data.commit || ""}${data.pr_url ? " · pull request" : ""}`;
  if (event.type === "confirmation.finished") return `${data.ok ? "passed" : "failed"} · ${data.target || "check"}`;
  if (event.type === "thread.note") return data.message || "context added";
  if (event.type === "thread.agent") return `Mira · ${data.model || "model"} · ${data.tokens || 0} token(s)`;
  if (event.type === "thread.commentary") return `${data.role || "role"} · AI commentary · ${data.model || "model"}`;
  if (event.type === "step.finished") return `${data.step}: exit ${data.exit_code}`;
  if (event.type === "challenge.decided") return data.allow ? "Independent check passed" : "Independent check blocked";
  if (event.type === "note") return "The proof is ready.";
  return Object.entries(data).map(([key, value]) => `${key}=${value}`).join(" · ");
}

function summarySentence(detail) {
  const state = detail.task.state;
  if (state === "proved") return "The problem was reproduced, fixed and checked. The fix is ready to go back to the source.";
  if (state === "blocked") return "The factory could not verify a safe fix. A person needs to look before anything ships.";
  if (state === "released") return "The fix was delivered back to where the problem was reported.";
  if (state === "reverted") return "A released fix was reverted. A person is looking at why.";
  if (state.startsWith("waiting")) return `${stateLabel(state)}. The factory will continue when the next event arrives.`;
  if (state === "queued") return "This report is in the queue. The factory has not started yet.";
  return `${stateLabel(state)}. The factory is working on the reported issue.`;
}

function summaryChanged(detail) {
  const evidence = detail.evidence;
  const title = detail.task.source?.title || "The reported issue";
  if (!evidence) return "No change has been produced yet.";
  if (detail.task.state === "proved" || detail.task.state === "released") {
    const files = (evidence.files_changed || []).length;
    return `“${title}” is fixed. ${files || "A focused"} file${files === 1 ? "" : "s"} changed in one patch.`;
  }
  if (detail.task.state === "blocked") {
    return "No verified change is ready. The factory stopped rather than ship a fix it could not prove.";
  }
  return "The change is still being prepared.";
}

function summaryChecks(detail) {
  const evidence = detail.evidence;
  if (!evidence?.verdict) {
    return `<li><span class="warn-tick">•</span> No checks have run yet.</li>`;
  }
  const outcomes = evidence.verdict.outcomes || [];
  const must = outcomes.filter((item) => item.priority === "P0");
  const optional = outcomes.filter((item) => item.priority === "P1");
  const mustPassed = must.every((item) => item.passed);
  const items = [
    `<li><span class="${mustPassed ? "tick" : "bad-tick"}">${mustPassed ? "✓" : "!"}</span> ${must.length} must-pass check${must.length === 1 ? "" : "s"} ${mustPassed ? "passed" : "failed"}.</li>`,
  ];
  if (optional.length) {
    const p1 = optional.filter((item) => item.passed).length;
    const label = optional.length === 1 ? "optional check" : "optional checks";
    items.push(`<li><span class="${p1 === optional.length ? "tick" : "warn-tick"}">${p1 === optional.length ? "✓" : "•"}</span> ${p1} of ${optional.length} ${label} passed.</li>`);
  }
  if (evidence.challenge) {
    items.push(`<li><span class="${evidence.challenge.allow ? "tick" : "bad-tick"}">${evidence.challenge.allow ? "✓" : "!"}</span> A separate agent ${evidence.challenge.allow ? "challenged the diagnosis" : "found a blocker"}.</li>`);
  }
  if (evidence.reproduce) {
    items.push(`<li><span class="${evidence.reproduce.exit_code !== 0 ? "tick" : "warn-tick"}">${evidence.reproduce.exit_code !== 0 ? "✓" : "•"}</span> The problem was reproduced before the fix.</li>`);
  }
  return items.join("");
}

function summaryWho(detail) {
  const state = detail.task.state;
  const gates = (detail.timeline || []).filter((event) => event.type === "gate.decided");
  const release = gates.find((event) => event.data.gate === "release");
  const plan = gates.find((event) => event.data.gate !== "release");
  const by = (gate) => (gate.data.by === "cli" ? "a person" : "the flow");
  if (state === "blocked") return "A person decides the next step.";
  if (state === "reverted") return "A person decides whether to retry.";
  if (state === "proved") return "A person releases it. Not released yet.";
  if (state === "released") {
    return release ? `Released by ${by(release)} ${timeAgo(release.ts)}.` : "A person released it.";
  }
  if (state === "queued") return "A person approves the plan before any fix.";
  if (plan) return `Plan approved by ${by(plan)} ${timeAgo(plan.ts)}.`;
  const decision = detail.evidence?.decision;
  if (decision) return decision.requires_approval ? "A person still needs to approve." : "No approval was required.";
  return "A person approves the plan before any fix.";
}

function summaryAction(detail) {
  const state = detail.task.state;
  if (state === "blocked") return "A person needs to review the evidence and decide whether to retry or change the plan.";
  if (state === "proved") return "Nothing is needed from you. If the problem returns, reopen the report.";
  if (state === "released") return "Nothing is needed from you. The report is closed.";
  if (state === "reverted") return "A person is investigating the revert. You can add context to the report.";
  if (state.startsWith("waiting")) return "The factory is waiting for a person or an external check. You can add context meanwhile.";
  return "You can add context to the report. The factory will pick it up.";
}

function summaryNext(detail) {
  const state = detail.task.state;
  if (state === "blocked") return "Nothing will ship until a person decides. The report stays open.";
  if (state === "proved") return "The fix goes back to the app, tracker or person that reported it.";
  if (state === "released") {
    if (detail.confirmation) {
      return detail.confirmation.ok
        ? "The released fix was confirmed at the source. The report can be closed."
        : "The confirmation failed. A person decides whether to retry or reopen the work.";
    }
    if (detail.delivery) return "The fix is delivered. Confirmation is the next step.";
    return "A person released it. Delivery is the next step.";
  }
  if (state === "reverted") return "The release was reverted; a person is deciding the next step.";
  if (state.startsWith("waiting")) return "The next step starts when the waiting event arrives.";
  if (state === "queued") return "The factory will pick it up from the queue.";
  return "The factory is still preparing the change.";
}

function renderNextActions(detail) {
  if (!state.writable) return "";
  const release = detail.release || {};
  const buttons = [];
  if (release.ready && !release.released) {
    buttons.push(`<button type="button" class="btn" data-action="release">Release this commit</button>`);
  }
  if (release.released && !detail.delivery) {
    buttons.push(`<button type="button" class="btn" data-action="deliver">Deliver</button>`);
  }
  if (detail.delivery && !detail.confirmation) {
    buttons.push(`<button type="button" class="btn" data-action="confirm">Confirm</button>`);
  }
  buttons.push(`<button type="button" class="btn ghost" data-action="open-release">Release view</button>`);
  return `<div class="form-row" style="margin:10px 0 0">${buttons.join(" ")}</div>`;
}

function renderSummary(detail) {
  const task = detail.task;
  const state = task.state;
  const risk = detail.evidence?.risk?.level || detail.summary.risk;
  const decision = detail.evidence?.decision?.verb || detail.summary.decision;
  const hero = `<section class="hero">
    <div class="eyebrow">Fix report</div>
    <h2>${esc(stateLabel(state))}</h2>
    <p>${esc(summarySentence(detail))}</p>
    <div class="hero-meta">
      <span><strong>${esc(sourceLabel(task.source.kind))}</strong> · ${esc(task.source.ref)}</span>
      <span><strong>${esc(timeAgo(task.updated_at))}</strong></span>
      <span><strong>${esc(task.product)}</strong> · ${esc(task.flow)}</span>
      ${risk ? `<span>Risk <strong>${esc(risk[0].toUpperCase() + risk.slice(1))}</strong></span>` : ""}
      ${decision ? `<span>Decision <strong>${esc(decisionLabel(decision))}</strong></span>` : ""}
      ${detail.evidence ? `<span>took <strong>${esc(fmtMs(detail.evidence.duration_ms))}</strong></span>` : ""}
    </div>
  </section>`;
  const changed = card("What changed for you", `<p class="muted" style="margin:0">${esc(summaryChanged(detail))}</p>`);
  const checked = card("What we checked", `<ul class="big-list">${summaryChecks(detail)}</ul>`);
  const notTested = detail.evidence?.not_tested?.length
    ? `<ul class="big-list">${detail.evidence.not_tested.map((item) => `<li><span class="warn-tick">•</span> ${esc(item)}</li>`).join("")}</ul>`
    : `<p class="muted small" style="margin:0">No gaps were recorded in the evidence.</p>`;
  const residual = card("What we did not check", notTested);
  const who = card("Who decided", `<p class="muted" style="margin:0">${esc(summaryWho(detail))}</p>`);
  const next = card("Where it goes next", `<p class="muted" style="margin:0">${esc(summaryNext(detail))}</p>`);
  const action = card(
    "What you can do",
    `<p class="muted" style="margin:0 0 10px">${esc(summaryAction(detail))}</p>
     <button class="btn" data-action="evidence">See the evidence</button>
     <button class="btn ghost" data-action="copy">Copy link</button>
     ${renderNextActions(detail)}`,
  );
  const timeline = card(
    "What happened",
    `<ol class="timeline">${(detail.timeline || []).slice().reverse().slice(0, 6).map((event) => `<li><time>${esc(new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</time><span class="type">${esc(timelineLabel(event.type))}</span><span class="data">${esc(eventSummary(event))}</span></li>`).join("") || "<li class='muted small'>No events yet.</li>"}</ol>`,
  );
  return `${hero}<div class="summary-grid">${changed}${checked}${residual}${who}${next}${action}</div><div class="stack" style="margin-top:16px">${timeline}</div>`;
}

function renderEvidenceMeta(detail) {
  const evidence = detail.evidence;
  const run = detail.run;
  const task = detail.task;
  const rows = [
    ["Task id", task.id],
    ["Task kind", task.kind],
    ["Run id", run?.run_id || "—"],
    ["Base commit", evidence?.base_commit || "—"],
    ["Rules version", evidence?.checks_sha || "—"],
    ["Evidence fingerprint", evidence?.proof_sha256 || "—"],
    ["Model", evidence?.model || "—"],
    ["Provider", evidence?.provider || "—"],
    ["Verifier", `${detail.verifier?.name || "local"} · ${detail.verifier?.isolation || "process"}`],
    ["Memory", memoryStatus(detail).label],
  ];
  return card(
    "Run metadata",
    `<dl class="kv">${rows.map(([key, value]) => `<dt>${esc(key)}</dt><dd class="mono">${esc(value)}</dd>`).join("")}</dl>
     <div class="export-row">
       <a class="btn ghost" href="/api/tasks/${encodeURIComponent(task.id)}/export/evidence.md" download>proof.md</a>
       <a class="btn ghost" href="/api/tasks/${encodeURIComponent(task.id)}/export/evidence.json" download>evidence.json</a>
       <a class="btn ghost" href="/api/tasks/${encodeURIComponent(task.id)}/export/run.json" download>run.json</a>
       ${detail.release?.released ? `<a class="btn ghost" href="/api/tasks/${encodeURIComponent(task.id)}/export/release.json" download>release.json</a>` : ""}
       ${detail.delivery ? `<a class="btn ghost" href="/api/tasks/${encodeURIComponent(task.id)}/export/delivery.json" download>delivery.json</a>` : ""}
       ${detail.confirmation ? `<a class="btn ghost" href="/api/tasks/${encodeURIComponent(task.id)}/export/confirmation.json" download>confirmation.json</a>` : ""}
     </div>`,
  );
}

const threadRoleLabel = {
  person: "Person",
  builder: "Builder",
  verifier: "Verifier",
  challenger: "Challenger",
  team: "Team",
  delivery: "Delivery",
  confirmation: "Confirmation",
  system: "System",
  tracker: "Tracker",
  monitor: "Monitor",
  mira: "Mira",
  inspector: "Inspector",
  reporter: "Reporter",
};

const threadRoleLetter = {
  person: "P",
  builder: "B",
  verifier: "V",
  challenger: "C",
  team: "T",
  delivery: "D",
  confirmation: "✓",
  system: "·",
  tracker: "T",
  monitor: "M",
  mira: "M",
  inspector: "I",
  reporter: "R",
};

function renderThreadCard(card) {
  if (!card) return "";
  const rows = (card.rows || [])
    .map(([label, value]) => {
      const text = String(value ?? "");
      const cell = /^https?:\/\//.test(text)
        ? `<a href="${esc(text)}" target="_blank" rel="noopener">${esc(text)}</a>`
        : `<span class="mono">${esc(text)}</span>`;
      return `<div class="thread-row"><span>${esc(label)}</span>${cell}</div>`;
    })
    .join("");
  const options = (card.options || [])
    .map(
      (option) =>
        `<button type="button" class="btn ${option.tone === "primary" ? "" : "ghost"}" data-thread-action="${esc(option.action)}">${esc(option.label)}${option.recommended ? " · recommended" : ""}</button>`,
    )
    .join(" ");
  return `<div class="thread-card">
    ${card.prompt ? `<p class="thread-question">${esc(card.prompt)}</p>` : ""}
    ${rows}
    ${options ? `<div class="thread-options">${options}</div>` : ""}
  </div>`;
}

function sourceUrl(task) {
  const ref = String(task?.source?.ref || "");
  if (/^https?:\/\//.test(ref)) return ref;
  const match = ref.match(/^([^/]+)\/([^#]+)#(\d+)$/);
  if (match) return `https://github.com/${match[1]}/${match[2]}/issues/${match[3]}`;
  return "";
}

function renderThreadMessage(message) {
  const role = message.role || "system";
  const facts = (message.facts || [])
    .map((fact) => `<span class="chip">${esc(fact)}</span>`)
    .join(" ");
  const badge = message.generated ? `<span class="ai-badge">AI commentary</span>` : "";
  return `<div class="thread-msg ${esc(role)} ${esc(message.tone || "")}${message.generated ? " generated" : ""}">
    <div class="thread-avatar" aria-hidden="true">${esc(threadRoleLetter[role] || "·")}</div>
    <div class="thread-body">
      <div class="thread-meta">
        <b>${esc(threadRoleLabel[role] || role)}</b>
        ${badge}
        <time>${esc(new Date(message.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</time>
      </div>
      <h3>${esc(message.title)}</h3>
      ${message.body ? `<p>${esc(message.body)}</p>` : ""}
      ${facts ? `<div class="thread-facts">${facts}</div>` : ""}
      ${renderThreadCard(message.card)}
    </div>
  </div>`;
}

function railCard(title, body) {
  return `<section class="rail-card"><h3>${esc(title)}</h3>${body}</section>`;
}

function railRows(rows) {
  return rows
    .map(([label, value, href]) => {
      const cell = href
        ? `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(value)}</a>`
        : `<span>${esc(value)}</span>`;
      return `<div class="rail-row"><span class="rail-label">${esc(label)}</span>${cell}</div>`;
    })
    .join("");
}

function renderThreadRail(rail, detail) {
  const task = rail.task || {};
  const factory = rail.factory || {};
  const cost = rail.cost || {};
  const agents = (rail.agents || [])
    .map(
      (agent) => `<div class="rail-agent">
        <span class="rail-role">${esc(agent.role)}</span>
        <b>${esc(agent.name)}</b>
        <em>${esc(agent.detail)}</em>
        ${agent.tone ? pill(agent.detail, agent.tone === "ok" ? "green" : "red") : ""}
      </div>`,
    )
    .join("");
  const deliverables = (rail.deliverables || [])
    .map(
      (item) => `<div class="rail-row">
        <span class="rail-label">${esc(item.label)}</span>
        ${item.href ? `<a href="${esc(item.href)}" target="_blank" rel="noopener">${esc(item.value)}</a>` : `<span class="mono">${esc(item.value)}</span>`}
      </div>`,
    )
    .join("");
  const checks = (rail.checks || [])
    .map(
      (item) =>
        `<div class="rail-row"><span class="rail-label">${esc(item.label)}</span>${pill(
          item.value,
          item.value === "allow" || item.value === "pass" ? "green" : item.value === "block" || item.value === "fail" ? "red" : "",
        )}</div>`,
    )
    .join("");
  const artifacts = (detail.artifacts || [])
    .slice(0, 6)
    .map(
      (item) => `<a class="rail-artifact" href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.kind)} · ${esc(item.name)}</a>`,
    )
    .join("");
  return `${railCard("Task", railRows([
    ["Id", task.id || "—"],
    ["Product", task.product || "—"],
    ["Source", task.source || "—"],
    ["State", task.state || "—"],
  ]))}
  ${railCard("Factory", railRows([
    ["Flow", factory.flow || "—"],
    ["Run", factory.run || "—"],
    ["Base commit", factory.base_commit || "—"],
    ["Checks SHA", factory.checks_sha || "—"],
  ]))}
  ${railCard("People", `<div class="rail-people">${(rail.people || []).map((name) => pill(name)).join(" ")}${(rail.owners || []).map((name) => pill(`owner: ${name}`)).join(" ")}</div>`)}
  ${railCard("Agents", agents || `<p class="muted small">No agent work recorded yet.</p>`)}
  ${railCard("Deliverables", deliverables)}
  ${railCard("Checks", checks)}
  ${railCard("Cost", railRows([
    ["Tokens", String(cost.tokens ?? 0)],
    ["USD", fmtUsd(cost.usd ?? 0)],
    ["Wall", fmtMs(cost.duration_ms ?? 0)],
  ]))}
  ${railCard("Artifacts", artifacts || `<p class="muted small">No artifacts.</p>`)}`;
}

function renderThread(detail) {
  const messages = detail.thread || [];
  const ai = state.ai || {};
  const mode = ai.available ? state.composeMode || "ask" : "note";
  const modes = ai.available
    ? `<div class="composer-modes" role="group" aria-label="Message mode">
        <button type="button" data-compose-mode="ask" class="${mode === "ask" ? "active" : ""}">Ask Mira</button>
        <button type="button" data-compose-mode="note" class="${mode === "note" ? "active" : ""}">Add context</button>
      </div>`
    : "";
  const composer = state.writable
    ? `<form class="thread-composer" id="thread-form">
        ${modes}
        <textarea id="thread-input" rows="2" placeholder="${mode === "ask" ? "Tell Mira more…" : "Add context to this run…"}"></textarea>
        <div class="thread-composer-actions">
          <span class="muted small">${mode === "ask" ? "Advisory only. Mira reads the recorded proof and cannot open a gate." : "A note, not a command. It never opens a gate or starts a run."}</span>
          <button type="submit" class="btn">${mode === "ask" ? "Ask Mira" : "Add context"}</button>
        </div>
      </form>`
    : `<p class="thread-readonly">Start <span class="mono">works ui --write</span> to ask Mira or add context.</p>`;
  const url = sourceUrl(detail.task);
  const source = url
    ? `<a href="${esc(url)}" target="_blank" rel="noopener" class="mono">${esc(detail.task.source.ref)}</a>`
    : `<span class="mono">${esc(detail.task.source.ref)}</span>`;
  const commentary =
    state.writable && ai.available
      ? `<button type="button" class="btn ghost" data-action="commentary">Generate commentary</button>`
      : "";
  return `<div class="thread-layout">
    <div class="thread-main">
      <header class="thread-head">
        <div class="thread-head-main">
          <div class="thread-done-row">
            <span class="thread-done ${esc(stateTone(detail.task.state))}">${esc(stateLabel(detail.task.state))}</span>
            ${source}
            <span class="muted small">${esc(detail.task.product)}</span>
          </div>
          <h2>${esc(detail.task.source.title || detail.task.id)}</h2>
          <p class="thread-intent">Build this from ${esc(sourceLabel(detail.task.source.kind))}: ${esc(detail.task.source.ref)}</p>
        </div>
        <div class="thread-head-side">
          <span class="muted small">${messages.length} event(s)</span>
          ${commentary}
        </div>
      </header>
      <div class="thread-line">${messages.map(renderThreadMessage).join("") || `<p class="muted small">No events yet.</p>`}</div>
      ${composer}
    </div>
    <aside class="thread-rail" aria-label="Task context">${renderThreadRail(detail.rail || {}, detail)}</aside>
  </div>`;
}

function renderTimeline(timeline) {
  const filters = {
    all: () => true,
    gates: (event) => ["gate.decided", "decision.made", "decision.shadow"].includes(event.type),
    delivery: (event) =>
      event.type.startsWith("delivery") ||
      (event.type === "state.changed" && event.data?.to === "released"),
    confirmation: (event) => event.type.startsWith("confirmation"),
    readiness: (event) => ["readiness.checked", "team.verified"].includes(event.type),
  };
  const active = filters[state.timelineFilter] ? state.timelineFilter : "all";
  const rows = (timeline || [])
    .filter(filters[active])
    .slice()
    .reverse()
    .map((event) => `<li data-event-seq="${event.seq}" class="event-row">
      <time>${esc(new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</time>
      <span class="type">${esc(timelineLabel(event.type))}</span>
      <span class="data" title="${esc(eventSummary(event))}">${esc(eventSummary(event))}</span>
    </li>`);
  const buttons = Object.keys(filters)
    .map(
      (key) =>
        `<button type="button" class="chip ${active === key ? "active" : ""}" data-timeline-filter="${key}">${esc(key)}</button>`,
    )
    .join(" ");
  return card(
    "Timeline",
    `<div class="chips" style="margin-bottom:10px">${buttons}</div>
     <ol class="timeline">${rows.join("") || "<li class='muted small'>No events for this filter.</li>"}</ol>`,
    { actions: `${esc((timeline || []).length)} recent events` },
  );
}

function renderEvidence(detail) {
  const evidence = detail.evidence;
  const pipeline = detail.pipeline?.technical
    ? card("Pipeline · 10 steps", renderLine(detail, detail.pipeline.technical, "technical"), {
        tight: true,
      })
    : "";
  return evidence
    ? `${pipeline}${renderEvidenceMeta(detail)}<div class="grid">
        <div class="stack">
          ${renderVerdict(evidence)}
          ${renderFindings(evidence)}
          ${renderChallenge(evidence)}
          ${renderCommands(evidence)}
          ${renderChange(evidence)}
          ${renderPolicy(evidence)}
        </div>
        <div class="stack">
          ${renderRisk(evidence)}
          ${renderDecision(evidence)}
          ${renderReadiness(detail)}
          ${renderFeatures(detail)}
          ${renderArtifacts(detail)}
          ${renderMemoryRecall(evidence)}
          ${renderResidual(evidence)}
          ${renderCost(evidence)}
          ${renderVerifier(detail)}
          ${renderTeam(detail)}
          ${renderTimeline(detail.timeline)}
        </div>
      </div>`
    : `<div class="grid"><div class="stack">${renderEmptyProof()}</div><div class="stack">${renderReadiness(detail)}${renderFeatures(detail)}${renderArtifacts(detail)}${renderMemoryRecall(evidence)}${renderVerifier(detail)}${renderTimeline(detail.timeline)}</div></div>`;
}

function stopStory() {
  if (state.storyTimer) {
    window.clearInterval(state.storyTimer);
    state.storyTimer = null;
  }
}

function storyStageId(technical) {
  return {
    signal: "reported",
    reproduce: "confirmed",
    plan: "fixed",
    plan_gate: "fixed",
    build: "fixed",
    check: "checked",
    proof: "checked",
    release_gate: "delivered",
    deliver: "delivered",
    confirm: "delivered",
  }[technical] || technical;
}

function activeStage(detail, stages) {
  if (state.storyAt != null) {
    const scene = (detail.pipeline?.replay || [])[state.storyAt];
    if (scene) {
      const mapped = storyStageId(scene.stage);
      if (stages.some((stage) => stage.id === mapped)) return mapped;
    }
  }
  const current = stages.find((stage) => stage.state === "active")
    || stages.find((stage) => stage.state === "blocked")
    || [...stages].reverse().find((stage) => stage.state === "done")
    || stages[0];
  return current?.id;
}

function displayedState(stage, position, activeIndex, replaying) {
  if (!replaying) return stage.state || "pending";
  if (position < activeIndex) return "done";
  if (position === activeIndex) return "active";
  return "pending";
}

function renderLine(detail, stages, mode = "story") {
  if (!stages?.length) return `<p class="muted small">No pipeline recorded.</p>`;
  const active = activeStage(detail, stages);
  const index = Math.max(0, stages.findIndex((stage) => stage.id === active));
  const pct = ((index + 0.5) / stages.length) * 100;
  const selected = state.storySelected || active;
  const replaying = state.storyAt != null;
  const nodes = stages
    .map((stage, position) => {
      const stateName = displayedState(stage, position, index, replaying);
      const node = stateName === "done" ? "✓"
        : stateName === "blocked" ? "!"
        : stage.kind === "gate" ? "◆"
        : stateName === "active" ? "●"
        : String(position + 1);
      const classes = `station ${stateName}${stage.kind === "gate" ? " gate" : ""}${stage.id === selected ? " selected" : ""}`;
      return `<button type="button" class="${classes}" data-story-stage="${esc(stage.id)}" aria-label="${esc(stage.label)}: ${esc(stateName)}">
        <span class="node">${node}</span>
        <span class="station-label">${esc(stage.label)}</span>
        <span class="station-time">${esc(stage.at ? timeAgo(stage.at) : "—")}</span>
      </button>`;
    })
    .join("");
  return `<div class="line-scroll">
    <div class="line ${mode === "technical" ? "technical" : "story"}" style="--count:${stages.length}">
      <div class="rail"></div>
      <div class="rail-done" style="left:5%; width:${Math.max(0, pct - 5)}%"></div>
      <div class="stations">${nodes}</div>
      <div class="mira-marker" style="left:${pct}%">
        <img src="/mira.svg" alt="" width="44" height="44" />
        <span>Mira</span>
      </div>
    </div>
  </div>`;
}

function renderStoryReplay(detail) {
  const replay = detail.pipeline?.replay || [];
  if (!replay.length) return "";
  const at = state.storyAt == null ? replay.length - 1 : state.storyAt;
  const scene = replay[at];
  const playing = Boolean(state.storyTimer);
  return card(
    "Steps",
    `<div class="replay-row">
      <button type="button" class="btn ghost" data-story-step="-1" aria-label="Previous event">←</button>
      <button type="button" class="btn" data-story-play>${playing ? "Pause" : "Play"}</button>
      <button type="button" class="btn ghost" data-story-step="1" aria-label="Next event">→</button>
      <input id="story-range" type="range" min="0" max="${replay.length - 1}" value="${at}" aria-label="Replay position" />
      <button type="button" class="btn ghost" data-story-live>Now</button>
    </div>
    <p class="small muted" style="margin:10px 0 0" aria-live="polite">
      ${esc(scene ? `${timelineLabel(scene.type)} · ${eventSummary(scene)}` : "Current position")}
      <span class="faint"> · ${at + 1} / ${replay.length}</span>
    </p>`,
    { actions: `${replay.length} steps` },
  );
}

function renderRoute(detail, stages) {
  return `<section class="route-block" aria-label="Fix route">
    <div class="route-head">
      <span class="route-title">The fix route</span>
      <span class="route-legend" aria-label="Milestone states">
        <span><i class="legend-dot pending" aria-hidden="true"></i>Not started</span>
        <span><i class="legend-dot active" aria-hidden="true"></i>Mira is here</span>
        <span><i class="legend-dot waiting" aria-hidden="true"></i>Waits for you</span>
        <span><i class="legend-dot done" aria-hidden="true"></i>Done</span>
        <span><i class="legend-dot blocked" aria-hidden="true"></i>Stopped</span>
      </span>
    </div>
    <div class="route-scroll">
      <div class="route-wrap">
        <svg class="route-svg" viewBox="0 0 1200 380" preserveAspectRatio="none" aria-hidden="true">
          <path id="route-base" class="route-base" d="M 160 260 C 320 150 460 320 600 250 S 880 150 1040 260"/>
          <path id="route-progress" class="route-progress" d="M 160 260 C 320 150 460 320 600 250 S 880 150 1040 260"/>
        </svg>
        <div class="route-points" id="route-points" role="list" aria-label="Fix milestones"></div>
        <div class="route-mira" id="route-mira" aria-hidden="true"><img src="/mira.svg" alt="" width="52" height="52" /></div>
      </div>
    </div>
  </section>`;
}

function milestoneLabel(stage, display, detail) {
  const product = detail?.task?.product || "the product";
  const stops = {
    picked_up: {
      active: "Mira is picking it up",
      done: "Picked up",
      blocked: "Mira could not pick it up",
    },
    confirmed: {
      active: "Mira is confirming it",
      done: "Confirmed",
      blocked: "Mira could not confirm it",
    },
    fixed: {
      active: "Mira is fixing it",
      done: "Fixed",
      blocked: "Mira stopped while fixing",
    },
    checked: {
      active: "Mira is checking it",
      done: "Checked",
      blocked: "Mira stopped at a check",
    },
    delivered: {
      active: stage.label.startsWith("Release")
        ? "Mira is ready to release"
        : "Mira is delivering it",
      done: `Delivered to ${product}`,
      blocked: "Mira stopped before delivery",
    },
  };
  const stop = stops[stage.id];
  if (!stop) return stage.label;
  return stop[display] || stage.label;
}

function layoutRoute(detail) {
  const path = document.getElementById("route-base");
  const progress = document.getElementById("route-progress");
  const points = document.getElementById("route-points");
  const mira = document.getElementById("route-mira");
  const stages = detail.pipeline?.story || [];
  if (!path || !progress || !points || !mira || !stages.length) return;
  const length = path.getTotalLength();
  const active = activeStage(detail, stages);
  const activeIndex = Math.max(0, stages.findIndex((stage) => stage.id === active));
  const replaying = state.storyAt != null;
  const hasCurrent = stages.some(
    (stage) => stage.state === "active" || stage.state === "blocked",
  );
  const allDone = stages.every((stage) => stage.state === "done");
  const queued = detail.task?.state === "queued";
  const showMira = !queued && activeIndex > 0 && (replaying || hasCurrent || allDone);
  points.innerHTML = "";
  stages.forEach((stage, index) => {
    const point = path.getPointAtLength((length * index) / Math.max(1, stages.length - 1));
    const display = index === 0 ? "source" : displayedState(stage, index, activeIndex, replaying);
    const node = display === "done" ? "✓"
      : display === "blocked" ? "!"
      : display === "active" && stage.kind === "gate" ? "◆"
      : display === "active" ? "●"
      : "";
    const item = document.createElement("div");
    const side = index % 2 === 0 ? "above" : "below";
    item.className = `milestone ${display} ${side}${stage.kind === "gate" ? " gate" : ""}`;
    item.style.left = `${(point.x / 1200) * 100}%`;
    item.style.top = `${(point.y / 380) * 100}%`;
    const copy = display === "source" ? "Reported" : milestoneLabel(stage, display, detail);
    const stateWord = display === "source"
      ? "the report"
      : display === "done"
        ? "done"
        : display === "active"
          ? "Mira is here now"
          : display === "blocked"
            ? "stopped"
            : "not started";
    item.setAttribute("role", "listitem");
    item.setAttribute(
      "aria-label",
      `${copy}, ${stateWord}${stage.at && display !== "pending" ? `, ${timeAgo(stage.at)}` : ""}`,
    );
    if (display === "active") item.setAttribute("aria-current", "step");
    item.innerHTML = `<span class="m-node" aria-hidden="true">${node}</span><span class="m-copy"><strong>${esc(copy)}</strong>${
      stage.at && display !== "pending" ? `<em>${esc(timeAgo(stage.at))}</em>` : ""
    }</span>`;
    points.append(item);
  });
  const activePoint = path.getPointAtLength(
    (length * activeIndex) / Math.max(1, stages.length - 1),
  );
  mira.hidden = !showMira;
  mira.classList.toggle("above-node", activeIndex % 2 === 1);
  mira.style.left = `${(activePoint.x / 1200) * 100}%`;
  mira.style.top = `${(activePoint.y / 380) * 100}%`;
  const segments = Math.max(1, stages.length - 1);
  const start = length / segments;
  const end = (length * Math.max(0, activeIndex)) / segments;
  const visible = Math.max(0, end - start);
  progress.style.strokeDasharray = `${visible} ${length}`;
  progress.style.strokeDashoffset = `${-start}`;
  progress.classList.toggle("blocked", stages[activeIndex]?.state === "blocked");
}

function renderReceipt(detail) {
  const evidence = detail.evidence;
  const blocked = detail.task.state === "blocked";
  const changed = blocked
    ? "No change released"
    : evidence?.files_changed?.length
      ? `${evidence.files_changed.length} file${evidence.files_changed.length === 1 ? "" : "s"} changed`
      : "No change yet";
  const outcomes = evidence?.verdict?.outcomes || [];
  const must = outcomes.filter((item) => item.priority === "P0");
  const mustPassed = must.filter((item) => item.passed).length;
  const checked = must.length
    ? mustPassed === must.length
      ? `${mustPassed} of ${must.length} must-pass checks passed`
      : `${must.length - mustPassed} of ${must.length} must-pass checks failed`
    : "No checks yet";
  const notChecked = evidence?.not_tested?.length ? evidence.not_tested[0] : "No gaps recorded";
  const checkedNote = !evidence?.verdict
    ? "No checks yet"
    : evidence.verdict.allow
      ? evidence.challenge?.allow
        ? "Independent review passed"
        : "No independent review"
      : "A must-pass check failed";
  const who = blocked ? "A person on the fix team (not named yet)" : summaryWho(detail);
  return `<div class="receipt">
    <div><span>Changed</span><strong>${esc(changed)}</strong><p>${esc(summaryChanged(detail))}</p></div>
    <div><span>Checked</span><strong>${esc(checked)}</strong><p>${esc(checkedNote)}</p></div>
    <div><span>Not checked</span><strong>${esc(notChecked)}</strong><p>The proof says what was not covered.</p></div>
    <div><span>Decides</span><strong>${esc(who)}</strong><p>Human gates stay human.</p></div>
  </div>`;
}

function renderStoryRail(detail, blocked) {
  const state = detail.task.state;
  const title = blocked
    ? "What we need"
    : state === "proved"
      ? "What happens next"
      : state === "released"
        ? "Delivered"
        : "Where it stands";
  const body = blocked
    ? `<p class="rail-kicker">Needs a person</p>
       <p class="rail-big">One check failed.</p>
       <p>${esc(blocked.why)}</p>
       <dl class="rail-facts">
         <dt>Failed check</dt><dd><code>${esc(blocked.check || "must-pass check")}</code></dd>
         <dt>Impact</dt><dd>${esc(blocked.impact || `Nothing was released to ${detail.task.product}.`)}</dd>
       </dl>
       <p class="rail-next">${esc(blocked.next)}</p>`
    : state === "proved"
      ? `<p class="rail-kicker">Ready for a person</p>
         <p class="rail-big">Release to ${esc(detail.task.product)}</p>
         <p>The fix is built and checked. A person needs to release it back to ${esc(detail.task.product)}.</p>
         <dl class="rail-facts"><dt>Next step</dt><dd>Release to ${esc(detail.task.product)}</dd></dl>`
      : state === "queued"
        ? `<p class="rail-kicker">Waiting</p><p class="rail-big">In the queue</p><p>The factory has not started yet. Mira will pick it up.</p>`
        : state === "building" || state === "plan_approved"
          ? `<p class="rail-kicker">In progress</p><p class="rail-big">Mira is fixing it</p><p>The fix is being written now. Checks have not run yet.</p>`
          : state === "checking"
            ? `<p class="rail-kicker">In progress</p><p class="rail-big">Mira is checking it</p><p>The fix is built; the checks are running now.</p>`
            : `<p class="rail-kicker">In progress</p><p class="rail-big">${esc(stateLabel(state))}</p><p>The factory is working on the reported problem.</p>`;
  return `<aside class="story-rail"${blocked ? ' id="blocked"' : ""}>
    <div class="rail-title">${esc(title)}</div>
    ${body}
    <div class="rail-actions">
      <button type="button" class="btn ghost" data-action="copy">Copy link</button>
      <button type="button" class="btn ghost" data-action="cinema">Present</button>
      <button type="button" class="btn ghost" data-action="evidence">Open evidence</button>
    </div>
  </aside>`;
}

function storyHeadline(detail) {
  const state = detail.task.state;
  if (state === "blocked") return "Not fixed yet";
  if (state === "proved") return "Ready for release";
  if (state === "released") return `Fixed and back in ${detail.task.product}`;
  if (state === "reverted") return "Reverted";
  if (state === "queued") return "In the queue";
  if (state === "building" || state === "plan_approved") return "Fixing it now";
  if (state === "checking") return "Checking it now";
  return stateLabel(state);
}

function storyHeroText(detail) {
  const state = detail.task.state;
  const product = detail.task.product;
  const blocked = detail.pipeline?.blocked;
  if (state === "blocked" && blocked) {
    const impact = blocked.impact || `Nothing was released to ${product}. The problem is still there.`;
    return `${impact} A person needs to decide the next step.`;
  }
  if (state === "proved") {
    return `The fix is built and checked. A person needs to release it back to ${product}.`;
  }
  if (state === "released") {
    return `The fix is back where it was seen. The report can close.`;
  }
  if (state === "queued") {
    return `The factory has not started yet. Mira will pick it up.`;
  }
  if (state === "building" || state === "plan_approved") {
    return `Mira is writing the fix for ${product}. No checks have run yet.`;
  }
  if (state === "checking") {
    return `The fix is built. Mira is running the checks now.`;
  }
  if (state === "reverted") {
    return `The fix was reverted; a person is looking at why.`;
  }
  return summarySentence(detail);
}

function storyPrimary(detail) {
  const state = detail.task.state;
  if (state === "blocked") {
    return `<button type="button" class="btn" data-action="blocked">See what failed</button>`;
  }
  if (state === "proved" || state === "reverted") {
    return `<button type="button" class="btn" data-action="evidence">Open evidence</button>`;
  }
  return "";
}

function memoryStatus(detail) {
  const events = detail.timeline || [];
  const last = [...events]
    .reverse()
    .find((event) => event.type === "memory.reported" || event.type === "memory.failed");
  if (!last) return { label: "Not recorded", tone: "muted", at: null };
  if (last.type === "memory.reported") {
    return { label: "PPMA synced", tone: "ok", at: last.ts };
  }
  return { label: "PPMA failed", tone: "bad", at: last.ts };
}

function reportedAt(detail) {
  return (
    detail?.pipeline?.story?.find((stage) => stage.id === "reported")?.at
    || detail?.task?.created_at
    || detail?.task?.updated_at
  );
}

function replayBanner(detail) {
  const count = (detail.pipeline?.replay || []).length;
  return `<div class="replay-banner">Replaying history · ${state.storyAt + 1} / ${count} · press <strong>Now</strong> for the final result.</div>`;
}

function renderStory(detail) {
  const pipeline = detail.pipeline;
  if (!pipeline) return renderSummary(detail);
  const stages = pipeline.story;
  const task = detail.task;
  const risk = detail.evidence?.risk?.level || detail.summary.risk;
  const blocked = pipeline.blocked;
  const memory = memoryStatus(detail);
  const riskChip = risk && risk !== "low"
    ? `<span>Risk <strong>${esc(risk[0].toUpperCase() + risk.slice(1))}</strong></span>`
    : "";
  const hero = `<section class="story-main">
    <div class="story-hero-copy">
      <div class="eyebrow">${esc(task.product)} · report</div>
      <h2 class="story-answer">${esc(storyHeadline(detail))}</h2>
      <p class="story-lede">${esc(storyHeroText(detail))}</p>
      <div class="story-meta">
        <span><strong>${esc(task.product)}</strong></span>
        <span>Reported <strong>${esc(timeAgo(reportedAt(detail)))}</strong></span>
        <span class="memory-${esc(memory.tone)}">Memory <strong>${esc(memory.label)}</strong></span>
        ${riskChip}
      </div>
      <div class="hero-actions">${storyPrimary(detail)}<button type="button" class="btn ghost" data-action="copy">Copy link</button></div>
    </div>
    <img class="story-mira" src="/mira.svg" alt="Mira, the courier" width="140" height="140" />
  </section>`;
  const receipt = `<div id="story-receipt">${
    state.storyAt == null ? renderReceipt(detail) : replayBanner(detail)
  }</div>`;
  const replay = `<details class="replay-details" id="story-replay">
    <summary>How we got here · ${(pipeline.replay || []).length} step${(pipeline.replay || []).length === 1 ? "" : "s"}</summary>
    <div class="replay-body">${renderStoryReplay(detail)}</div>
  </details>`;
  return `<div class="story-body">
    <div class="story-left">${hero}${renderRoute(detail, stages)}${receipt}${replay}</div>
    ${renderStoryRail(detail, blocked)}
  </div>`;
}

function bindReplayControls() {
  $$("#story-replay [data-story-step]").forEach((button) => {
    button.addEventListener("click", () => {
      const replay = state.detail?.pipeline?.replay || [];
      if (!replay.length) return;
      const current = state.storyAt == null ? replay.length - 1 : state.storyAt;
      setStoryAt(current + Number(button.dataset.storyStep));
    });
  });
  $$("#story-replay [data-story-play]").forEach((button) =>
    button.addEventListener("click", toggleStoryPlay),
  );
  $$("#story-replay [data-story-live]").forEach((button) => {
    button.addEventListener("click", () => {
      stopStory();
      state.storyAt = null;
      refreshStoryReplay();
      history.replaceState(null, "", taskHash(state.selected));
    });
  });
  const range = $("#story-range");
  if (range) {
    range.addEventListener("change", (event) => setStoryAt(Number(event.target.value)));
  }
}

function bindStory() {
  $$("#detail [data-action='blocked']").forEach((button) => {
    button.addEventListener("click", () => {
      const target = $("#blocked");
      if (!target) return;
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.classList.add("pulse");
      window.setTimeout(() => target.classList.remove("pulse"), 1200);
    });
  });
  bindReplayControls();
  $$("#detail [data-action='cinema']").forEach((button) => {
    button.addEventListener("click", toggleCinema);
  });
}

function refreshStoryReplay() {
  const detail = state.detail;
  if (!detail || state.view !== "story") return;
  layoutRoute(detail);
  const receipt = $("#story-receipt");
  if (receipt) {
    receipt.innerHTML = state.storyAt == null ? renderReceipt(detail) : replayBanner(detail);
  }
  const body = $("#story-replay .replay-body");
  if (body) body.innerHTML = renderStoryReplay(detail);
  bindReplayControls();
}

function setStoryAt(index) {
  const replay = state.detail?.pipeline?.replay || [];
  if (!replay.length) return;
  stopStory();
  state.storyAt = Math.max(0, Math.min(replay.length - 1, index));
  refreshStoryReplay();
  history.replaceState(null, "", taskHash(state.selected));
}

function toggleStoryPlay() {
  if (state.storyTimer) {
    stopStory();
    refreshStoryReplay();
    return;
  }
  const replay = state.detail?.pipeline?.replay || [];
  if (!replay.length) return;
  if (state.storyAt == null || state.storyAt >= replay.length - 1) state.storyAt = 0;
  state.storyTimer = window.setInterval(() => {
    const scenes = state.detail?.pipeline?.replay || [];
    if (!scenes.length) {
      stopStory();
      return;
    }
    if (state.storyAt == null || state.storyAt >= scenes.length - 1) {
      stopStory();
      refreshStoryReplay();
      return;
    }
    state.storyAt += 1;
    refreshStoryReplay();
  }, 850);
  refreshStoryReplay();
}

function toggleCinema() {
  const active = document.body.dataset.cinema === "true";
  document.body.dataset.cinema = active ? "false" : "true";
  toast(active ? "Present mode off" : "Present mode on — Esc to exit.");
}
function renderTabs() {
  return `<div class="view-tabs" role="tablist" aria-label="Detail view">
    <button type="button" class="view-tab ${state.view === "story" ? "active" : ""}" data-view="story" role="tab" aria-selected="${state.view === "story"}">Story</button>
    <button type="button" class="view-tab ${state.view === "evidence" ? "active" : ""}" data-view="evidence" role="tab" aria-selected="${state.view === "evidence"}">Evidence <span class="faint">for engineers</span></button>
    <button type="button" class="view-tab ${state.view === "release" ? "active" : ""}" data-view="release" role="tab" aria-selected="${state.view === "release"}">Release <span class="faint">deliver & confirm</span></button>
    <button type="button" class="view-tab ${state.view === "thread" ? "active" : ""}" data-view="thread" role="tab" aria-selected="${state.view === "thread"}">Thread <span class="faint">worklog</span></button>
  </div>`;
}

function bindView() {
  $$("#detail .view-tab").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  $$("#detail [data-action='evidence']").forEach((button) => {
    button.addEventListener("click", () => setView("evidence"));
  });
  $$("#detail [data-action='copy']").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(location.href);
        toast("Link copied.");
      } catch {
        toast("Could not copy the link.");
      }
    });
  });
  $$("#detail [data-action='run-readiness']").forEach((button) => {
    button.addEventListener("click", async () => {
      const detail = state.detail;
      if (!detail || !state.writable) return;
      button.disabled = true;
      try {
        const result = await api("/api/readiness", {
          method: "POST",
          headers: { "X-Works-Write": "1" },
          body: { repo: detail.task.repo },
        });
        detail.readiness = result;
        toast(result.status === "pass" ? "Readiness is green." : "Readiness is red.");
        renderDetail();
      } catch (error) {
        toast(`Readiness failed: ${error.message}`);
        button.disabled = false;
      }
    });
  });
  $$("#detail [data-action='release']").forEach((button) => {
    button.addEventListener("click", () =>
      performAction(button, "release", {}, () => "Release approved. The task is released."),
    );
  });
  $$("#detail [data-action='open-release']").forEach((button) => {
    button.addEventListener("click", () => setView("release"));
  });
  $$("#detail [data-action='deliver']").forEach((button) => {
    button.addEventListener("click", () => {
      const provider = $("#deliver-provider")?.value || "none";
      const tracker = $("#deliver-tracker")?.value || "";
      const dry = Boolean($("#deliver-dry")?.checked);
      return performAction(
        button,
        "deliver",
        { provider, tracker: tracker || null, dry_run: dry },
        (result) =>
          result.delivery?.dry_run
            ? "Dry run: the commit is ready; nothing was pushed."
            : `Delivered ${String(result.delivery?.commit || "").slice(0, 10)}.`,
      );
    });
  });
  $$("#detail [data-action='confirm']").forEach((button) => {
    button.addEventListener("click", () => {
      const url = $("#confirm-url")?.value?.trim() || null;
      const command = $("#confirm-command")?.value?.trim() || null;
      const tracker = $("#confirm-tracker")?.value || "";
      const close = Boolean($("#confirm-close")?.checked);
      const force = button.dataset.force === "1";
      return performAction(
        button,
        "confirm",
        { url, command, tracker: tracker || null, close, force },
        (result) =>
          result.confirmation?.ok
            ? "Confirmed: the released commit passed."
            : "Confirmation failed; the result is recorded.",
      );
    });
  });
  $$("#detail [data-action='team-verify']").forEach((button) => {
    button.addEventListener("click", () =>
      performAction(
        button,
        "team-verify",
        {},
        (result) =>
          result.team?.verdict === "allow"
            ? "Team verdict: allow."
            : "Team verdict: block.",
      ),
    );
  });
  $$("#detail [data-action='detector-create']").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const result = await api("/api/sources", {
          method: "POST",
          headers: { "X-Works-Write": "1" },
          body: { source: "detector", name: button.dataset.name },
        });
        toast(`${result.found} alert(s), ${result.created} new task(s).`);
        await loadTasks();
        await refreshDetectors();
      } catch (error) {
        toast(`Detector intake failed: ${error.message}`);
        button.disabled = false;
      }
    });
  });
  $$("#detail [data-action='refresh-detectors']").forEach((button) => {
    button.addEventListener("click", () => refreshDetectors());
  });
  $$("#detail [data-timeline-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      state.timelineFilter = button.dataset.timelineFilter;
      renderDetail();
    });
  });
  $$("#detail details[data-artifact-url]").forEach((node) => {
    node.addEventListener("toggle", async () => {
      if (!node.open || node.dataset.loaded === "1") return;
      node.dataset.loaded = "1";
      const pre = node.querySelector("pre");
      try {
        const response = await fetch(node.dataset.artifactUrl);
        pre.textContent = (await response.text()).slice(0, 40_000);
      } catch (error) {
        pre.textContent = `Could not load: ${error.message}`;
      }
    });
  });
  const threadForm = $("#thread-form");
  if (threadForm) {
    threadForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = $("#thread-input");
      const message = input.value.trim();
      if (!message) return;
      const button = threadForm.querySelector("button[type='submit']");
      if ((state.composeMode || "ask") === "ask" && state.ai?.available) {
        input.value = "";
        await streamAsk(message, button);
        return;
      }
      button.disabled = true;
      try {
        await api("/api/actions", {
          method: "POST",
          headers: { "X-Works-Write": "1" },
          body: { action: "add-context", task_id: state.selected, message },
        });
        input.value = "";
        toast("Context added to the worklog.");
        await loadDetail(state.selected);
      } catch (error) {
        toast(`Could not add context: ${error.message}`);
      } finally {
        button.disabled = false;
      }
    });
  }
  $$("#detail [data-compose-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.composeMode = button.dataset.composeMode;
      renderDetail();
    });
  });
  $$("#detail [data-action='commentary']").forEach((button) => {
    button.addEventListener("click", () =>
      performAction(
        button,
        "commentary",
        {},
        (result) => `${(result.messages || []).length} commentary message(s) added.`,
      ),
    );
  });
  $$("#detail [data-action='compare-runs']").forEach((button) => {
    button.addEventListener("click", () => openRunsDialog());
  });
  $$("#detail [data-lightbox]").forEach((image) => {
    image.addEventListener("click", () =>
      openLightbox(image.dataset.lightbox, image.alt || "artifact"),
    );
  });
  $$("#detail [data-event-seq]").forEach((node) => {
    node.addEventListener("click", () => openEventDialog(Number(node.dataset.eventSeq)));
  });
  $$("#detail [data-compare]").forEach((range) => {
    range.addEventListener("input", () => {
      range.closest(".artifact-compare-wrap")?.style.setProperty("--pos", `${range.value}%`);
    });
  });
  $$("#detail [data-thread-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.threadAction;
      if (action === "open-run") {
        openRunDialog();
        return;
      }
      if (action === "open-release") {
        setView("release");
        return;
      }
      if (action === "open-evidence") {
        setView("evidence");
        return;
      }
      return performAction(button, action, {}, () => `${action} recorded.`);
    });
  });
}

function setView(view) {
  state.view = ["story", "evidence", "release", "thread"].includes(view) ? view : "story";
  localStorage.setItem("works.view.v3", state.view);
  if (state.selected) {
    history.replaceState(null, "", taskHash(state.selected));
  }
  stopStory();
  renderDetail();
}

function taskHash(id) {
  const suffix = state.view === "evidence" ? "/evidence" : state.view === "release" ? "/release" : state.view === "thread" ? "/thread" : "/story";
  const params = new URLSearchParams();
  if (state.view === "story" && state.storyAt != null) params.set("at", String(state.storyAt));
  const query = params.toString() ? `?${params.toString()}` : "";
  return `#/task/${encodeURIComponent(id)}${suffix}${query}`;
}

function renderDetail() {
  const detail = state.detail;
  if (!detail) {
    $("#empty").hidden = false;
    $("#detail").hidden = true;
    return;
  }
  const task = detail.task;
  const title = task.source?.title || `Task ${task.id}`;
  const label = state.view === "evidence" ? "Evidence" : state.view === "release" ? "Release" : state.view === "thread" ? "Thread" : "Story";
  $("#crumb").innerHTML = `<button type="button" class="crumb-link" id="crumb-home">Queue</button><span class="crumb-sep">/</span>${esc(label)}`;
  $("#crumb-home").addEventListener("click", () => clearSelection());
  $("#title").textContent = title;
  $("#subtitle").textContent = `${stateLabel(task.state)} · reported ${timeAgo(reportedAt(detail))}`;
  const body = state.view === "evidence" ? renderEvidence(detail) : state.view === "release" ? renderReleaseView(detail) : state.view === "thread" ? renderThread(detail) : renderStory(detail);
  $("#detail").innerHTML = `${renderTabs()}${body}`;
  $("#empty").hidden = true;
  $("#detail").hidden = false;
  bindView();
  if (state.view === "story") {
    bindStory();
    window.requestAnimationFrame(() => layoutRoute(detail));
  }
}

function clearSelection(updateHash = true) {
  stopStory();
  state.selected = null;
  state.detail = null;
  state.storyAt = null;
  state.storySelected = null;
  if (updateHash) history.replaceState(null, "", "#/");
  $("#crumb").textContent = "Queue";
  $("#title").textContent = "A signal in, a released fix out";
  $("#subtitle").textContent = "Select a report to read its story and evidence.";
  renderTasks();
  renderDetail();
}

async function loadHealth() {
  const health = await api("/api/health");
  state.writable = Boolean(health.write);
  state.ai = health.ai || null;
  $("#report").hidden = !state.writable;
  $("#intake").hidden = !state.writable;
  await Promise.all([loadProducts(), loadDetectors()]);
  if (state.detail) renderDetail();
}

async function loadProducts() {
  try {
    state.products = await api("/api/products");
  } catch {
    state.products = { configured: false, products: [], path: ".works/products.yaml" };
  }
  const list = $("#product-list");
  if (list) {
    list.innerHTML = (state.products.products || [])
      .map((item) => `<option value="${esc(item.name)}">${esc(item.repo)}</option>`)
      .join("");
  }
  if (state.detail) renderDetail();
}

async function loadDetectors(refresh = false) {
  try {
    state.detectors = await api(`/api/detectors${refresh ? "?refresh=1" : ""}`);
  } catch {
    state.detectors = { configured: false, detectors: [], path: ".works/detectors.yaml" };
  }
  const select = $("#detector-select");
  if (select) {
    select.innerHTML = (state.detectors.detectors || [])
      .map((item) => `<option value="${esc(item.name)}">${esc(item.name)} · ${esc(item.product)}</option>`)
      .join("");
  }
  if (state.detail) renderDetail();
}

function openIntake() {
  if (!state.writable) return;
  const dialog = $("#intake-dialog");
  const form = $("#intake-form");
  form.elements.product.value = state.detail?.task?.product || "";
  form.elements.repo.value = localStorage.getItem("works.repo") || "";
  toggleIntakeSource();
  dialog.showModal();
}

function toggleIntakeSource() {
  const form = $("#intake-form");
  const source = form.elements.source.value;
  $$("#intake-form [data-intake]").forEach((node) => {
    node.hidden = node.dataset.intake !== source;
  });
}

async function submitIntake(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type='submit']");
  const data = new FormData(form);
  const source = String(data.get("source") || "github");
  const body = {
    source,
    product: String(data.get("product") || "").trim(),
    repo: String(data.get("repo") || "").trim(),
  };
  if (source === "github") {
    body.repository = String(data.get("repository") || "").trim();
    body.label = String(data.get("label") || "").trim();
  } else if (source === "jira") {
    body.url = String(data.get("url") || "").trim();
    body.jql = String(data.get("jql") || "").trim();
  } else {
    body.name = String(data.get("detector") || "").trim();
  }
  button.disabled = true;
  try {
    const result = await api("/api/sources", {
      method: "POST",
      headers: { "X-Works-Write": "1" },
      body,
    });
    $("#intake-dialog").close();
    toast(`${result.found} signal(s), ${result.created} new task(s).`);
    await loadTasks();
    if (result.tasks?.length) selectTask(result.tasks[0]);
    else if (state.selected) await loadDetail(state.selected);
  } catch (error) {
    toast(`Import failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

function openReport() {
  if (!state.writable) return;
  const dialog = $("#report-dialog");
  const form = $("#report-form");
  form.elements.product.value = state.detail?.task?.product || "openjiuwen";
  form.elements.repo.value =
    state.detail?.task?.repo || localStorage.getItem("works.repo") || "";
  dialog.showModal();
  form.elements.product.focus();
}

async function submitReport(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type='submit']");
  const data = new FormData(form);
  const body = {
    repo: String(data.get("repo") || "").trim(),
    product: String(data.get("product") || "").trim(),
    ref: String(data.get("ref") || "").trim(),
    title: String(data.get("title") || "").trim(),
    kind: String(data.get("kind") || "manual"),
    task_kind: String(data.get("task_kind") || "fix"),
    flow: String(data.get("flow") || "fix-issue"),
  };
  button.disabled = true;
  try {
    const result = await api("/api/tasks", {
      method: "POST",
      headers: { "X-Works-Write": "1" },
      body,
    });
    if (body.repo) localStorage.setItem("works.repo", body.repo);
    $("#report-dialog").close();
    form.reset();
    await loadTasks();
    await loadProducts();
    selectTask(result.task.id);
    toast(result.created ? `Created ${result.task.id}. It is queued.` : `${result.task.id} already existed.`);
  } catch (error) {
    toast(`Create failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

async function loadTasks() {
  try {
    const data = await api("/api/tasks?limit=200");
    state.tasks = data.tasks || [];
    const products = [...new Set(state.tasks.map((task) => task.product).filter(Boolean))].sort();
    const select = $("#product-filter");
    if (select) {
      const current = state.productFilter;
      select.innerHTML =
        '<option value="">All products</option>' +
        products.map((product) => `<option value="${esc(product)}">${esc(product)}</option>`).join("");
      select.value = products.includes(current) ? current : "";
      state.productFilter = select.value;
    }
    const exists = state.selected && state.tasks.some((task) => task.id === state.selected);
    if (state.selected && !exists) {
      state.selected = null;
      state.detail = null;
    }
    renderTasks();
    if (!state.selected) renderDetail();
  } catch (error) {
    toast(`Queue unavailable: ${error.message}`);
  }
}

async function loadDetail(id) {
  try {
    const detail = await api(`/api/tasks/${encodeURIComponent(id)}`);
    state.detail = detail;
    state.selected = id;
    renderTasks();
    renderDetail();
  } catch (error) {
    toast(`Task unavailable: ${error.message}`);
  }
}

function selectTask(id, preserve = false) {
  if (!id) return;
  if (!preserve) {
    stopStory();
    state.storyAt = null;
    state.storySelected = null;
  }
  state.selected = id;
  history.replaceState(null, "", taskHash(id));
  renderTasks();
  loadDetail(id);
}

function nextTask(step) {
  if (!state.tasks.length) return;
  const index = state.tasks.findIndex((task) => task.id === state.selected);
  const next = state.tasks[(index + step + state.tasks.length) % state.tasks.length];
  selectTask(next.id);
}

function applyHash() {
  const match = location.hash.match(/^#\/task\/([^/?]+)(?:\/(story|summary|evidence|release|thread))?(?:\?(.*))?$/);
  if (match && match[2]) state.view = match[2] === "evidence" ? "evidence" : match[2] === "release" ? "release" : match[2] === "thread" ? "thread" : "story";
  const params = new URLSearchParams(match && match[3] ? match[3] : "");
  state.storyAt = params.has("at") ? Number(params.get("at")) : null;
  loadTasks().then(() => {
    if (match) {
      selectTask(decodeURIComponent(match[1]), true);
    } else {
      clearSelection(false);
    }
  });
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(next);
}

function toggleDensity() {
  const next = document.documentElement.dataset.density === "compact" ? "comfortable" : "compact";
  applyDensity(next);
}

function paletteItems(query) {
  const actions = [
    { label: "Story view", run: () => setView("story") },
    { label: "Evidence view", run: () => setView("evidence") },
    { label: "Release view", run: () => setView("release") },
    { label: "Thread view", run: () => setView("thread") },
    { label: "New task", run: openReport },
    { label: "Import signals", run: openIntake },
    { label: "Refresh", run: () => $("#refresh").click() },
    { label: "Toggle theme", run: toggleTheme },
    { label: "Toggle density", run: toggleDensity },
    { label: "Focus search", run: () => $("#search").focus() },
  ];
  const tasks = state.tasks.map((task) => ({
    label: `${task.title || task.id} · ${stateLabel(task.state)}`,
    run: () => selectTask(task.id),
  }));
  if (state.writable && state.detail) {
    actions.push({ label: "Open release actions", run: () => setView("release") });
    actions.push({
      label: "Verify with the team",
      run: () => document.querySelector("#detail [data-action='team-verify']")?.click(),
    });
    if (state.detail.delivery?.pr_url) {
      actions.push({
        label: "Copy pull request link",
        run: async () => {
          try {
            await navigator.clipboard.writeText(state.detail.delivery.pr_url);
            toast("Pull request link copied.");
          } catch {
            toast("Could not copy the link.");
          }
        },
      });
    }
  }
  const all = [...actions, ...tasks];
  const needle = query.trim().toLowerCase();
  return needle ? all.filter((item) => item.label.toLowerCase().includes(needle)) : all;
}

function renderPalette(query) {
  const results = $("#palette-results");
  const items = paletteItems(query).slice(0, 12);
  if (!items.length) {
    results.innerHTML = `<p class="muted small" style="padding:8px 10px">Nothing matches.</p>`;
    return;
  }
  results.innerHTML = items
    .map((item, index) => `<button type="button" class="palette-item${index === 0 ? " active" : ""}" data-index="${index}">${esc(item.label)}</button>`)
    .join("");
  $$("#palette-results .palette-item").forEach((button) => {
    button.addEventListener("click", () => {
      const item = items[Number(button.dataset.index)];
      $("#palette").close();
      item.run();
    });
  });
}

function openPalette() {
  const dialog = $("#palette");
  if (!dialog.open) dialog.showModal();
  $("#palette-input").value = "";
  renderPalette("");
  $("#palette-input").focus();
}

function bind() {
  $("#theme").addEventListener("click", toggleTheme);
  $("#density").addEventListener("click", toggleDensity);
  $("#cmdk").addEventListener("click", openPalette);
  $("#report").addEventListener("click", openReport);
  $("#factory").addEventListener("click", openFactory);
  $("#settings").addEventListener("click", openSettings);
  $("#factory-close").addEventListener("click", () => $("#factory-dialog").close());
  $("#factory-refresh").addEventListener("click", () => loadFactory());
  $("#settings-cancel").addEventListener("click", () => $("#settings-dialog").close());
  $("#settings-form").addEventListener("submit", saveSettings);
  $("#lightbox-close").addEventListener("click", () => $("#lightbox").close());
  $("#event-close").addEventListener("click", () => $("#event-dialog").close());
  $("#runs-close").addEventListener("click", () => $("#runs-dialog").close());
  $("#run-a").addEventListener("change", renderRunComparison);
  $("#run-b").addEventListener("change", renderRunComparison);
  $("#intake").addEventListener("click", openIntake);
  $("#report-cancel").addEventListener("click", () => $("#report-dialog").close());
  $("#intake-cancel").addEventListener("click", () => $("#intake-dialog").close());
  $("#report-form").addEventListener("submit", submitReport);
  $("#intake-form").addEventListener("submit", submitIntake);
  $("#intake-form").elements.source.addEventListener("change", toggleIntakeSource);
  $("#run-close").addEventListener("click", () => $("#run-dialog").close());
  $("#palette-input").addEventListener("input", (event) => renderPalette(event.target.value));
  $("#palette-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      const first = $("#palette-results .palette-item");
      if (first) first.click();
    }
  });
  $("#refresh").addEventListener("click", () => {
    loadTasks();
    if (state.selected) loadDetail(state.selected);
  });
  $("#search").addEventListener("input", (event) => {
    state.query = event.target.value;
    renderTasks();
  });
  $$(".filter").forEach((button) => {
    button.addEventListener("click", () => {
      state.filter = button.dataset.filter;
      $$(".filter").forEach((item) => item.classList.toggle("active", item === button));
      renderTasks();
    });
  });
  $("#product-filter").addEventListener("change", (event) => {
    state.productFilter = event.target.value;
    renderTasks();
  });
  $("#source-filter").addEventListener("change", (event) => {
    state.sourceFilter = event.target.value;
    renderTasks();
  });
  document.addEventListener("keydown", (event) => {
    const tag = document.activeElement?.tagName;
    const typing = tag === "INPUT" || tag === "TEXTAREA" || document.activeElement?.isContentEditable;
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openPalette();
      return;
    }
    if ($("#palette").open) {
      if (event.key === "Escape") $("#palette").close();
      return;
    }
    if (event.key === "Escape" && document.body.dataset.cinema === "true") {
      document.body.dataset.cinema = "false";
      return;
    }
    if (event.key === "c" && !typing) {
      event.preventDefault();
      toggleCinema();
      return;
    }
    if (event.key === "n" && !typing && state.writable) {
      event.preventDefault();
      openReport();
      return;
    }
    if (event.key === "?" && !typing) {
      event.preventDefault();
      $("#help").showModal();
    } else if (event.key === "/" && !typing) {
      event.preventDefault();
      $("#search").focus();
    } else if (event.key === "Escape") {
      if ($("#help").open) $("#help").close();
      if (typing) {
        $("#search").value = "";
        state.query = "";
        renderTasks();
        $("#search").blur();
      }
    } else if (event.key === "j" && !typing) {
      event.preventDefault();
      nextTask(1);
    } else if (event.key === "k" && !typing) {
      event.preventDefault();
      nextTask(-1);
    } else if (event.key === "r" && !typing) {
      event.preventDefault();
      $("#refresh").click();
    } else if (event.key === "t" && !typing) {
      event.preventDefault();
      toggleTheme();
    }
  });
  window.addEventListener("hashchange", applyHash);
  startPolling();
}

function boot() {
  const storedTheme = localStorage.getItem(themeKey);
  const storedDensity = localStorage.getItem(densityKey);
  applyTheme(storedTheme || (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
  applyDensity(storedDensity || "comfortable");
  bind();
  void loadHealth().catch(() => {});
  applyHash();
}

boot();
