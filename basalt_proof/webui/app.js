"use strict";

const state = {
  overview: null,
  proof: null,
  bootstrap: { actions_enabled: false, action_token: "" },
  factory: null,
  beta: null,
  architecture: null,
  preview: null,
  operations: null,
  selectedFactoryRun: null,
  selectedTransaction: null,
  artifactPreview: { item: null, offset: 0, visible: "", nextOffset: null },
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
  text("status-live", message);
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

  text("checks-metric", `${data.proof.checks.passed}/${data.proof.checks.applicable ?? data.proof.checks.total} applicable`);
  text("checks-sub", `${data.proof.checks.failed} failed · ${data.proof.checks.skipped} not applicable`);
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
  text("factory-total", data.factory?.total || 0);
  text("factory-verified", data.factory?.verified || 0);
  text("factory-blocked", data.factory?.blocked || 0);
  text("factory-rolled-back", data.factory?.rolled_back || 0);
  text("factory-run-count", `${data.factory?.total || 0} runs`);

  renderRoadmap(data.roadmap || []);
  const recent = byId("recent-runs");
  clear(recent);
  if (!data.transactions.recent.length) {
    recent.className = "activity-list empty-state";
    recent.textContent = "No governed transactions yet.";
  } else {
    recent.className = "activity-list";
    data.transactions.recent.slice(0, 5).forEach((item) => recent.append(runRow(item, true)));
  }
  renderRuns(data.transactions.recent || []);
  renderApprovals(data.approvals.items || []);
  renderArtifacts(data.artifacts.items || []);
  renderLanguages(data.graph.languages || {});
  renderFactoryRuns(data.factory?.recent || []);
  const agentTransactions = (data.transactions?.recent || []).filter((item) => (item.kind || "agent") === "agent");
  if (!state.selectedFactoryRun && agentTransactions.length) renderStandaloneAgentTimeline(agentTransactions);
}

function renderStandaloneAgentTimeline(items) {
  const container = byId("agent-execution-list");
  clear(container);
  container.className = "stack-list";
  items.slice(0, 12).forEach((item) => {
    const card = element("button", "stack-item");
    card.type = "button";
    card.append(element("strong", "", `${item.role || item.agent_role || "Agent"} · ${item.status || "UNKNOWN"}`));
    card.append(element("p", "", `${item.task || item.run_id} · ${item.patch_file_count || 0} patch files · ${item.changed_lines || 0} changed lines`));
    card.addEventListener("click", () => showTransaction(item));
    container.append(card);
  });
}

function renderFactoryRuns(runs) {
  const body = byId("factory-runs-table");
  if (!body) return;
  clear(body);
  if (!runs.length) {
    const row = document.createElement("tr");
    const cell = element("td", "empty-state", "No factory runs recorded.");
    cell.colSpan = 5;
    row.append(cell);
    body.append(row);
    return;
  }
  runs.forEach((item) => {
    const row = document.createElement("tr");
    row.append(element("td", "", item.product_name || item.run_id));
    const statusCell = document.createElement("td");
    statusCell.append(element("span", `status-mini ${item.status || ""}`, item.status || "UNKNOWN"));
    row.append(statusCell);
    row.append(element("td", "", item.proof_status ? `${item.proof_status} ${item.proof_score || 0}/100` : "Not run"));
    row.append(element("td", "", formatDate(item.updated_at)));
    const actionCell = document.createElement("td");
    const inspect = element("button", "text-button", "Inspect");
    inspect.type = "button";
    inspect.addEventListener("click", () => showFactoryRun(item.run_id));
    actionCell.append(inspect);
    row.append(actionCell);
    body.append(row);
  });
}

function renderFactoryState(data) {
  state.factory = data;
  text("factory-state-version", `state ${data.current_state?.version ?? 0}`);
  const inventory = byId("model-inventory");
  clear(inventory);
  const profiles = data.models || [];
  if (!profiles.length) {
    inventory.className = "stack-list empty-state";
    inventory.textContent = "No execution profiles loaded.";
  } else {
    inventory.className = "stack-list";
    profiles.forEach((item) => {
      const deterministic = String(item.provider || "").toLowerCase() === "local" || String(item.model || "").startsWith("basalt-");
      const card = element("div", "stack-item");
      card.append(element("strong", "", `${deterministic ? "Deterministic engine" : "Model provider"} · ${item.provider}/${item.model}`));
      card.append(element("p", "", `${item.available ? "Available" : "Not configured"} · privacy ${(item.privacy_modes || []).join(", ") || "unknown"} · capabilities ${(item.capabilities || []).join(", ") || "none"}`));
      inventory.append(card);
    });
  }
}


