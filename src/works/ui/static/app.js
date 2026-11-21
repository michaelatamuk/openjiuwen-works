const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  tasks: [],
  selected: null,
  detail: null,
  filter: "all",
  query: "",
  loading: false,
};

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
  return String(value ?? "unknown").replaceAll("_", " ");
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

async function api(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `${response.status} ${response.statusText}`);
  return body;
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
  const tasks = state.tasks.filter((task) => {
    if (state.filter === "waiting" && !String(task.state).startsWith("waiting")) return false;
    if (state.filter === "blocked" && !["blocked", "reverted", "flaky_test"].includes(task.state)) return false;
    if (state.filter === "proved" && !["proved", "released"].includes(task.state)) return false;
    if (!query) return true;
    return [task.title, task.id, task.source, task.product, task.flow, task.state]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
  if (!tasks.length) {
    list.innerHTML = `<p class="muted small" style="padding:16px 12px">No tasks match.</p>`;
    return;
  }
  list.innerHTML = tasks
    .map((task) => {
      const active = task.id === state.selected ? " active" : "";
      const risk = task.risk ? pill(task.risk, riskTone(task.risk)) : "";
      const title = task.title || `Task ${task.id}`;
      const meta = `${task.source} · ${task.product} · ${task.flow}`;
      return `<button type="button" class="task${active}" data-id="${esc(task.id)}"${
        active ? ' aria-current="true"' : ""
      }>
        <span class="dot ${esc(task.state)}" aria-hidden="true"></span>
        <span class="task-main">
          <span class="task-title">${esc(title)}</span>
          <span class="task-meta">${esc(meta)}</span>
        </span>
        <span class="task-side">${risk}<span class="time">${esc(timeAgo(task.updated_at))}</span></span>
      </button>`;
    })
    .join("");
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
    .map((check) => `<div class="check ${check.ok ? "pass" : "fail"}">
      <span class="box" aria-hidden="true">${check.ok ? "✓" : "!"}</span>
      <span>${esc(check.label)}</span>
    </div>`)
    .join("");
  const ratio = readiness.total ? Math.round((readiness.passed / readiness.total) * 100) : 0;
  return card(
    "Readiness",
    `${checks}
    <div class="progress"><i style="width:${ratio}%"></i></div>
    <p class="muted small" style="margin:10px 0 0">${esc(readiness.note)}</p>`,
    { actions: `${esc(readiness.passed)}/${esc(readiness.total)}` },
  );
}

function renderFeatures(detail) {
  const features = detail.features;
  if (!features?.available) {
    return card("Feature coverage", `<p class="muted small">${esc(features?.note || "No feature map yet.")}</p>`);
  }
  return card(
    "Feature coverage",
    `<p class="muted small">Feature maps: ${features.files.map((file) => `<code>${esc(file)}</code>`).join(", ")}</p>`,
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

function renderTimeline(timeline) {
  const rows = (timeline || []).slice().reverse().map((event) => {
    const data = Object.entries(event.data || {})
      .map(([key, value]) => `${key}=${value}`)
      .join(" · ");
    return `<li>
      <time>${esc(new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</time>
      <span class="type">${esc(event.type)}</span>
      <span class="data" title="${esc(data)}">${esc(data)}</span>
    </li>`;
  });
  return card(
    "Timeline",
    `<ol class="timeline">${rows.join("") || "<li class='muted small'>No events.</li>"}</ol>`,
    { actions: `${esc((timeline || []).length)} recent events` },
  );
}

function renderDetail() {
  const detail = state.detail;
  if (!detail) {
    $("#empty").hidden = false;
    $("#detail").hidden = true;
    return;
  }
  const task = detail.task;
  const evidence = detail.evidence;
  const summary = detail.summary;
  const title = task.source?.title || `Task ${task.id}`;
  $("#crumb").textContent = `${task.product} / ${task.flow}`;
  $("#title").textContent = title;
  $("#subtitle").textContent = `${task.source.kind}:${task.source.ref} · ${task.kind} · ${task.id}`;
  const statePill = pill(stateLabel(task.state), stateTone(task.state));
  const risk = evidence?.risk || { level: summary.risk };
  const decision = evidence?.decision || { verb: summary.decision };
  const checks = evidence?.checks_sha ? `${evidence.checks_sha.slice(0, 10)}…` : "—";
  const cost = evidence ? `${fmtUsd(evidence.usd)} · ${fmtMs(evidence.duration_ms)}` : "—";
  const proof = evidence?.proof_sha256 ? `${evidence.proof_sha256.slice(0, 10)}…` : "—";

  const head = `<div class="pill-row" style="margin:0 0 16px">
    ${statePill}
    ${pill(task.kind, task.kind === "check-change" ? "amber" : "blue")}
    ${risk.level ? pill(`risk ${risk.level}`, riskTone(risk.level)) : ""}
    ${decision.verb ? pill(`decision ${decision.verb}`, "violet") : ""}
    ${summary.would_block ? pill(`${summary.would_block} would-block`, "amber") : ""}
    <a class="pill" href="#/task/${esc(task.id)}">deep link</a>
  </div>`;

  const summaryCards = `<div class="summary">
    <div class="metric"><div class="label">State</div><div class="value">${esc(stateLabel(task.state))}</div><div class="hint">${esc(timeAgo(task.updated_at))}</div></div>
    <div class="metric"><div class="label">Risk</div><div class="value">${esc((risk.level || "—").toUpperCase())}</div><div class="hint">${esc(risk.required_reviewers ? `${risk.required_reviewers} reviewer(s)` : "not rated")}</div></div>
    <div class="metric"><div class="label">Proof</div><div class="value mono">${esc(proof)}</div><div class="hint">${esc(evidence?.stop_reason || "no run")}</div></div>
    <div class="metric"><div class="label">Cost</div><div class="value">${esc(cost)}</div><div class="hint">${esc(checks)} checks</div></div>
  </div>`;

  const proofSections = evidence
    ? `<div class="stack">
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
        ${renderResidual(evidence)}
        ${renderCost(evidence)}
        ${renderTimeline(detail.timeline)}
      </div>`
    : `<div class="stack">${renderEmptyProof()}</div>
      <div class="stack">
        ${renderReadiness(detail)}
        ${renderFeatures(detail)}
        ${renderTimeline(detail.timeline)}
      </div>`;

  $("#detail").innerHTML = `${head}${summaryCards}<div class="grid">${proofSections}</div>`;
  $("#empty").hidden = true;
  $("#detail").hidden = false;
}

async function loadTasks({ keepSelection = true, selectFirst = true } = {}) {
  try {
    const data = await api("/api/tasks?limit=200");
    state.tasks = data.tasks || [];
    renderTasks();
    const exists = state.tasks.some((task) => task.id === state.selected);
    if (!exists && keepSelection && state.tasks.length) {
      if (selectFirst) selectTask(state.tasks[0].id);
    } else if (!state.tasks.length) {
      state.selected = null;
      state.detail = null;
      renderDetail();
    }
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

function selectTask(id) {
  if (!id) return;
  state.selected = id;
  history.replaceState(null, "", `#/task/${encodeURIComponent(id)}`);
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
  const match = location.hash.match(/^#\/task\/(.+)$/);
  loadTasks({ keepSelection: false, selectFirst: false }).then(() => {
    if (match) {
      selectTask(decodeURIComponent(match[1]));
    } else if (state.tasks.length) {
      selectTask(state.tasks[0].id);
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

function bind() {
  $("#theme").addEventListener("click", toggleTheme);
  $("#density").addEventListener("click", toggleDensity);
  $("#refresh").addEventListener("click", () => {
    loadTasks({ keepSelection: true });
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
  document.addEventListener("keydown", (event) => {
    const tag = document.activeElement?.tagName;
    const typing = tag === "INPUT" || tag === "TEXTAREA" || document.activeElement?.isContentEditable;
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
  window.setInterval(() => {
    loadTasks({ keepSelection: true, selectFirst: false });
    if (state.selected) loadDetail(state.selected);
  }, 15_000);
}

function boot() {
  const storedTheme = localStorage.getItem(themeKey);
  const storedDensity = localStorage.getItem(densityKey);
  applyTheme(storedTheme || (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
  applyDensity(storedDensity || "comfortable");
  bind();
  applyHash();
}

boot();
