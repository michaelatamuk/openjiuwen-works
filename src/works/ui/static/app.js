const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  tasks: [],
  selected: null,
  detail: null,
  filter: "all",
  query: "",
  view: localStorage.getItem("works.view") || "summary",
};

const stateHuman = {
  queued: "Waiting in queue",
  reproducing: "Confirming the problem",
  reproduced: "Problem confirmed",
  planning: "Planning the fix",
  plan_approved: "Plan approved",
  building: "Building the fix",
  checking: "Checking the fix",
  proved: "Fixed and verified",
  waiting_review: "Waiting for a person",
  waiting_ci: "Running checks",
  waiting_deploy: "Delivering the fix",
  releasing: "Delivering the fix",
  released: "Delivered",
  reverted: "Reverted",
  blocked: "Needs attention",
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
};

const groupDefs = [
  ["needs", "Needs you", ["blocked", "waiting_review", "waiting_ci", "waiting_deploy"]],
  ["working", "Working", ["queued", "reproducing", "reproduced", "planning", "plan_approved", "building", "checking", "releasing"]],
  ["ready", "Ready", ["proved"]],
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
    .map(([id, label, states]) => {
      const group = tasks.filter((task) => states.includes(task.state));
      if (!group.length) return "";
      const rows = group
        .map((task) => {
          const active = task.id === state.selected ? " active" : "";
          const risk = task.risk ? pill(riskLabel(task.risk), riskTone(task.risk)) : "";
          const title = task.title || `Task ${task.id}`;
          const meta = `${sourceLabel(task.source.split(":")[0])} · ${task.product} · ${stateLabel(task.state)}`;
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
      return `<div class="group-label">${esc(label)}<span>${group.length}</span></div>${rows}`;
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
  const gate = (detail.timeline || []).find((event) => event.type === "gate.decided");
  if (gate) {
    const by = gate.data.by === "cli" ? "a person" : "the flow";
    return `Approved by ${by} ${timeAgo(gate.ts)}.`;
  }
  const decision = detail.evidence?.decision;
  if (decision) return `${decision.requires_approval ? "A person still needs to approve." : "No approval was required."}`;
  return "No approval has been recorded yet.";
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
  if (state === "released") return "The fix is back where it was seen. The report is closed.";
  if (state === "reverted") return "The release was reverted; a person is deciding the next step.";
  if (state.startsWith("waiting")) return "The next step starts when the waiting event arrives.";
  if (state === "queued") return "The factory will pick it up from the queue.";
  return "The factory is still preparing the change.";
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
     <button class="btn ghost" data-action="copy">Copy link</button>`,
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
  ];
  return card(
    "Run metadata",
    `<dl class="kv">${rows.map(([key, value]) => `<dt>${esc(key)}</dt><dd class="mono">${esc(value)}</dd>`).join("")}</dl>`,
  );
}

function renderTimeline(timeline) {
  const rows = (timeline || [])
    .slice()
    .reverse()
    .map((event) => `<li>
      <time>${esc(new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</time>
      <span class="type">${esc(timelineLabel(event.type))}</span>
      <span class="data" title="${esc(eventSummary(event))}">${esc(eventSummary(event))}</span>
    </li>`);
  return card(
    "Timeline",
    `<ol class="timeline">${rows.join("") || "<li class='muted small'>No events.</li>"}</ol>`,
    { actions: `${esc((timeline || []).length)} recent events` },
  );
}

function renderEvidence(detail) {
  const evidence = detail.evidence;
  return evidence
    ? `${renderEvidenceMeta(detail)}<div class="grid">
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
          ${renderResidual(evidence)}
          ${renderCost(evidence)}
          ${renderTimeline(detail.timeline)}
        </div>
      </div>`
    : `<div class="grid"><div class="stack">${renderEmptyProof()}</div><div class="stack">${renderReadiness(detail)}${renderFeatures(detail)}${renderTimeline(detail.timeline)}</div></div>`;
}

function renderTabs() {
  return `<div class="view-tabs" role="tablist" aria-label="Detail view">
    <button type="button" class="view-tab ${state.view === "summary" ? "active" : ""}" data-view="summary" role="tab" aria-selected="${state.view === "summary"}">Summary</button>
    <button type="button" class="view-tab ${state.view === "evidence" ? "active" : ""}" data-view="evidence" role="tab" aria-selected="${state.view === "evidence"}">Evidence</button>
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
}

function setView(view) {
  state.view = view === "evidence" ? "evidence" : "summary";
  localStorage.setItem("works.view", state.view);
  if (state.selected) {
    history.replaceState(null, "", taskHash(state.selected));
  }
  renderDetail();
}

function taskHash(id) {
  return `#/task/${encodeURIComponent(id)}${state.view === "evidence" ? "/evidence" : ""}`;
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
  $("#crumb").innerHTML = `<button type="button" class="crumb-link" id="crumb-home">Queue</button><span class="crumb-sep">/</span>Fix report`;
  $("#crumb-home").addEventListener("click", () => clearSelection());
  $("#title").textContent = title;
  $("#subtitle").textContent = `${sourceLabel(task.source.kind)} · ${stateLabel(task.state)} · ${timeAgo(task.updated_at)}`;
  const body = state.view === "evidence" ? renderEvidence(detail) : renderSummary(detail);
  $("#detail").innerHTML = `${renderTabs()}${body}`;
  $("#empty").hidden = true;
  $("#detail").hidden = false;
  bindView();
}

function clearSelection(updateHash = true) {
  state.selected = null;
  state.detail = null;
  if (updateHash) history.replaceState(null, "", "#/");
  $("#crumb").textContent = "Queue";
  $("#title").textContent = "A signal in, a released fix out";
  $("#subtitle").textContent = "Select a report to read its Summary or Evidence.";
  renderTasks();
  renderDetail();
}

async function loadTasks() {
  try {
    const data = await api("/api/tasks?limit=200");
    state.tasks = data.tasks || [];
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

function selectTask(id) {
  if (!id) return;
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
  const match = location.hash.match(/^#\/task\/([^/]+)(?:\/(summary|evidence))?$/);
  if (match && match[2]) state.view = match[2];
  loadTasks().then(() => {
    if (match) {
      selectTask(decodeURIComponent(match[1]));
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
    { label: "Summary view", run: () => setView("summary") },
    { label: "Evidence view", run: () => setView("evidence") },
    { label: "Refresh", run: () => $("#refresh").click() },
    { label: "Toggle theme", run: toggleTheme },
    { label: "Toggle density", run: toggleDensity },
    { label: "Focus search", run: () => $("#search").focus() },
  ];
  const tasks = state.tasks.map((task) => ({
    label: `${task.title || task.id} · ${stateLabel(task.state)}`,
    run: () => selectTask(task.id),
  }));
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
    loadTasks();
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