function renderFactoryDetail(run) {
  state.selectedFactoryRun = run;
  text("factory-detail-title", `${run.product_name} · ${run.run_id}`);
  const container = byId("factory-detail");
  clear(container);
  const rolledBack = run.status === "ROLLED_BACK" || run.rollback?.performed;
  const proofLabel = run.proof_status
    ? `${rolledBack ? "Historical proof" : "Proof"} · ${run.proof_status} ${run.proof_score}/100`
    : "Not run";
  const targetStatus = rolledBack
    ? `INACTIVE · quarantined${run.rollback?.quarantine_path ? ` at ${run.rollback.quarantine_path}` : ""}`
    : (run.target_path || "Not assembled");
  const entries = [
    ["Run state", run.status], ["Template", run.template], ["Base state", run.base_state_version],
    ["Committed state", run.committed_state_version || "—"], ["Current Factory state", run.current_factory_state ? `${run.current_factory_state.version} · ${shortHash(run.current_factory_state.state_hash)}` : "—"],
    ["Tasks", (run.tasks || []).length], ["Epochs", (run.epochs || []).length], ["Proof result", proofLabel],
    ["Output state", shortHash(run.project_state_hash)], ["Target", targetStatus],
    ["Execution mode", run.execution_truth?.mode || "DETERMINISTIC_LOCAL"], ["Message", run.message],
  ];
  if (rolledBack) {
    entries.push(["Restored state", shortHash(run.rollback?.restored_state_hash || run.rollback?.record?.restored_state_hash)]);
    entries.push(["Rollback transaction", run.rollback?.record?.rollback_transaction_run_id || run.rollback?.record?.rollback_run_id || "Recorded in transaction ledger"]);
    entries.push(["Rolled back by", run.rollback?.record?.actor || "—"]);
    entries.push(["Rollback reason", run.rollback?.record?.reason || "—"]);
  }
  if (run.control_plane?.project_id) {
    entries.push(["Control Plane project", run.control_plane.project_id]);
    entries.push(["Deployment", run.control_plane.deployment_id ? `${run.control_plane.deployment_environment} · ${run.control_plane.deployment_status}` : "Not packaged"]);
  }
  entries.forEach(([label, value]) => {
    const card = element("div", "detail-card");
    card.append(element("span", "", label), element("strong", "", value));
    container.append(card);
  });
  const actions = byId("factory-detail-actions");
  clear(actions);
  if (run.status === "PLANNED") {
    const scope = element("div", "scope-disclosure");
    scope.append(element("strong", "", "Build scope"), element("span", "", "A verified product will be assembled outside the Basalt source repository. No deployment or remote model execution occurs automatically."));
    actions.append(scope);
    const build = element("button", "button primary", "Build and prove");
    build.type = "button";
    build.disabled = !state.bootstrap.actions_enabled;
    build.addEventListener("click", () => buildFactoryRun(run.run_id));
    actions.append(build);
  }
  if (run.status === "VERIFIED" && !run.control_plane?.project_id) {
    const register = element("button", "button primary", "Register in Control Plane");
    register.type = "button"; register.disabled = !state.bootstrap.actions_enabled;
    register.addEventListener("click", () => registerFactoryRun(run.run_id));
    actions.append(register);
  }
  if (run.status === "VERIFIED" && run.control_plane?.project_id && !run.control_plane?.deployment_id) {
    const packageButton = element("button", "button primary", "Package for staging approval");
    packageButton.type = "button"; packageButton.disabled = !state.bootstrap.actions_enabled;
    packageButton.addEventListener("click", () => packageFactoryRun(run.run_id));
    actions.append(packageButton);
  }
  if (run.rollback?.eligible || run.status === "VERIFIED") {
    const rollback = element("button", "button secondary", "Rollback factory output");
    rollback.type = "button";
    rollback.disabled = !state.bootstrap.actions_enabled;
    rollback.addEventListener("click", () => openActionDialog("factory-rollback", run.run_id));
    actions.append(rollback);
  }
  if (run.execution_truth?.claim) actions.append(element("p", "muted", run.execution_truth.claim));
  byId("factory-detail-panel").classList.remove("hidden");
  renderPlan(run);
  renderAgentRecords(run.agent_records || [], run);
}


function renderPlan(run) {
  const bannerNode = byId("plan-run-state");
  if (!run || !(run.tasks || []).length) {
    bannerNode.className = "state-banner";
    bannerNode.textContent = "No governed plan selected. Create or inspect a Factory run to view dependency-safe work.";
  } else if (run.status === "ROLLED_BACK") {
    bannerNode.className = "state-banner warning";
    bannerNode.textContent = `Run ROLLED_BACK · historical materialization retained · active output quarantined · restored state ${shortHash(run.rollback?.restored_state_hash || run.rollback?.record?.restored_state_hash)}`;
  } else {
    bannerNode.className = "state-banner";
    bannerNode.textContent = `Run ${run.status} · ${(run.tasks || []).length} tasks · ${(run.epochs || []).length} dependency-safe epochs · output ${run.target_path || "not assembled"}`;
  }
  const assignments = new Map((run.model_assignments || []).map((item) => [item.task_id, item]));
  const epochGrid = byId("epoch-grid");
  clear(epochGrid);
  (run.epochs || []).forEach((epoch) => {
    const card = element("article", "epoch-card");
    card.append(element("span", "", `EPOCH ${epoch.number}`));
    card.append(element("h3", "", epoch.name));
    card.append(element("p", "", epoch.purpose));
    card.append(element("strong", "", `${(epoch.task_ids || []).length} tasks · ${epoch.status}`));
    epochGrid.append(card);
  });
  const body = byId("factory-task-table");
  clear(body);
  if (!(run.tasks || []).length) {
    const row = document.createElement("tr"); const cell = element("td", "empty-state", "No tasks planned for the selected run."); cell.colSpan = 7; row.append(cell); body.append(row); return;
  }
  (run.tasks || []).forEach((task) => {
    const assignment = assignments.get(task.task_id) || {};
    const route = `${assignment.provider || "local"}/${assignment.model || task.agent_role}`;
    const row = document.createElement("tr");
    row.append(element("td", "", `${task.task_id} · ${task.title}`));
    row.append(element("td", "", `${task.epoch} · ${task.epoch_name}`));
    row.append(element("td", "", `${route} · ${assignment.privacy_mode || "local"}`));
    row.append(element("td", "", (task.dependencies || []).join(", ") || "None"));
    row.append(element("td", "", task.expected_artifact || (task.required_locks || []).join(", ") || "Defined by task contract"));
    row.append(element("td", "", task.risk_level));
    const statusCell = document.createElement("td");
    const historical = run.status === "ROLLED_BACK" ? " · HISTORICAL" : "";
    statusCell.append(element("span", `status-mini ${task.status || ""}`, `${task.status || "PLANNED"}${historical}`));
    row.append(statusCell);
    body.append(row);
  });
}


function renderAgentRecords(records, run = state.selectedFactoryRun || {}) {
  const container = byId("agent-execution-list");
  clear(container);
  const assignments = new Map((run.model_assignments || []).map((item) => [item.task_id, item]));
  if (!records.length && (run.tasks || []).length) {
    container.className = "stack-list";
    (run.tasks || []).forEach((task) => {
      const assignment = assignments.get(task.task_id) || {};
      const card = element("details", "stack-item evidence-detail");
      card.append(element("summary", "", `${task.task_id} · ${task.agent_role} · PLANNED`));
      card.append(element("p", "", `Route ${assignment.provider || "local"}/${assignment.model || "deterministic contract"} · privacy ${assignment.privacy_mode || "local"} · epoch ${task.epoch} · depends on ${(task.dependencies || []).join(", ") || "none"}`));
      card.append(element("p", "muted", `Capabilities: ${task.description} · expected output ${task.expected_artifact || "task contract artifact"} · review ${assignment.review_model || "deterministic proof route"}`));
      container.append(card);
    });
    return;
  }
  if (!records.length) {
    container.className = "stack-list empty-state";
    container.textContent = "No Factory plan is selected.";
    return;
  }
  container.className = "stack-list";
  records.forEach((item) => {
    const card = element("details", "stack-item evidence-detail");
    const historical = run.status === "ROLLED_BACK" ? " · HISTORICAL" : "";
    card.append(element("summary", "", `${item.task_id} · ${item.agent_role} · ${item.status}${historical}`));
    const assignment = item.model_assignment || {};
    const duration = item.started_at && item.finished_at ? `${Math.max(0, new Date(item.finished_at) - new Date(item.started_at))} ms` : "unknown";
    const grid = element("div", "detail-grid compact-detail");
    [
      ["Execution", item.execution_mode || "DETERMINISTIC_LOCAL"], ["Route", `${assignment.provider || "local"}/${assignment.model || "deterministic contract"}`],
      ["Privacy", assignment.privacy_mode || "local"], ["Started", formatDate(item.started_at)], ["Finished", formatDate(item.finished_at)],
      ["Duration", duration], ["Dependencies", (item.dependency_ids || []).join(", ") || "None"],
      ["Artifacts", (item.artifacts || []).join(", ") || "None"], ["Proof", run.proof_status ? `${run.proof_status} ${run.proof_score}/100` : "Pending"],
      ["Output state", shortHash(run.project_state_hash)],
    ].forEach(([label, value]) => { const cell = element("div", "detail-card"); cell.append(element("span", "", label), element("strong", "", value)); grid.append(cell); });
    card.append(grid, element("p", "muted", item.summary));
    container.append(card);
  });
}


