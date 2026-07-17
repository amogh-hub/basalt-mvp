"use strict";

const state = {
  overview: null,
  proof: null,
  bootstrap: { actions_enabled: false, action_token: "" },
};

const byId = (id) => document.getElementById(id);

function text(id, value) {
  const node = byId(id);
  if (node) node.textContent = value == null ? "" : String(value);
}

function clear(node) {
  node.replaceChildren();
}

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content != null) node.textContent = String(content);
  return node;
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(Number(value || 0));
}

function shortHash(value) {
  const raw = String(value || "");
  return raw ? raw.slice(0, 14) : "unknown";
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

async function api(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  if (options.action) headers["X-Basalt-Action-Token"] = state.bootstrap.action_token;
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data?.error?.message || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data;
}

function banner(message, kind = "good") {
  const node = byId("banner");
  node.textContent = message;
  node.className = `banner ${kind}`;
  window.setTimeout(() => node.classList.add("hidden"), 4500);
}

function statusClass(status) {
  if (status === "VERIFIED") return "good";
  if (["WEAK_PROOF", "NEEDS_HUMAN_REVIEW", "AWAITING_APPROVAL", "APPROVED"].includes(status)) return "warn";
  if (["NOT_VERIFIED", "BLOCKED_BY_POLICY", "ROLLED_BACK", "REJECTED", "FAILED"].includes(status)) return "bad";
  return "neutral";
}

function switchView(section) {
  document.querySelectorAll(".view").forEach((node) => node.classList.toggle("active", node.id === section));
  document.querySelectorAll(".nav-item").forEach((node) => node.classList.toggle("active", node.dataset.section === section));
  window.history.replaceState(null, "", `#${section}`);
}

function renderRoadmap(items) {
  const container = byId("roadmap-list");
  clear(container);
  items.forEach((item) => {
    const row = element("div", `roadmap-item ${String(item.status).toLowerCase()}`);
    row.append(element("span", "roadmap-number", String(item.phase).padStart(2, "0")));
    row.append(element("span", "roadmap-name", item.name));
    row.append(element("span", "roadmap-status", item.status));
    container.append(row);
  });
}

function runRow(item, compact = false) {
  const wrapper = element("div", "activity-item");
  const info = element("div");
  info.append(element("strong", "", item.task || item.run_id || "Agent transaction"));
  info.append(element("p", "", compact ? formatDate(item.updated_at) : `${item.run_id || ""} · ${formatDate(item.updated_at)}`));
  wrapper.append(info);
  wrapper.append(element("span", `status-mini ${item.status || ""}`, item.status || "UNKNOWN"));
  return wrapper;
}

function renderOverview(data) {
  state.overview = data;
  text("project-name", data.project.name);
  text("project-path", data.project.path);
  text("intent-copy", data.truth.intent);
  text("proof-score", data.truth.score);
  byId("score-ring").style.setProperty("--score-angle", `${Math.max(0, Math.min(100, data.truth.score)) * 3.6}deg`);

  const verdict = byId("verdict-badge");
  verdict.textContent = data.truth.status;
  verdict.className = `status-badge ${statusClass(data.truth.status)}`;
  text("risk-badge", `Risk ${data.truth.risk}`);
  text("freshness-badge", data.truth.graph_fresh ? "Graph fresh" : "Graph stale");

  text("checks-metric", `${data.proof.checks.passed}/${data.proof.checks.total}`);
  text("checks-sub", `${data.proof.checks.failed} failed · ${data.proof.checks.skipped} skipped`);
  text("mutation-metric", data.proof.mutations.killed);
  text("mutation-sub", `${data.proof.mutations.survived} survived`);
  text("edges-metric", formatNumber(data.graph.edges));
  text("symbols-sub", `${formatNumber(data.graph.symbols)} symbols`);
  text("approvals-metric", data.approvals.pending);
  text("graph-state", `state ${shortHash(data.graph.state_hash)}`);
  text("graph-files", formatNumber(data.graph.files));
  text("graph-symbols", formatNumber(data.graph.symbols));
  text("graph-features", formatNumber(data.graph.features));
  text("graph-tests", formatNumber(data.graph.test_mappings));
  text("transaction-count", `${data.transactions.total} total`);
  text("approval-count", `${data.approvals.pending} pending`);
  text("artifact-count", `${data.artifacts.count} artifacts`);

  renderRoadmap(data.roadmap || []);
  const recent = byId("recent-runs");
  clear(recent);
  if (!data.transactions.recent.length) {
    recent.className = "activity-list empty-state";
    recent.textContent = "No agent transactions yet.";
  } else {
    recent.className = "activity-list";
    data.transactions.recent.slice(0, 5).forEach((item) => recent.append(runRow(item, true)));
  }
  renderRuns(data.transactions.recent || []);
  renderApprovals(data.approvals.items || []);
  renderArtifacts(data.artifacts.items || []);
  renderLanguages(data.graph.languages || {});
}

function renderProof(report) {
  state.proof = report;
  const checks = report.checks || [];
  const findings = report.security_findings || [];
  const mutations = report.mutations || [];
  text("proof-passed", checks.filter((item) => item.status === "PASS").length);
  text("proof-failed", checks.filter((item) => item.status === "FAIL").length);
  text("proof-survived", mutations.filter((item) => item.survived === true).length);
  text("proof-high", findings.filter((item) => String(item.level).toUpperCase() === "HIGH").length);
  text("proof-sandbox", `Sandbox ${report.sandbox || "unknown"}`);
  text("proof-finished", report.finished_at ? `Finished ${formatDate(report.finished_at)}` : "No verification yet");

  const body = byId("checks-table");
  clear(body);
  if (!checks.length) {
    const row = document.createElement("tr");
    const cell = element("td", "empty-state", "No proof checks loaded.");
    cell.colSpan = 5;
    row.append(cell);
    body.append(row);
  } else {
    checks.forEach((item) => {
      const row = document.createElement("tr");
      row.append(element("td", "", item.name));
      const statusCell = document.createElement("td");
      statusCell.append(element("span", `status-mini ${item.status}`, item.status));
      row.append(statusCell);
      row.append(element("td", "", item.sandbox || "—"));
      row.append(element("td", "", `${item.duration_ms || 0} ms`));
      row.append(element("td", "", item.message || "—"));
      body.append(row);
    });
  }
  renderStack("findings-list", findings, (item) => ({
    title: `${String(item.level).toUpperCase()} · ${item.rule}`,
    copy: `${item.file}:${item.line} — ${item.message}`,
  }), "No security, policy, dependency or quality findings.");
  renderStack("mutations-list", mutations, (item) => ({
    title: `${item.survived ? "SURVIVED" : "KILLED"} · ${item.mutation_type}`,
    copy: `${item.file}${item.line ? `:${item.line}` : ""} — ${item.message}`,
  }), "No mutation evidence generated.");
}

function renderStack(id, items, mapper, emptyCopy) {
  const container = byId(id);
  clear(container);
  if (!items.length) {
    container.className = "stack-list empty-state";
    container.textContent = emptyCopy;
    return;
  }
  container.className = "stack-list";
  items.slice(0, 16).forEach((item) => {
    const mapped = mapper(item);
    const card = element("div", "stack-item");
    card.append(element("strong", "", mapped.title));
    card.append(element("p", "", mapped.copy));
    container.append(card);
  });
}

function renderRuns(runs) {
  const body = byId("runs-table");
  clear(body);
  if (!runs.length) {
    const row = document.createElement("tr");
    const cell = element("td", "empty-state", "No governed transactions recorded.");
    cell.colSpan = 6;
    row.append(cell);
    body.append(row);
    return;
  }
  runs.forEach((item) => {
    const row = document.createElement("tr");
    row.append(element("td", "", item.run_id || "—"));
    row.append(element("td", "", item.task || "—"));
    const statusCell = document.createElement("td");
    statusCell.append(element("span", `status-mini ${item.status || ""}`, item.status || "UNKNOWN"));
    row.append(statusCell);
    row.append(element("td", "", item.risk || "—"));
    row.append(element("td", "", formatDate(item.updated_at)));
    const actionCell = document.createElement("td");
    const button = element("button", "text-button", "Inspect");
    button.type = "button";
    button.addEventListener("click", () => showRun(item.run_id));
    actionCell.append(button);
    row.append(actionCell);
    body.append(row);
  });
}

async function showRun(runId) {
  try {
    const run = await api(`/api/v1/runs/${encodeURIComponent(runId)}`);
    text("run-detail-title", run.run_id);
    const container = byId("run-detail");
    clear(container);
    const entries = [
      ["Status", run.status], ["Task", run.task], ["Role", run.agent_role],
      ["Base state", shortHash(run.base_state_hash)], ["Current state", shortHash(run.current_state_hash)],
      ["Attempt", `${run.attempt}/${run.max_attempts}`], ["Files", (run.impacted_files || []).length],
      ["Tests", (run.impacted_tests || []).length], ["Features", (run.impacted_features || []).length],
      ["Message", run.message], ["Created", formatDate(run.created_at)], ["Updated", formatDate(run.updated_at)],
    ];
    entries.forEach(([label, value]) => {
      const card = element("div", "detail-card");
      card.append(element("span", "", label));
      card.append(element("strong", "", value || "—"));
      container.append(card);
    });
    const actions = element("div", "approval-actions");
    if (run.status === "AWAITING_APPROVAL") {
      const approve = element("button", "button primary", "Approve");
      approve.type = "button";
      approve.disabled = !state.bootstrap.actions_enabled;
      approve.addEventListener("click", () => openActionDialog("approve", run.run_id));
      const reject = element("button", "button secondary", "Reject");
      reject.type = "button";
      reject.disabled = !state.bootstrap.actions_enabled;
      reject.addEventListener("click", () => openActionDialog("reject", run.run_id));
      actions.append(approve, reject);
    } else if (run.status === "APPROVED") {
      const apply = element("button", "button primary", "Apply and prove");
      apply.type = "button";
      apply.disabled = !state.bootstrap.actions_enabled;
      apply.addEventListener("click", () => openActionDialog("apply", run.run_id));
      actions.append(apply);
    } else if (run.status === "VERIFIED") {
      const rollback = element("button", "button secondary", "Rollback transaction");
      rollback.type = "button";
      rollback.disabled = !state.bootstrap.actions_enabled;
      rollback.addEventListener("click", () => openActionDialog("rollback", run.run_id));
      actions.append(rollback);
    }
    if (actions.childElementCount) container.append(actions);
    byId("run-detail-panel").classList.remove("hidden");
    switchView("transactions");
  } catch (error) {
    banner(error.message, "bad");
  }
}

function renderApprovals(items) {
  const container = byId("approval-list");
  clear(container);
  if (!items.length) {
    container.className = "approval-list empty-state";
    container.textContent = "No decisions require human approval.";
    return;
  }
  container.className = "approval-list";
  items.forEach((item) => {
    const card = element("article", "approval-card");
    const top = element("div", "approval-top");
    const copy = element("div");
    copy.append(element("h3", "", item.task || item.run_id));
    copy.append(element("p", "", `${item.run_id} · Risk ${item.risk || "unknown"} · ${item.role || "Agent"}`));
    top.append(copy);
    top.append(element("span", `status-mini ${item.status}`, item.status));
    card.append(top);
    const actions = element("div", "approval-actions");
    const approve = element("button", "button primary", "Approve");
    approve.type = "button";
    approve.disabled = !state.bootstrap.actions_enabled;
    approve.addEventListener("click", () => openActionDialog("approve", item.run_id));
    const reject = element("button", "button secondary", "Reject");
    reject.type = "button";
    reject.disabled = !state.bootstrap.actions_enabled;
    reject.addEventListener("click", () => openActionDialog("reject", item.run_id));
    actions.append(approve, reject);
    card.append(actions);
    container.append(card);
  });
}

function renderArtifacts(items) {
  const container = byId("artifact-list");
  clear(container);
  if (!items.length) {
    container.className = "artifact-list empty-state";
    container.textContent = "No artifacts generated yet.";
    return;
  }
  container.className = "artifact-list";
  items.forEach((item) => {
    const row = element("div", "artifact-item");
    const info = element("div");
    info.append(element("strong", "", item.name));
    info.append(element("span", "", `${item.path} · ${formatNumber(item.size_bytes)} bytes`));
    row.append(info, element("span", "", "Open"));
    row.addEventListener("click", () => previewArtifact(item));
    container.append(row);
  });
}

async function previewArtifact(item) {
  try {
    const result = await api(`/api/v1/artifacts/content/${encodeURIComponent(item.id)}`);
    text("artifact-preview-title", result.name);
    byId("artifact-preview").textContent = typeof result.content === "string"
      ? result.content
      : JSON.stringify(result.content, null, 2);
  } catch (error) {
    banner(error.message, "bad");
  }
}

function renderLanguages(languages) {
  const container = byId("language-bars");
  clear(container);
  const entries = Object.entries(languages).sort((a, b) => b[1] - a[1]);
  if (!entries.length) {
    container.append(element("div", "empty-state", "No indexed source languages."));
    return;
  }
  const max = Math.max(...entries.map(([, value]) => Number(value)));
  entries.forEach(([name, value]) => {
    const row = element("div", "bar-row");
    row.append(element("span", "", name));
    const track = element("div", "bar-track");
    const fill = element("div", "bar-fill");
    fill.style.width = `${Math.max(4, (Number(value) / max) * 100)}%`;
    track.append(fill);
    row.append(track, element("span", "", value));
    container.append(row);
  });
}

function renderImpact(result) {
  const container = byId("impact-result");
  clear(container);
  container.className = "result-box";
  const grid = element("div", "result-grid");
  [["Risk", result.risk_level], ["Files", (result.impacted_files || []).length], ["Tests", (result.impacted_tests || []).length], ["Features", (result.impacted_features || []).length]].forEach(([label, value]) => {
    const card = element("div", "result-stat");
    card.append(element("span", "", label), element("strong", "", value));
    grid.append(card);
  });
  container.append(grid);
  const reasons = (result.reasons || []).slice(0, 6);
  reasons.forEach((reason) => container.append(element("p", "muted", reason.reason || JSON.stringify(reason))));
}

function renderContext(result) {
  const container = byId("context-result");
  clear(container);
  container.className = "result-box";
  const grid = element("div", "result-grid");
  [["Pack", result.context_pack_id], ["Task type", result.task_type], ["Files", (result.files || []).length], ["Tokens", `${result.estimated_tokens}/${result.token_budget}`], ["Tests", (result.tests || []).length], ["Precision", Number(result.context_precision_score || 0).toFixed(4)]].forEach(([label, value]) => {
    const card = element("div", "result-stat");
    card.append(element("span", "", label), element("strong", "", value));
    grid.append(card);
  });
  container.append(grid);
}

function openActionDialog(action, runId = "") {
  const dialog = byId("action-dialog");
  text("dialog-title", action === "approve" ? "Approve patch" : action === "reject" ? "Reject patch" : action === "rollback" ? "Rollback transaction" : action === "apply" ? "Apply approved patch" : "Run verification");
  text("dialog-copy", action === "verify" ? "Basalt will run the complete configured proof process." : `This action will be recorded against ${runId}.`);
  byId("dialog-run-id").value = runId;
  byId("dialog-action").value = action;
  byId("dialog-actor-label").classList.toggle("hidden", ["verify", "apply"].includes(action));
  byId("dialog-reason-label").classList.toggle("hidden", ["verify", "apply"].includes(action));
  byId("dialog-token-label").classList.toggle("hidden", action !== "apply");
  byId("dialog-actor").value = "";
  byId("dialog-reason").value = "";
  byId("dialog-approval-token").value = "";
  dialog.showModal();
}

async function submitAction(event) {
  event.preventDefault();
  const action = byId("dialog-action").value;
  const runId = byId("dialog-run-id").value;
  const actor = byId("dialog-actor").value.trim();
  const reason = byId("dialog-reason").value.trim();
  const approvalToken = byId("dialog-approval-token").value.trim();
  let path = "/api/v1/verify";
  let body = { sandbox: "auto" };
  if (action !== "verify") {
    path = `/api/v1/runs/${encodeURIComponent(runId)}/${action}`;
    body = action === "apply" ? { approval_token: approvalToken, sandbox: "auto" } : { actor, reason };
  }
  try {
    byId("dialog-submit").disabled = true;
    const result = await api(path, { method: "POST", body: JSON.stringify(body), action: true });
    byId("action-dialog").close();
    if (result.approval_token) {
      await navigator.clipboard?.writeText(result.approval_token).catch(() => undefined);
      banner("Approved. The one-time apply token was copied to your clipboard.");
    } else {
      banner(`${action} completed successfully.`);
    }
    await loadAll();
  } catch (error) {
    banner(error.message, "bad");
  } finally {
    byId("dialog-submit").disabled = false;
  }
}

async function loadAll() {
  try {
    const [overview, proof] = await Promise.all([api("/api/v1/overview"), api("/api/v1/proof")]);
    renderOverview(overview);
    renderProof(proof || {});
  } catch (error) {
    banner(error.message, "bad");
  }
}

async function initialize() {
  try {
    state.bootstrap = await api("/api/v1/bootstrap");
    byId("verify-button").disabled = !state.bootstrap.actions_enabled;
    byId("mode-dot").classList.toggle("enabled", state.bootstrap.actions_enabled);
    text("mode-label", state.bootstrap.actions_enabled ? "Actions enabled" : "Read-only");
    await loadAll();
  } catch (error) {
    banner(error.message, "bad");
  }
}

document.querySelectorAll(".nav-item").forEach((node) => node.addEventListener("click", (event) => {
  event.preventDefault();
  switchView(node.dataset.section);
}));
document.querySelectorAll("[data-jump]").forEach((node) => node.addEventListener("click", () => switchView(node.dataset.jump)));
byId("refresh-button").addEventListener("click", loadAll);
byId("verify-button").addEventListener("click", () => openActionDialog("verify"));
byId("close-run-detail").addEventListener("click", () => byId("run-detail-panel").classList.add("hidden"));
byId("action-form").addEventListener("submit", submitAction);
byId("impact-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/v1/impact", { method: "POST", body: JSON.stringify({ target: byId("impact-target").value, depth: Number(byId("impact-depth").value) }) });
    renderImpact(result);
  } catch (error) { banner(error.message, "bad"); }
});
byId("context-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const targets = byId("context-targets").value.split(",").map((item) => item.trim()).filter(Boolean);
    const result = await api("/api/v1/context", { method: "POST", body: JSON.stringify({ task: byId("context-task").value, role: byId("context-role").value, targets, budget: Number(byId("context-budget").value) }) });
    renderContext(result);
  } catch (error) { banner(error.message, "bad"); }
});

const initialSection = window.location.hash.slice(1);
if (["overview", "proof", "graph", "transactions", "approvals", "evidence"].includes(initialSection)) switchView(initialSection);
initialize();
