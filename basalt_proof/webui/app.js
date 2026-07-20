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
  const models = data.models || [];
  if (!models.length) {
    inventory.className = "stack-list empty-state";
    inventory.textContent = "No model profiles loaded.";
  } else {
    inventory.className = "stack-list";
    models.forEach((item) => {
      const card = element("div", "stack-item");
      card.append(element("strong", "", `${item.provider}/${item.model}`));
      card.append(element("p", "", `${item.available ? "Available" : "Not configured"} · ${item.privacy_modes.join(", ")} · ${item.capabilities.join(", ")}`));
      inventory.append(card);
    });
  }
}

function renderFactoryDetail(run) {
  state.selectedFactoryRun = run;
  text("factory-detail-title", `${run.product_name} · ${run.run_id}`);
  const container = byId("factory-detail");
  clear(container);
  const entries = [
    ["Status", run.status], ["Template", run.template], ["Base state", run.base_state_version],
    ["Committed state", run.committed_state_version || "—"], ["Tasks", (run.tasks || []).length],
    ["Epochs", (run.epochs || []).length], ["Proof", run.proof_status ? `${run.proof_status} ${run.proof_score}/100` : "Not run"],
    ["Output state", shortHash(run.project_state_hash)], ["Target", run.target_path || "Not assembled"],
    ["Execution mode", run.execution_truth?.mode || "DETERMINISTIC_LOCAL"], ["Message", run.message],
  ];
  entries.forEach(([label, value]) => {
    const card = element("div", "detail-card");
    card.append(element("span", "", label), element("strong", "", value));
    container.append(card);
  });
  const actions = byId("factory-detail-actions");
  clear(actions);
  if (run.status === "PLANNED") {
    const build = element("button", "button primary", "Build and prove");
    build.type = "button";
    build.disabled = !state.bootstrap.actions_enabled;
    build.addEventListener("click", () => buildFactoryRun(run.run_id));
    actions.append(build);
  }
  if (run.rollback?.eligible || run.status === "VERIFIED") {
    const rollback = element("button", "button secondary", "Rollback factory output");
    rollback.type = "button";
    rollback.disabled = !state.bootstrap.actions_enabled;
    rollback.addEventListener("click", () => openActionDialog("factory-rollback", run.run_id));
    actions.append(rollback);
  }
  if (run.execution_truth?.claim) {
    const truth = element("p", "muted", run.execution_truth.claim);
    actions.append(truth);
  }
  byId("factory-detail-panel").classList.remove("hidden");
  renderPlan(run);
  renderAgentRecords(run.agent_records || []);
}

function renderPlan(run) {
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
  (run.tasks || []).forEach((task) => {
    const row = document.createElement("tr");
    row.append(element("td", "", `${task.task_id} · ${task.title}`));
    row.append(element("td", "", `${task.epoch} · ${task.epoch_name}`));
    row.append(element("td", "", task.agent_role));
    row.append(element("td", "", task.risk_level));
    const statusCell = document.createElement("td");
    statusCell.append(element("span", `status-mini ${task.status || ""}`, task.status || "PLANNED"));
    row.append(statusCell);
    body.append(row);
  });
}