async function showFactoryRun(runId) {
  try {
    const run = await api(`/api/v1/factory/runs/${encodeURIComponent(runId)}`);
    renderFactoryDetail(run);
    switchView("factory");
  } catch (error) { banner(error.message, "bad"); }
}

async function buildFactoryRun(runId) {
  try {
    const result = await api(`/api/v1/factory/runs/${encodeURIComponent(runId)}/build`, { method: "POST", body: JSON.stringify({ sandbox: "temp" }), action: true });
    banner(result.status === "VERIFIED" ? "Factory product verified and assembled." : `Factory returned ${result.status}.`, result.status === "VERIFIED" ? "good" : "bad");
    await loadAll();
    renderFactoryDetail(result);
  } catch (error) { banner(error.message, "bad"); }
}

async function registerFactoryRun(runId) {
  try {
    const result = await api(`/api/v1/factory/runs/${encodeURIComponent(runId)}/register`, { method: "POST", action: true, body: JSON.stringify({ actor: "Local user" }) });
    banner(`Registered Control Plane project ${result.project_id}.`);
    await loadAll();
    renderFactoryDetail(await api(`/api/v1/factory/runs/${encodeURIComponent(runId)}`));
  } catch (error) { banner(error.message, "bad"); }
}

async function packageFactoryRun(runId) {
  try {
    const result = await api(`/api/v1/factory/runs/${encodeURIComponent(runId)}/package`, { method: "POST", action: true, body: JSON.stringify({ actor: "Local user", environment: "staging" }) });
    banner(`Staging package created · ${result.deployment.status}. Human approval is now required.`);
    await loadAll();
    renderFactoryDetail(await api(`/api/v1/factory/runs/${encodeURIComponent(runId)}`));
    switchView("approvals");
  } catch (error) { banner(error.message, "bad"); }
}

async function rollbackFactoryRun(runId, actor, reason) {
  const result = await api(`/api/v1/factory/runs/${encodeURIComponent(runId)}/rollback`, {
    method: "POST",
    action: true,
    body: JSON.stringify({ actor, reason }),
  });
  banner("Factory output quarantined and rollback state committed.");
  await loadAll();
  const refreshed = await api(`/api/v1/factory/runs/${encodeURIComponent(runId)}`);
  renderFactoryDetail(refreshed);
  return result;
}

function renderProof(report) {
  state.proof = report;
  const checks = report.checks || [];
  const findings = report.security_findings || [];
  const mutations = report.mutations || [];
  const normalized = (value) => String(value || "UNKNOWN").toUpperCase();
  text("proof-passed", checks.filter((item) => normalized(item.status) === "PASS").length);
  text("proof-failed", checks.filter((item) => normalized(item.status) === "FAIL").length);
  text("proof-survived", mutations.filter((item) => item.survived === true).length);
  text("proof-high", findings.filter((item) => String(item.level).toUpperCase() === "HIGH").length);
  text("proof-sandbox", `Sandbox ${report.sandbox || "unknown"}`);
  text("proof-finished", report.finished_at ? `Finished ${formatDate(report.finished_at)}` : "No verification yet");

  const breakdown = byId("proof-breakdown");
  clear(breakdown);
  const scoreItems = report.score_breakdown || [];
  if (!scoreItems.length) {
    breakdown.className = "stack-list empty-state";
    breakdown.textContent = "No score breakdown loaded.";
  } else {
    breakdown.className = "stack-list";
    scoreItems.forEach((item) => {
      const card = element("div", "stack-item");
      const delta = item.points ?? item.score ?? item.delta ?? 0;
      const label = item.label || item.name || item.category || item.rule || "Proof component";
      card.append(element("strong", "", `${label} · ${delta >= 0 ? "+" : ""}${delta}`));
      card.append(element("p", "", item.reason || item.message || item.status || "Deterministic proof-score component."));
      breakdown.append(card);
    });
  }

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
      const status = normalized(item.status);
      const displayStatus = ["SKIP", "SKIPPED", "NOT_APPLICABLE"].includes(status) ? "NOT_APPLICABLE" : status;
      row.append(element("td", "", item.name));
      const statusCell = document.createElement("td");
      statusCell.append(element("span", `status-mini ${displayStatus}`, displayStatus));
      row.append(statusCell);
      row.append(element("td", "", item.sandbox || "—"));
      row.append(element("td", "", `${item.duration_ms || 0} ms`));
      row.append(element("td", "", item.message || (displayStatus === "NOT_APPLICABLE" ? "No command configured; not included in applicable checks." : "—")));
      body.append(row);
    });
  }
  const actionableFindings = findings.filter((item) => String(item.level).toUpperCase() !== "LOW" || !/\.(md|markdown)$/i.test(String(item.file || "")));
  const lowDocumentation = findings.filter((item) => String(item.level).toUpperCase() === "LOW" && /\.(md|markdown)$/i.test(String(item.file || "")));
  renderStack("findings-list", actionableFindings, (item) => ({
    title: `${String(item.level).toUpperCase()} · ${item.rule}`,
    copy: `${item.file}:${item.line} — ${item.message}`,
  }), lowDocumentation.length ? `${lowDocumentation.length} low-severity documentation style findings are grouped below.` : "No security, policy, dependency or quality findings.");
  if (lowDocumentation.length) {
    const root = byId("findings-list");
    const details = element("details", "evidence-detail");
    details.append(element("summary", "", `Low documentation findings · ${lowDocumentation.length}`));
    const list = element("ul", "evidence-list");
    lowDocumentation.slice(0, 100).forEach((item) => list.append(element("li", "", `${item.file}:${item.line} — ${item.message}`)));
    details.append(list); root.append(details);
  }
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
    cell.colSpan = 7;
    row.append(cell);
    body.append(row);
    return;
  }
  runs.forEach((item) => {
    const row = document.createElement("tr");
    row.append(element("td", "", item.kind === "factory" ? "Factory" : "Agent"));
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
    button.addEventListener("click", () => showTransaction(item));
    actionCell.append(button);
    row.append(actionCell);
    body.append(row);
  });
}

function appendTransactionEntries(container, entries) {
  entries.forEach(([label, value]) => {
    const card = element("div", "detail-card");
    card.append(element("span", "", label));
    card.append(element("strong", "", value === 0 ? "0" : (value || "—")));
    container.append(card);
  });
}

async function showTransaction(item) {
  try {
    state.selectedTransaction = { kind: item.kind || "agent", run_id: item.run_id };
    const container = byId("run-detail");
    clear(container);
    if (item.kind === "factory") {
      const run = await api(`/api/v1/factory/runs/${encodeURIComponent(item.run_id)}`);
      text("run-detail-title", `${run.product_name || "Factory"} · state transaction`);
      appendTransactionEntries(container, [
        ["Type", "Factory state transaction"], ["Transaction state", run.transaction_state || item.ledger_status || item.status], ["Factory run state", run.status], ["Proof result", run.proof_status ? `${run.proof_status} ${run.proof_score}/100` : "Not run"],
        ["Product", run.product_name], ["Run ID", run.run_id], ["Base state version", run.base_state_version], ["Committed state version", run.committed_state_version || "—"],
        ["Current Factory state", run.current_factory_state ? `${run.current_factory_state.version} · ${shortHash(run.current_factory_state.state_hash)}` : "—"],
        ["Output state hash", shortHash(run.project_state_hash)], ["Tasks", (run.tasks || []).length], ["Epochs", (run.epochs || []).length],
        ["Target", run.rollback?.performed ? "Inactive · quarantined" : run.target_path], ["Execution truth", run.execution_truth?.mode || "DETERMINISTIC_LOCAL"],
        ["Updated", formatDate(run.updated_at)], ["Rollback", run.rollback?.performed ? "Performed" : (run.rollback?.eligible ? "Eligible" : "No eligible transaction")],
      ]);
      if (run.rollback?.record) {
        const record = run.rollback.record;
        appendTransactionEntries(container, [
          ["Rolled back by", record.actor], ["Rollback reason", record.reason], ["Restored hash", shortHash(record.restored_state_hash)],
          ["Quarantine", record.quarantine_path], ["Rollback state version", record.rollback_state_version],
        ]);
      }
      if ((run.evidence || []).length) appendTransactionEntries(container, [["Evidence", `${run.evidence.length} Factory artifacts · hash tracked`]]);
      const actions = element("div", "approval-actions");
      if (run.rollback?.eligible) {
        const rollback = element("button", "button secondary", "Rollback factory output");
        rollback.type = "button"; rollback.disabled = !state.bootstrap.actions_enabled;
        rollback.addEventListener("click", () => openActionDialog("factory-rollback", run.run_id)); actions.append(rollback);
      }
      if (actions.childElementCount) container.append(actions);
    } else {
      const run = await api(`/api/v1/runs/${encodeURIComponent(item.run_id)}`);
      text("run-detail-title", run.run_id);
      const patch = run.patch_scope || {}; const impact = run.impact_radius || {}; const decision = run.decision_context || {}; const approval = decision.approval || {}; const provenance = run.transaction_provenance || {};
      appendTransactionEntries(container, [
        ["Type", "Agent patch transaction"], ["Transaction state", run.status], ["Task", run.task], ["Proposer", run.agent_role], ["Run ID", run.run_id],
        ["Base state", shortHash(run.base_state_hash)], ["Current state", shortHash(run.current_state_hash)], ["Patch files", patch.files_changed ?? (patch.files || []).length],
        ["Changed lines", patch.changed_lines || 0], ["Additions / deletions", `+${patch.additions || 0} / −${patch.deletions || 0}`], ["Impact files", (impact.files || []).length],
        ["Impact tests", (impact.tests || []).length], ["Impact features", (impact.features || []).length], ["Policy verdict", decision.policy_verdict], ["Risk", decision.risk],
        ["Required approvals", (decision.required_approvals || []).join(", ") || "None"], ["Approved by", approval.actor || "—"], ["Approval reason", approval.reason || "—"],
        ["Proof result", provenance.proof_status ? `${provenance.proof_status} ${provenance.proof_score}/100` : "Not committed"],
        ["Rollback", run.rollback?.performed ? `Performed · ${shortHash(run.rollback.restored_hash)}` : (run.rollback?.eligible ? "Eligible" : "No eligible transaction")],
        ["Message", run.message], ["Created", formatDate(run.created_at)], ["Updated", formatDate(run.updated_at)],
      ]);
      if (run.patch_preview) { const details = element("details", "evidence-detail"); details.open = true; details.append(element("summary", "", `Proposed patch · ${(patch.files || []).join(", ") || "diff"}`), element("pre", "transaction-diff", run.patch_preview)); container.append(details); }
    }
    byId("run-detail-panel").classList.remove("hidden"); switchView("transactions");
  } catch (error) { banner(error.message, "bad"); }
}