function renderAgentRecords(records) {
  const container = byId("agent-execution-list");
  clear(container);
  if (!records.length) {
    container.className = "stack-list empty-state";
    container.textContent = "The selected plan has not executed yet.";
    return;
  }
  container.className = "stack-list";
  records.forEach((item) => {
    const card = element("div", "stack-item");
    card.append(element("strong", "", `${item.agent_role} · ${item.status}`));
    const model = item.model_assignment?.model || "not invoked";
    const mode = item.execution_mode || "DETERMINISTIC_LOCAL";
    const deps = (item.dependency_ids || []).length ? ` · depends on ${(item.dependency_ids || []).join(", ")}` : "";
    card.append(element("p", "", `${item.summary} · ${mode} · routed profile ${model}${deps}`));
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
        ["Type", "Factory state transaction"], ["Status", run.status], ["Product", run.product_name],
        ["Base state version", run.base_state_version], ["Committed state version", run.committed_state_version || "—"],
        ["Output state hash", shortHash(run.project_state_hash)], ["Tasks", (run.tasks || []).length],
        ["Epochs", (run.epochs || []).length], ["Proof", run.proof_status ? `${run.proof_status} ${run.proof_score}/100` : "Not run"],
        ["Target", run.target_path], ["Execution truth", run.execution_truth?.mode || "DETERMINISTIC_LOCAL"],
        ["Updated", formatDate(run.updated_at)], ["Rollback", run.rollback?.performed ? "Performed" : (run.rollback?.eligible ? "Eligible" : "Not eligible")],
      ]);
      if (run.rollback?.record) {
        const record = run.rollback.record;
        appendTransactionEntries(container, [
          ["Rolled back by", record.actor], ["Rollback reason", record.reason],
          ["Restored hash", shortHash(record.restored_state_hash)], ["Quarantine", record.quarantine_path],
        ]);
      }
      const actions = element("div", "approval-actions");
      if (run.rollback?.eligible) {
        const rollback = element("button", "button secondary", "Rollback factory output");
        rollback.type = "button";
        rollback.disabled = !state.bootstrap.actions_enabled;
        rollback.addEventListener("click", () => openActionDialog("factory-rollback", run.run_id));
        actions.append(rollback);
      }
      if (actions.childElementCount) container.append(actions);
    } else {
      const run = await api(`/api/v1/runs/${encodeURIComponent(item.run_id)}`);
      text("run-detail-title", run.run_id);
      const patch = run.patch_scope || {};
      const impact = run.impact_radius || {};
      const decision = run.decision_context || {};
      const approval = decision.approval || {};
      const provenance = run.transaction_provenance || {};
      appendTransactionEntries(container, [
        ["Type", "Agent patch transaction"], ["Status", run.status], ["Task", run.task], ["Proposer", run.agent_role],
        ["Base state", shortHash(run.base_state_hash)], ["Current state", shortHash(run.current_state_hash)],
        ["Patch files", patch.files_changed ?? (patch.files || []).length], ["Changed lines", patch.changed_lines || 0],
        ["Additions / deletions", `+${patch.additions || 0} / −${patch.deletions || 0}`],
        ["Impact radius · files", (impact.files || []).length], ["Impact radius · tests", (impact.tests || []).length],
        ["Impact radius · features", (impact.features || []).length], ["Policy verdict", decision.policy_verdict],
        ["Risk", decision.risk], ["Required approvals", (decision.required_approvals || []).join(", ") || "None"],
        ["Approved by", approval.actor || "—"], ["Approval reason", approval.reason || "—"],
        ["Proof after", provenance.proof_status ? `${provenance.proof_status} ${provenance.proof_score}/100` : "Not committed"],
        ["Rollback", run.rollback?.performed ? `Performed · ${shortHash(run.rollback.restored_hash)}` : (run.rollback?.eligible ? "Eligible" : "Not eligible")],
        ["Message", run.message], ["Created", formatDate(run.created_at)], ["Updated", formatDate(run.updated_at)],
      ]);
      if ((decision.policy_reasons || []).length) {
        const details = element("details", "evidence-detail");
        details.open = true;
        details.append(element("summary", "", "Policy reasons and risk controls"));
        const list = element("ul", "evidence-list");
        (decision.policy_reasons || []).forEach((reason) => list.append(element("li", "", reason)));
        (decision.risk_flags || []).forEach((flag) => list.append(element("li", "", `Risk flag: ${flag}`)));
        details.append(list);
        container.append(details);
      }
      if (run.patch_preview) {
        const details = element("details", "evidence-detail");
        details.open = true;
        details.append(element("summary", "", `Proposed patch · ${(patch.files || []).join(", ") || "diff"}`));
        details.append(element("pre", "transaction-diff", run.patch_preview));
        container.append(details);
      }
      if ((run.evidence || []).length) {
        const details = element("details", "evidence-detail");
        details.append(element("summary", "", `${run.evidence.length} linked evidence artifacts`));
        const list = element("div", "artifact-list");
        run.evidence.forEach((artifact) => {
          const row = element("button", "artifact-item");
          row.type = "button";
          row.append(element("strong", "", artifact.name), element("span", "", `SHA ${shortHash(artifact.sha256)} · ${artifact.schema}`));
          row.addEventListener("click", () => { switchView("evidence"); previewArtifact(artifact); });
          list.append(row);
        });
        details.append(list);
        container.append(details);
      }
      const actions = element("div", "approval-actions");
      if (run.status === "AWAITING_APPROVAL") {
        const approve = element("button", "button primary", "Approve");
        approve.type = "button"; approve.disabled = !state.bootstrap.actions_enabled;
        approve.addEventListener("click", () => openActionDialog("approve", run.run_id));
        const reject = element("button", "button secondary", "Reject");
        reject.type = "button"; reject.disabled = !state.bootstrap.actions_enabled;
        reject.addEventListener("click", () => openActionDialog("reject", run.run_id));
        actions.append(approve, reject);
      } else if (run.status === "APPROVED") {
        const apply = element("button", "button primary", "Apply and prove");
        apply.type = "button"; apply.disabled = !state.bootstrap.actions_enabled;
        apply.addEventListener("click", () => openActionDialog("apply", run.run_id));
        actions.append(apply);
      } else if (run.status === "VERIFIED") {
        const rollback = element("button", "button secondary", "Rollback transaction");
        rollback.type = "button"; rollback.disabled = !state.bootstrap.actions_enabled;
        rollback.addEventListener("click", () => openActionDialog("rollback", run.run_id));
        actions.append(rollback);
      }
      if (actions.childElementCount) container.append(actions);
    }
    byId("run-detail-panel").classList.remove("hidden");
    switchView("transactions");
  } catch (error) {
    banner(error.message, "bad");
  }
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
  const workspace = data?.workspace || {};
  const jobs = data?.jobs || {};
  const providers = data?.providers || {};
  const deployments = data?.deployments || {};
  const projects = workspace.projects || [];
  const teams = workspace.teams || [];
  const activity = workspace.activity || [];
  const jobItems = jobs.jobs || [];
  const providerItems = providers.providers || [];
  const deploymentItems = deployments.deployments || [];
  text("beta-project-count", projects.length);
  text("beta-job-count", jobItems.length);
  text("beta-provider-count", providers.configured || 0);
  text("beta-deployment-count", deploymentItems.length);

  const renderStack = (id, items, mapItem, emptyText) => {
    const container = byId(id);
    if (!container) return;
    clear(container);
    if (!items.length) {
      container.className = "stack-list empty-state";
      container.textContent = emptyText;
      return;
    }
    container.className = "stack-list";
    items.slice(0, 12).forEach((item) => {
      const card = element("div", "stack-item");
      const mapped = mapItem(item);
      card.append(element("strong", "", mapped.title));
      card.append(element("p", "", mapped.detail));
      container.append(card);
    });
  };

  const orgItems = teams.map((item) => ({
    ...item,
    activity: activity.find((event) => event.team_id === item.team_id),
  }));
  renderStack("beta-organizations", orgItems, (item) => ({
    title: `${item.name || item.team_id} · ${item.status || "ACTIVE"}`,
    detail: `${item.slug || "local-team"} · owner ${item.created_by || "unknown"}${item.activity ? ` · latest ${item.activity.action}` : ""}`,
  }), `No local organizations registered. ${workspace.counts?.users || 0} users · ${workspace.counts?.memberships || 0} memberships.`);
  renderStack("beta-runtime", data?.runtime?.workspaces || data?.runtime?.items || [], (item) => ({
    title: item.job_id || item.workspace || "Isolated workspace",
    detail: `${item.status || "prepared"} · ${typeof item.profile === "object" ? (item.profile?.name || "private-beta") : (item.profile || "private-beta")}`,
  }), "No active isolated workspaces. Jobs use lease-based local workers; managed remote workers are not claimed.");

  renderStack("beta-projects", projects, (item) => ({
    title: item.name || item.project_id,
    detail: `${item.template || "project"} · ${item.privacy_mode || "local"} · ${item.status || "ACTIVE"}`,
  }), "No private-beta projects registered.");
  renderStack("beta-jobs", jobItems, (item) => ({
    title: `${item.job_type || "JOB"} · ${item.status || "UNKNOWN"}`,
    detail: `${item.job_id || ""} · attempts ${item.attempts || 0}/${item.max_attempts || 0}`,
  }), "No private-beta jobs submitted.");
  renderStack("beta-providers", providerItems, (item) => ({
    title: item.display_name || item.provider_id,
    detail: `${item.model || "model"} · ${item.configured ? "configured" : "not configured"} · ${item.kind || "provider"}`,
  }), "No provider profiles loaded.");
  renderStack("beta-deployments", deploymentItems, (item) => ({
    title: `${item.environment || "preview"} · ${item.status || "UNKNOWN"}`,
    detail: `${item.deployment_id || ""} · ${item.proof_status || "UNKNOWN"} ${item.proof_score || 0}/100`,
  }), "No deployment artifacts packaged.");
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
  text("operations-status", `${data?.status || "UNKNOWN"} · local`);
  text("operations-incidents", metrics.incidents || 0);
  text("operations-high", metrics.high_incidents || 0);
  text("operations-approvals", metrics.pending_approvals || 0);
  text("operations-rollbacks", metrics.rollback_ready || 0);
  renderStack("operations-incident-list", data?.incidents || [], (item) => ({
    title: `${item.severity} · ${item.code}`,
    copy: `${item.summary} · source ${item.source}`,
  }), "No incidents detected from local proof, graph, queue, deployment, or preview state.");
  const recovery = byId("operations-recovery");
  clear(recovery);
  Object.entries(data?.recovery || {}).forEach(([label, value]) => {
    const card = element("div", "detail-card");
    card.append(element("span", "", label.replaceAll("_", " ")), element("strong", "", typeof value === "boolean" ? (value ? "Available" : "Unavailable") : value));
    recovery.append(card);
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
  const groups = new Map();
  items.forEach((item) => {
    const key = `${item.group_type || "evidence"}:${item.group_id || "latest"}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  });
  groups.forEach((groupItems, key) => {
    const heading = element("div", "artifact-group-heading");
    heading.append(element("strong", "", key.replace(":", " · ")));
    heading.append(element("span", "", `${groupItems.length} artifacts`));
    container.append(heading);
    groupItems.forEach((item) => {
      const row = element("button", "artifact-item");
      row.type = "button";
      const info = element("div");
      info.append(element("strong", "", item.name));
      info.append(element("span", "", `${item.schema || item.mime_type} · SHA ${shortHash(item.sha256)} · ${item.mutability || "status unknown"}`));
      row.append(info, element("span", "", "Open"));
      row.addEventListener("click", () => previewArtifact(item));
      container.append(row);
    });
  });
}

async function previewArtifact(item) {
  try {
    const result = await api(`/api/v1/artifacts/content/${encodeURIComponent(item.id)}`);
    text("artifact-preview-title", `${result.name} · SHA ${shortHash(result.sha256)}`);
    const metadata = `Origin: ${result.origin || "unknown"}
Group: ${result.group_type || "evidence"}/${result.group_id || "latest"}
Schema: ${result.schema || result.mime_type}
Integrity: ${result.integrity || "unknown"}
Mutability: ${result.mutability || "unknown"}
Created: ${formatDate(result.created_at)}
Modified: ${formatDate(result.modified_at)}

`;
    byId("artifact-preview").textContent = metadata + (typeof result.content === "string"
      ? result.content
      : JSON.stringify(result.content, null, 2));
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

byId("factory-plan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const users = byId("factory-users").value.split(",").map((item) => item.trim()).filter(Boolean);
  const constraints = byId("factory-constraints").value.split("\n").map((item) => item.trim()).filter(Boolean);
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

const initialSection = window.location.hash.slice(1);
if (["overview", "factory", "plan", "agents", "proof", "architecture", "graph", "preview", "transactions", "approvals", "beta", "operations", "evidence"].includes(initialSection)) switchView(initialSection);
initialize();