async function hydrateAgentApprovalCard(card, item) {
  try {
    const run = await api(`/api/v1/runs/${encodeURIComponent(item.run_id)}`);
    const decision = run.decision_context || {};
    const patch = run.patch_scope || {};
    const detail = element("details", "approval-evidence");
    detail.open = String(decision.risk || item.risk).toUpperCase() === "HIGH";
    detail.append(element("summary", "", "Decision evidence"));
    const grid = element("div", "detail-grid compact-detail");
    [
      ["Patch files", (patch.files || []).join(", ") || "None"], ["Changed lines", patch.changed_lines || 0],
      ["Base hash", shortHash(decision.base_state_hash)], ["Policy", decision.policy_verdict || "UNKNOWN"],
      ["Required approvals", (decision.required_approvals || []).join(", ") || "None"],
      ["Proof context", decision.proof_before ? "Before-proof evidence linked" : "Not available"],
    ].forEach(([label, value]) => {
      const cell = element("div", "detail-card"); cell.append(element("span", "", label), element("strong", "", value)); grid.append(cell);
    });
    detail.append(grid);
    (decision.policy_reasons || []).forEach((reason) => detail.append(element("p", "muted", reason)));
    if (run.patch_preview) detail.append(element("pre", "transaction-diff", run.patch_preview));
    card.insertBefore(detail, card.lastElementChild);
  } catch (error) {
    card.append(element("p", "muted", `Decision evidence unavailable: ${error.message}`));
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
    const isDeployment = item.kind === "deployment";

    copy.append(element("h3", "", item.task || item.run_id));

    if (isDeployment) {
      const environment = String(item.environment || "deployment").toUpperCase();
      const proof = `${item.proof_status || "UNKNOWN"} ${item.proof_score || 0}/100`;
      const checksum = item.artifact_sha256
        ? shortHash(item.artifact_sha256)
        : "not recorded";
      const linkedJob = (item.metadata || {}).job_id || "not linked";

      copy.append(element(
        "p",
        "",
        `${item.deployment_id} · ${environment} · ${item.project_id || "Unknown project"}`
      ));
      copy.append(element(
        "p",
        "",
        `Proof ${proof} · SHA ${checksum} · Job ${linkedJob}`
      ));
    } else {
      copy.append(element(
        "p", "",
        `${item.run_id} · Risk ${item.risk || "unknown"} · ${item.role || item.agent_role || "Agent"}`
      ));
      copy.append(element(
        "p", "",
        `${item.patch_file_count || 0} patch files · ${item.changed_lines || 0} changed lines · base ${shortHash(item.base_state_hash)}`
      ));
    }

    top.append(copy);
    top.append(element("span", `status-mini ${item.status}`, item.status));
    card.append(top);

    const actions = element("div", "approval-actions");

    if (isDeployment) {
      if (item.status === "AWAITING_APPROVAL") {
        const approve = element("button", "button primary", "Approve deployment");
        approve.type = "button";
        approve.disabled = !state.bootstrap.actions_enabled;
        approve.addEventListener(
          "click",
          () => openActionDialog("deployment-approve", item.deployment_id)
        );
        actions.append(approve);
      } else if (item.status === "APPROVED") {
        const promote = element("button", "button primary", "Promote deployment");
        promote.type = "button";
        promote.disabled = !state.bootstrap.actions_enabled;
        promote.addEventListener(
          "click",
          () => openActionDialog("deployment-promote", item.deployment_id)
        );
        actions.append(promote);
      }
    } else {
      const approve = element("button", "button primary", "Approve");
      approve.type = "button";
      approve.disabled = !state.bootstrap.actions_enabled;
      approve.addEventListener(
        "click",
        () => openActionDialog("approve", item.run_id)
      );

      const reject = element("button", "button secondary", "Reject");
      reject.type = "button";
      reject.disabled = !state.bootstrap.actions_enabled;
      reject.addEventListener(
        "click",
        () => openActionDialog("reject", item.run_id)
      );

      actions.append(approve, reject);
    }

    if (actions.childElementCount) card.append(actions);
    container.append(card);
    if (!isDeployment) hydrateAgentApprovalCard(card, item);
  });
}

function renderBeta(data) {
  state.beta = data;
  const workspace = data?.workspace || {}; const jobs = data?.jobs || {}; const providers = data?.providers || {}; const deployments = data?.deployments || {};
  const projects = workspace.projects || []; const teams = workspace.teams || []; const activity = workspace.activity || []; const jobItems = jobs.jobs || []; const providerItems = providers.providers || []; const deploymentItems = deployments.deployments || [];
  text("beta-project-count", projects.length); text("beta-job-count", jobItems.length); text("beta-provider-count", providers.configured || 0); text("beta-deployment-count", deploymentItems.length);
  const stack = (id, items, mapItem, emptyText) => { const container = byId(id); clear(container); if (!items.length) { container.className = "stack-list empty-state"; container.textContent = emptyText; return; } container.className = "stack-list"; items.slice(0, 20).forEach((item) => { const mapped = mapItem(item); const card = element("div", "stack-item"); card.append(element("strong", "", mapped.title), element("p", "", mapped.detail)); if (mapped.action) card.append(mapped.action); container.append(card); }); };
  const orgItems = teams.map((item) => ({ ...item, activity: activity.find((event) => event.team_id === item.team_id) }));
  stack("beta-organizations", orgItems, (item) => ({ title: `${item.name || item.team_id} · ${item.status || "ACTIVE"}`, detail: `${item.slug || "local-team"} · owner ${item.created_by || "unknown"}${item.activity ? ` · latest ${item.activity.action}` : ""}` }), `No local organizations registered. ${workspace.counts?.users || 0} users · ${workspace.counts?.memberships || 0} memberships.`);
  stack("beta-runtime", data?.runtime?.workspaces || data?.runtime?.items || [], (item) => ({ title: item.job_id || item.workspace || "Isolated workspace", detail: `${item.status || "prepared"} · ${typeof item.profile === "object" ? (item.profile?.name || "local") : (item.profile || "local")}` }), "No active isolated workspaces. Jobs use lease-based local workers; managed remote workers are not claimed.");
  stack("beta-projects", projects, (item) => ({ title: item.name || item.project_id, detail: `${item.project_id} · ${item.template || "project"} · ${item.privacy_mode || "local"} · ${item.status || "ACTIVE"} · ${item.repo_path || ""}` }), "No persistent projects registered. Register a VERIFIED Factory output to continue into packaging and deployment approvals.");
  stack("beta-jobs", jobItems, (item) => ({ title: `${item.job_type || "JOB"} · ${item.status || "UNKNOWN"}`, detail: `${item.job_id || ""} · attempts ${item.attempts || 0}/${item.max_attempts || 0}` }), "No durable jobs submitted.");
  stack("beta-providers", providerItems, (item) => ({ title: item.display_name || item.provider_id, detail: `${item.model || "engine"} · ${item.configured ? "configured" : "not configured"} · ${item.kind || "provider"}` }), "No execution provider profiles loaded.");
  stack("beta-deployments", deploymentItems, (item) => ({ title: `${item.environment || "preview"} · ${item.status || "UNKNOWN"}`, detail: `${item.deployment_id || ""} · project ${item.project_id || "unknown"} · proof ${item.proof_status || "UNKNOWN"} ${item.proof_score || 0}/100 · SHA ${shortHash(item.artifact_sha256)}` }), "No deployment artifacts packaged. VERIFIED Factory outputs may be registered and packaged for explicit approval.");
}


function renderArchitecture(data) {
  state.architecture = data;
  const summary = data?.summary || {};
  text("architecture-files", summary.source_files || 0);
  text("architecture-modules", summary.modules || 0);
  text("architecture-routes", summary.routes || 0);
  text("architecture-schemas", summary.schemas || 0);
  text("architecture-freshness", data?.fresh ? `Fresh · ${shortHash(data.state_hash)}` : "Graph stale");
  const layers = byId("architecture-layers");
  clear(layers);
  (data?.layers || []).forEach((item) => {
    const card = element("article", "architecture-card");
    card.append(element("h3", "", `${item.name} · ${item.count}`));
    const list = element("ul");
    (item.files || []).slice(0, 8).forEach((file) => list.append(element("li", "", file)));
    card.append(list);
    layers.append(card);
  });
  const apiItems = [...(data?.api?.discovered || []).map((item) => ({ title: `${item.method} ${item.path}`, copy: "Source-discovered endpoint" })), ...(data?.api?.graph_routes || []).map((item) => ({ title: item, copy: "Knowledge-graph route signal" }))];
  renderStack("architecture-api", apiItems, (item) => item, "No API routes detected.");
  const db = data?.database || {};
  const dbItems = [
    { title: `Engine · ${db.engine || "Not detected"}`, copy: `${(db.files || []).length} persistence source files` },
    ...(db.tables || []).map((item) => ({ title: `Table · ${item}`, copy: "Source-discovered schema" })),
    ...(db.schema_signals || []).map((item) => ({ title: `Schema · ${item}`, copy: "Knowledge-graph schema signal" })),
  ];
  renderStack("architecture-database", dbItems, (item) => item, "No database schema detected.");
  const depRoot = byId("architecture-dependencies");
  clear(depRoot);
  const table = document.createElement("table");
  table.innerHTML = "<thead><tr><th>Source module</th><th>Target module</th><th>Signals</th></tr></thead>";
  const body = document.createElement("tbody");
  (data?.dependencies || []).slice(0, 80).forEach((item) => {
    const row = document.createElement("tr");
    row.append(element("td", "", item.source), element("td", "", item.target), element("td", "", item.signals));
    body.append(row);
  });
  if (!body.childElementCount) {
    const row = document.createElement("tr"); const cell = element("td", "empty-state", "No cross-module dependencies detected."); cell.colSpan = 3; row.append(cell); body.append(row);
  }
  table.append(body); depRoot.append(table);
}

function renderPreview(data) {
  state.preview = data;
  text("preview-status", data?.status || "STOPPED");
  text("preview-available", data?.available ? "Yes" : "No");
  text("preview-mode", data?.mode || "STATIC_SAME_ORIGIN");
  text("preview-root", data?.root || (data?.available ? "repository root" : "—"));
  const detail = byId("preview-detail");
  clear(detail);
  [["State", data?.status || "STOPPED"], ["Reason", data?.reason || "—"], ["Started", formatDate(data?.started_at)], ["Started by", data?.started_by || "—"], ["Server-side execution", "Disabled"], ["Protected paths", data?.security?.protected_paths ? "Enforced" : "Unknown"]].forEach(([label, value]) => {
    const card = element("div", "detail-card"); card.append(element("span", "", label), element("strong", "", value)); detail.append(card);
  });
  byId("preview-start").disabled = !state.bootstrap.actions_enabled || !data?.available || data?.status === "RUNNING";
  byId("preview-stop").disabled = !state.bootstrap.actions_enabled || data?.status !== "RUNNING";
  byId("preview-open").classList.toggle("hidden", data?.status !== "RUNNING");
}

function renderOperations(data) {
  state.operations = data;
  const metrics = data?.metrics || {};
  text("operations-status", `${data?.status || "UNKNOWN"} · local`); text("operations-incidents", metrics.incidents || 0); text("operations-high", metrics.high_incidents || 0); text("operations-approvals", metrics.pending_approvals || 0); text("operations-rollbacks", metrics.rollback_ready || 0);
  renderStack("operations-incident-list", data?.incidents || [], (item) => ({ title: `${item.severity} · ${item.code}`, copy: `${item.summary} · source ${item.source}` }), "No incidents detected from local proof, graph, queue, deployment, or preview state.");
  const recovery = byId("operations-recovery"); clear(recovery);
  Object.entries(data?.recovery || {}).forEach(([label, value]) => {
    let display = typeof value === "boolean" ? (value ? "Available" : "No eligible transaction") : value;
    if (label === "transaction_rollback" && value === false) display = "No eligible transaction";
    const card = element("div", "detail-card"); card.append(element("span", "", label.replaceAll("_", " ")), element("strong", "", display)); recovery.append(card);
  });
}


function renderArtifacts(items) {
  const container = byId("artifact-list"); clear(container);
  if (!items.length) { container.className = "artifact-list empty-state"; container.textContent = "No artifacts generated yet."; return; }
  container.className = "artifact-list"; const groups = new Map();
  items.forEach((item) => { const key = `${item.group_type || "evidence"}:${item.group_id || "latest"}`; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(item); });
  groups.forEach((groupItems, key) => {
    const heading = element("div", "artifact-group-heading"); heading.append(element("strong", "", key.replace(":", " · ")), element("span", "", `${groupItems.length} artifacts`)); container.append(heading);
    groupItems.forEach((item) => {
      const row = element("button", "artifact-item"); row.type = "button"; const info = element("div"); const provenance = item.provenance || {};
      info.append(element("strong", "", item.name));
      const size = `${new Intl.NumberFormat().format(item.size_bytes || 0)} bytes${item.chunked_preview ? " · chunked preview" : ""}`;
      info.append(element("span", "", `${item.schema || item.mime_type} · ${size} · SHA ${shortHash(item.sha256)} · ${item.mutability || "status unknown"}`));
      if (provenance.factory_run_id) info.append(element("span", "artifact-provenance", `${provenance.product_name} · ${provenance.factory_status} · run ${provenance.factory_run_id} · output ${shortHash(provenance.output_state_hash)} · proof ${provenance.proof_status} ${provenance.proof_score}/100`));
      row.append(info, element("span", "", "Open")); row.addEventListener("click", () => previewArtifact(item, 0, true)); container.append(row);
    });
  });
}


async function previewArtifact(item, offset = 0, reset = false) {
  try {
    const result = await api(`/api/v1/artifacts/content/${encodeURIComponent(item.id)}?offset=${offset}&limit=200000`);
    const provenance = result.provenance || {};
    const metadata = `Origin: ${result.origin || "unknown"}\nGroup: ${result.group_type || "evidence"}/${result.group_id || "latest"}\nSchema: ${result.schema || result.mime_type}\nSize: ${new Intl.NumberFormat().format(result.size_bytes || 0)} bytes\nIntegrity: ${result.integrity || "unknown"}\nSHA-256: ${result.sha256 || "unknown"}\nMutability: ${result.mutability || "unknown"}\nCreated: ${formatDate(result.created_at)}\nModified: ${formatDate(result.modified_at)}\n${provenance.factory_run_id ? `Factory run: ${provenance.factory_run_id}\nProduct: ${provenance.product_name}\nFactory state: ${provenance.factory_status}\nOutput state: ${provenance.output_state_hash}\nTarget: ${provenance.target_path}\nProof: ${provenance.proof_status} ${provenance.proof_score}/100\nTransaction: ${provenance.transaction_run_id || "—"} · ${provenance.transaction_status || "—"}\n` : ""}\n`;
    const chunk = typeof result.content === "string" ? result.content : JSON.stringify(result.content, null, 2);
    if (reset) state.artifactPreview = { item, offset: 0, visible: metadata + chunk, nextOffset: result.next_offset };
    else { state.artifactPreview.visible += chunk; state.artifactPreview.nextOffset = result.next_offset; }
    text("artifact-preview-title", `${result.name} · SHA ${shortHash(result.sha256)}`);
    text("artifact-preview-status", result.truncated ? `${new Intl.NumberFormat().format(result.remaining_bytes)} bytes remain · chunked governed preview` : "Complete artifact loaded");
    byId("artifact-preview").textContent = state.artifactPreview.visible;
    byId("artifact-load-more").classList.toggle("hidden", !result.truncated);
    byId("artifact-copy").classList.remove("hidden");
    byId("artifact-preview-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) { banner(error.message, "bad"); }
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
  const container = byId("impact-result"); clear(container); container.className = "result-box";
  const grid = element("div", "result-grid"); [["Risk", result.risk_level], ["Files", (result.impacted_files || []).length], ["Tests", (result.impacted_tests || []).length], ["Features", (result.impacted_features || []).length]].forEach(([label, value]) => { const card = element("div", "result-stat"); card.append(element("span", "", label), element("strong", "", value)); grid.append(card); }); container.append(grid);
  const sections = [["Impacted files", result.impacted_files || []], ["Impacted tests", result.impacted_tests || []], ["Impacted features", result.impacted_features || []]];
  sections.forEach(([title, items]) => { const details = element("details", "evidence-detail"); details.open = true; details.append(element("summary", "", `${title} · ${items.length}`)); const list = element("ul", "evidence-list"); items.slice(0, 50).forEach((item) => list.append(element("li", "", typeof item === "string" ? item : (item.path || item.name || item.node || JSON.stringify(item))))); details.append(list); container.append(details); });
  const reasons = result.reasons || []; const details = element("details", "evidence-detail"); details.open = true; details.append(element("summary", "", `Reason paths · ${reasons.length}`)); const list = element("ul", "evidence-list"); reasons.slice(0, 50).forEach((reason) => { const node = reason.node || reason.target || "Impact relation"; const paths = reason.reasons || [reason.reason].filter(Boolean); list.append(element("li", "", `${node}: ${paths.join("; ") || "repository graph relation"}`)); }); details.append(list); container.append(details);
}


function renderContext(result) {
  const container = byId("context-result"); clear(container); container.className = "result-box";
  const saturated = result.budget_status === "SATURATED" || result.estimated_tokens >= result.token_budget;
  const grid = element("div", "result-grid"); [["Pack", result.context_pack_id], ["Task type", result.task_type], ["Files", (result.files || []).length], ["Tokens", `${result.estimated_tokens}/${result.token_budget}${saturated ? " · SATURATED" : ""}`], ["Tests", (result.tests || []).length], ["Precision", Number(result.context_precision_score || 0).toFixed(4)], ["Manifest", shortHash(result.manifest_hash)], ["Selection rules", result.selection_rule_version || "unknown"]].forEach(([label, value]) => { const card = element("div", `result-stat${label === "Tokens" && saturated ? " warning" : ""}`); card.append(element("span", "", label), element("strong", "", value)); grid.append(card); }); container.append(grid);
  container.append(element("p", saturated ? "state-banner warning" : "state-banner", result.context_precision_explanation || (saturated ? "Token budget fully consumed; inspect omissions and truncation before trusting completeness." : "Context compiled within budget.")));
  const allocationItems = Array.isArray(result.token_allocation) ? result.token_allocation : Object.entries(result.token_allocation || {}).map(([path, estimated_tokens]) => ({ path, estimated_tokens }));
  const allocation = new Map(allocationItems.map((item) => [item.path, item]));
  [["Selected files", result.files || []], ["Selected tests", result.tests || []]].forEach(([title, items]) => { const details = element("details", "evidence-detail"); details.open = true; details.append(element("summary", "", `${title} · ${items.length}`)); const list = element("ul", "evidence-list"); items.forEach((item) => { const path = typeof item === "string" ? item : (item.path || item.file || item.name || JSON.stringify(item)); const tokenItem = allocation.get(path) || {}; const tokens = tokenItem.estimated_tokens ?? "?"; const reason = typeof item === "object" ? (item.reason || item.selection_reason || "repository relevance") : (tokenItem.reason || "repository relevance"); list.append(element("li", "", `${path} · ${tokens} tokens · ${reason}`)); }); details.append(list); container.append(details); });
  const omitted = result.omitted_candidates || []; const omissions = element("details", "evidence-detail"); omissions.open = saturated; omissions.append(element("summary", "", `Omitted candidates · ${omitted.length}${result.truncated ? " · TRUNCATED" : ""}`)); const list = element("ul", "evidence-list"); omitted.slice(0, 100).forEach((item) => list.append(element("li", "", typeof item === "string" ? item : `${item.path || item.name || "candidate"} · ${item.reason || "budget/relevance rule"}`))); omissions.append(list); container.append(omissions);
}


function openActionDialog(action, targetId = "") {
  const dialog = byId("action-dialog");
  const titles = {
    approve: "Approve patch",
    reject: "Reject patch",
    rollback: "Rollback transaction",
    apply: "Apply approved patch",
    verify: "Run verification",
    "deployment-approve": "Approve deployment",
    "deployment-promote": "Promote deployment",
    "factory-rollback": "Rollback factory output",
  };

  text("dialog-title", titles[action] || "Confirm action");

  if (action === "verify") {
    text(
      "dialog-copy",
      "Basalt will run the complete configured proof process."
    );
  } else if (action === "deployment-approve") {
    text(
      "dialog-copy",
      `Approve ${targetId} after reviewing its proof, checksum, and environment. Approval does not promote it automatically.`
    );
  } else if (action === "factory-rollback") {
    text("dialog-copy", `Quarantine verified factory output ${targetId} and append a rollback state. The original evidence remains auditable.`);
  } else if (action === "deployment-promote") {
    text(
      "dialog-copy",
      `Promote approved deployment ${targetId}. This action is recorded in the deployment ledger.`
    );
  } else {
    text(
      "dialog-copy",
      `This action will be recorded against ${targetId}.`
    );
  }

  byId("dialog-run-id").value = targetId;
  byId("dialog-action").value = action;

  byId("dialog-actor-label").classList.toggle(
    "hidden",
    ["verify", "apply"].includes(action)
  );

  byId("dialog-reason-label").classList.toggle(
    "hidden",
    ["verify", "apply", "deployment-promote"].includes(action)
  );

  byId("dialog-token-label").classList.toggle(
    "hidden",
    action !== "apply"
  );

  byId("dialog-actor").value = "";
  byId("dialog-reason").value = "";
  byId("dialog-approval-token").value = "";
  dialog.showModal();
}

async function submitAction(event) {
  event.preventDefault();

  const action = byId("dialog-action").value;
  const targetId = byId("dialog-run-id").value;
  const actor = byId("dialog-actor").value.trim();
  const reason = byId("dialog-reason").value.trim();
  const approvalToken = byId("dialog-approval-token").value.trim();

  let path = "/api/v1/verify";
  let body = { sandbox: "auto" };

  if (action === "factory-rollback") {
    path = `/api/v1/factory/runs/${encodeURIComponent(targetId)}/rollback`;
    body = { actor, reason };
  } else if (action.startsWith("deployment-")) {
    const deploymentAction = action.replace("deployment-", "");
    path = `/api/v1/beta/deployments/${encodeURIComponent(targetId)}/${deploymentAction}`;
    body = deploymentAction === "approve" ? { actor, reason } : { actor };
  } else if (action !== "verify") {
    path = `/api/v1/runs/${encodeURIComponent(targetId)}/${action}`;
    body = action === "apply"
      ? { approval_token: approvalToken, sandbox: "auto" }
      : { actor, reason };
  }

  try {
    byId("dialog-submit").disabled = true;

    const result = await api(path, {
      method: "POST",
      body: JSON.stringify(body),
      action: true,
    });

    byId("action-dialog").close();

    if (result.approval_token) {
      await navigator.clipboard
        ?.writeText(result.approval_token)
        .catch(() => undefined);

      banner(
        "Approved. The one-time apply token was copied to your clipboard."
      );
    } else {
      banner(`${action.replace("deployment-", "deployment ")} completed successfully.`);
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
    const [overview, proof, factory, beta, architecture, preview, operations] = await Promise.all([
      api("/api/v1/overview"), api("/api/v1/proof"), api("/api/v1/factory"), api("/api/v1/beta"),
      api("/api/v1/architecture"), api("/api/v1/preview"), api("/api/v1/operations")
    ]);
    renderOverview(overview);
    renderProof(proof || {});
    renderFactoryState(factory || {});
    renderBeta(beta || {});
    renderArchitecture(architecture || {});
    renderPreview(preview || {});
    renderOperations(operations || {});
    if (state.selectedTransaction && !byId("run-detail-panel").classList.contains("hidden")) {
      const latest = (overview.transactions?.recent || []).find((item) => item.run_id === state.selectedTransaction.run_id && (item.kind || "agent") === state.selectedTransaction.kind);
      if (latest) await showTransaction(latest);
    }
    if (state.selectedFactoryRun && !byId("factory-detail-panel").classList.contains("hidden")) {
      const refreshed = await api(`/api/v1/factory/runs/${encodeURIComponent(state.selectedFactoryRun.run_id)}`);
      renderFactoryDetail(refreshed);
    }
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
byId("close-run-detail").addEventListener("click", () => { state.selectedTransaction = null; byId("run-detail-panel").classList.add("hidden"); });
byId("action-form").addEventListener("submit", submitAction);
byId("impact-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const errorNode = byId("impact-error"); const target = byId("impact-target").value.trim();
  if (!target) { errorNode.textContent = "Enter a repository file, symbol, route, or feature."; errorNode.classList.remove("hidden"); byId("impact-target").focus(); return; }
  errorNode.classList.add("hidden");
  try { renderImpact(await api("/api/v1/impact", { method: "POST", body: JSON.stringify({ target, depth: Number(byId("impact-depth").value) }) })); }
  catch (error) { errorNode.textContent = error.message; errorNode.classList.remove("hidden"); }
});
byId("context-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const errorNode = byId("context-error"); const task = byId("context-task").value.trim();
  if (!task) { errorNode.textContent = "Describe the task whose context should be compiled."; errorNode.classList.remove("hidden"); byId("context-task").focus(); return; }
  errorNode.classList.add("hidden");
  try { const targets = byId("context-targets").value.split(",").map((item) => item.trim()).filter(Boolean); renderContext(await api("/api/v1/context", { method: "POST", body: JSON.stringify({ task, role: byId("context-role").value, targets, budget: Number(byId("context-budget").value) }) })); }
  catch (error) { errorNode.textContent = error.message; errorNode.classList.remove("hidden"); }
});

byId("factory-plan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const users = byId("factory-users").value.split(",").map((item) => item.trim()).filter(Boolean);
  const constraints = byId("factory-constraints").value.split("\n").map((item) => item.trim()).filter(Boolean);
  const errorNode = byId("factory-form-error"); const name = byId("factory-name").value.trim(); const prompt = byId("factory-prompt").value.trim();
  if (!name || !prompt) { errorNode.textContent = "Product name and product intent are required."; errorNode.classList.remove("hidden"); (name ? byId("factory-prompt") : byId("factory-name")).focus(); return; }
  errorNode.classList.add("hidden");
  try {
    const run = await api("/api/v1/factory/plan", {
      method: "POST",
      action: true,
      body: JSON.stringify({
        name: byId("factory-name").value,
        prompt: byId("factory-prompt").value,
        template: byId("factory-template").value,
        users, constraints, privacy: byId("factory-privacy").value,
      }),
    });
    banner("Governed factory plan created.");
    await loadAll();
    renderFactoryDetail(run);
  } catch (error) { banner(error.message, "bad"); }
});
byId("close-factory-detail").addEventListener("click", () => byId("factory-detail-panel").classList.add("hidden"));
byId("preview-start").addEventListener("click", async () => {
  try {
    const result = await api("/api/v1/preview/start", { method: "POST", action: true, body: JSON.stringify({ actor: "local-user" }) });
    renderPreview(result); banner("Static preview started without arbitrary code execution.");
  } catch (error) { banner(error.message, "bad"); }
});
byId("preview-stop").addEventListener("click", async () => {
  try {
    const result = await api("/api/v1/preview/stop", { method: "POST", action: true, body: JSON.stringify({ actor: "local-user" }) });
    renderPreview(result); banner("Preview stopped.");
  } catch (error) { banner(error.message, "bad"); }
});

byId("artifact-load-more").addEventListener("click", () => { const preview = state.artifactPreview; if (preview.item && preview.nextOffset != null) previewArtifact(preview.item, preview.nextOffset, false); });
byId("artifact-copy").addEventListener("click", async () => { try { await navigator.clipboard.writeText(state.artifactPreview.visible || ""); banner("Visible evidence copied."); } catch { banner("Clipboard access was unavailable.", "bad"); } });

const initialSection = window.location.hash.slice(1);
if (["overview", "factory", "plan", "agents", "proof", "architecture", "graph", "preview", "transactions", "approvals", "beta", "operations", "evidence"].includes(initialSection)) switchView(initialSection);
initialize();
