const state = {
  bootstrap: null,
  snapshot: null,
  tree: [],
  flatFiles: [],
  tabs: new Map(),
  order: [],
  activePath: "",
  diagnostics: new Map(),
  diagnosticsTimer: null,
  paletteItems: [],
  paletteIndex: 0,
  activePanel: "build",
  searchQuery: "",
  restoring: false,
};

const $ = (id) => document.getElementById(id);
const qs = (selector, root = document) => root.querySelector(selector);
const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];

function node(tag, className = "", text = "") {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== "") item.textContent = String(text);
  return item;
}

async function api(path, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.body ? { "Content-Type": "application/json" } : {}),
  };
  if (options.action && state.bootstrap?.action_token) {
    headers["X-Basalt-Action-Token"] = state.bootstrap.action_token;
  }
  const response = await fetch(path, { ...options, headers });
  const contentType = response.headers.get("Content-Type") || "";
  const data = contentType.includes("json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(data?.error?.message || "Request failed");
  return data;
}

function toast(message, bad = false) {
  const item = $("toast");
  item.textContent = message;
  item.className = `toast visible${bad ? " bad" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { item.className = "toast"; }, 3200);
}

function setSaveState(text, bad = false) {
  $("save-state").textContent = text;
  $("save-state").style.color = bad ? "var(--bad)" : "";
}

function currentTab() {
  return state.activePath ? state.tabs.get(state.activePath) || null : null;
}

function languageLabel(language) {
  return ({
    python: "Python", javascript: "JavaScript", typescript: "TypeScript", json: "JSON",
    markdown: "Markdown", toml: "TOML", yaml: "YAML", html: "HTML", css: "CSS",
    scss: "SCSS", sql: "SQL", shell: "Shell", plaintext: "Plain Text",
  })[language] || language || "Plain Text";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function tokenClass(groups) {
  if (groups.comment) return "token-comment";
  if (groups.string) return "token-string";
  if (groups.keyword) return "token-keyword";
  if (groups.constant) return "token-constant";
  if (groups.number) return "token-number";
  if (groups.func) return "token-function";
  if (groups.tag) return "token-tag";
  if (groups.attr) return "token-attribute";
  return "";
}

function highlightLine(line, language) {
  if (language === "markdown") {
    if (/^\s{0,3}#{1,6}\s/.test(line)) return `<span class="token-heading">${escapeHtml(line)}</span>`;
  }
  let pattern = null;
  if (language === "python") {
    pattern = /(?<comment>#.*$)|(?<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(?<keyword>\b(?:and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b)|(?<constant>\b(?:True|False|None)\b)|(?<number>\b\d+(?:\.\d+)?\b)|(?<func>\b[A-Za-z_]\w*(?=\s*\())/g;
  } else if (["javascript", "typescript"].includes(language)) {
    pattern = /(?<comment>\/\/.*$)|(?<string>`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(?<keyword>\b(?:async|await|break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|finally|for|from|function|if|import|in|instanceof|let|new|of|return|static|switch|throw|try|typeof|var|void|while|with|yield|interface|type|implements|private|public|protected|readonly)\b)|(?<constant>\b(?:true|false|null|undefined)\b)|(?<number>\b\d+(?:\.\d+)?\b)|(?<func>\b[A-Za-z_$][\w$]*(?=\s*\())/g;
  } else if (language === "json") {
    pattern = /(?<string>"(?:\\.|[^"\\])*")|(?<constant>\b(?:true|false|null)\b)|(?<number>-?\b\d+(?:\.\d+)?(?:e[+-]?\d+)?\b)/gi;
  } else if (["html", "xml"].includes(language)) {
    pattern = /(?<comment><!--.*?-->)|(?<tag><\/?[A-Za-z][^>]*?>)|(?<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')/g;
  } else if (["css", "scss"].includes(language)) {
    pattern = /(?<comment>\/\*.*?\*\/)|(?<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(?<number>\b\d+(?:\.\d+)?(?:px|rem|em|%|vh|vw|s|ms)?\b)|(?<keyword>\b(?:display|position|color|background|border|padding|margin|width|height|grid|flex|font|overflow|transform|transition)\b)/g;
  } else if (["yaml", "toml", "sql", "shell"].includes(language)) {
    pattern = /(?<comment>#.*$|--.*$)|(?<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(?<keyword>\b(?:SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|CREATE|TABLE|JOIN|AS|AND|OR|NOT|NULL|true|false)\b)|(?<number>\b\d+(?:\.\d+)?\b)/gi;
  }
  if (!pattern) return escapeHtml(line);
  let output = "";
  let last = 0;
  for (const match of line.matchAll(pattern)) {
    const index = match.index ?? 0;
    output += escapeHtml(line.slice(last, index));
    const cls = tokenClass(match.groups || {});
    output += cls ? `<span class="${cls}">${escapeHtml(match[0])}</span>` : escapeHtml(match[0]);
    last = index + match[0].length;
  }
  return output + escapeHtml(line.slice(last));
}

function renderHighlight(content, language) {
  const highlighted = content.split("\n").map((line) => highlightLine(line, language)).join("\n");
  qs("#highlight code").innerHTML = `${highlighted}${content.endsWith("\n") ? "\n" : ""}`;
}

function renderLineNumbers(content) {
  const lines = Math.max(1, content.split("\n").length);
  $("line-numbers").textContent = Array.from({ length: lines }, (_, index) => index + 1).join("\n");
}

function updateCursorPosition() {
  const tabState = currentTab();
  if (!tabState) { $("cursor-position").textContent = "No cursor"; return; }
  const code = $("code");
  const before = code.value.slice(0, code.selectionStart);
  const lines = before.split("\n");
  $("cursor-position").textContent = `Ln ${lines.length}, Col ${lines.at(-1).length + 1}`;
}


function syncEditorScroll() {
  const code = $("code");
  $("highlight").scrollTop = code.scrollTop;
  $("highlight").scrollLeft = code.scrollLeft;
  $("line-numbers").scrollTop = code.scrollTop;
}

function fileIcon(path, kind = "file") {
  if (kind === "directory") return "▸";
  const ext = path.split(".").pop()?.toLowerCase();
  return ({ py: "PY", js: "JS", jsx: "JS", ts: "TS", tsx: "TS", json: "{}", md: "MD", html: "<>", css: "#", yml: "Y", yaml: "Y", toml: "T", sql: "DB" })[ext] || "·";
}

function flattenTree(items) {
  const output = [];
  items.forEach((item) => {
    if (item.kind === "file") output.push(item);
    if (item.children) output.push(...flattenTree(item.children));
  });
  return output;
}

function renderTreeItems(items, parent, depth = 0) {
  items.forEach((item) => {
    const wrapper = node("div", "tree-node");
    const row = node("button", `tree-row ${item.kind}`);
    row.type = "button";
    row.style.paddingLeft = `${8 + depth * 13}px`;
    const icon = node("span", "file-icon", fileIcon(item.path, item.kind));
    const label = node("span", "label", item.name);
    const meta = node("span", "meta", item.kind === "file" ? "" : String(item.children?.length || ""));
    row.append(icon, label, meta);
    wrapper.append(row);
    if (item.kind === "directory") {
      const children = node("div", "tree-children");
      renderTreeItems(item.children || [], children, depth + 1);
      row.addEventListener("click", () => {
        children.classList.toggle("collapsed");
        icon.textContent = children.classList.contains("collapsed") ? "▸" : "▾";
      });
      icon.textContent = "▾";
      wrapper.append(children);
    } else {
      row.dataset.path = item.path;
      row.title = item.path;
      row.addEventListener("click", () => openFile(item.path));
    }
    parent.append(wrapper);
  });
}

function markActiveTreePath() {
  qsa(".tree-row.file").forEach((item) => item.classList.toggle("active", item.dataset.path === state.activePath));
}

async function loadTree() {
  const data = await api("/api/v1/workspace/tree?depth=7");
  state.tree = data.items || [];
  state.flatFiles = flattenTree(state.tree);
  const root = $("tree");
  root.replaceChildren();
  renderTreeItems(state.tree, root);
  markActiveTreePath();
}

function renderTabs() {
  const root = $("file-tabs");
  root.replaceChildren();
  state.order.forEach((path) => {
    const tabState = state.tabs.get(path);
    if (!tabState) return;
    const tab = node("button", `file-tab${path === state.activePath ? " active" : ""}${tabState.dirty ? " dirty" : ""}`);
    tab.type = "button";
    tab.dataset.path = path;
    tab.title = path;
    const dirty = node("span", "dirty-dot");
    const name = node("span", "tab-name", path.split("/").at(-1));
    const close = node("button", "close-tab", "×");
    close.type = "button";
    close.title = `Close ${path}`;
    close.addEventListener("click", (event) => { event.stopPropagation(); closeTab(path); });
    tab.append(dirty, name, close);
    tab.addEventListener("click", () => activateTab(path));
    root.append(tab);
  });
}

function updateActionState() {
  const tabState = currentTab();
  const actionsEnabled = Boolean(state.bootstrap?.actions_enabled);
  $("save").disabled = !tabState || !tabState.dirty || !actionsEnabled;
  $("review-diff").disabled = !tabState || !tabState.dirty;
  $("reload-file").disabled = !tabState;
  const dirtyCount = [...state.tabs.values()].filter((item) => item.dirty).length;
  setSaveState(dirtyCount ? `${dirtyCount} modified` : "Clean");
}

function updateEditorForActiveTab() {
  const tabState = currentTab();
  renderTabs(); markActiveTreePath();
  if (!tabState) {
    $("empty-editor").classList.remove("hidden"); $("editor-frame").classList.add("hidden");
    $("breadcrumbs").textContent = "Select a file from the repository"; $("footer-path").textContent = "No file selected";
    $("footer-language").textContent = "No document"; $("footer-encoding").textContent = "—"; $("cursor-position").textContent = "No cursor";
    $("file-meta").textContent = "No document"; $("git-file-state").className = "file-truth hidden"; $("git-file-state").textContent = "";
    $("diagnostics-label").textContent = "No file selected"; $("diagnostics-summary").disabled = true; updateActionState(); return;
  }
  $("empty-editor").classList.add("hidden"); $("editor-frame").classList.remove("hidden"); $("code").disabled = false; $("code").value = tabState.content;
  $("breadcrumbs").textContent = tabState.path.split("/").join("  /  "); $("footer-path").textContent = tabState.path;
  $("footer-language").textContent = languageLabel(tabState.language); $("footer-encoding").textContent = "UTF-8";
  $("file-meta").textContent = `${tabState.line_count ?? Math.max(1, tabState.content.split("\n").length)} lines · ${tabState.size_bytes} bytes · ${tabState.sha256.slice(0, 12)}`;
  const gitTruth = tabState.git || {};
  const gitNode = $("git-file-state");
  if (gitTruth.ignored) { gitNode.className = "file-truth warning"; gitNode.textContent = `IGNORED BY GIT · changes will not be committed${gitTruth.rule ? ` · ${gitTruth.rule}` : ""}`; }
  else if (gitTruth.tracked) { gitNode.className = "file-truth good"; gitNode.textContent = "Tracked by Git"; }
  else { gitNode.className = "file-truth warning"; gitNode.textContent = "UNTRACKED BY GIT · save does not stage or commit this file"; }
  renderLineNumbers(tabState.content); renderHighlight(tabState.content, tabState.language); syncEditorScroll();
  requestAnimationFrame(() => { const code = $("code"); const max = code.value.length; const start = Math.max(0, Math.min(Number(tabState.cursorStart || 0), max)); const end = Math.max(start, Math.min(Number(tabState.cursorEnd || start), max)); code.setSelectionRange(start, end); code.scrollTop = Number(tabState.scrollTop || 0); code.scrollLeft = Number(tabState.scrollLeft || 0); syncEditorScroll(); updateCursorPosition(); });
  renderDiagnosticsSummary(state.diagnostics.get(tabState.path)); updateActionState();
}


function activateTab(path) {
  if (!state.tabs.has(path)) return;
  captureActiveTabView();
  state.activePath = path;
  updateEditorForActiveTab();
  scheduleDiagnostics();
  persistWorkspaceState();
}

function closeTab(path) {
  const tabState = state.tabs.get(path);
  if (!tabState) return;
  if (tabState.dirty && !window.confirm(`${path} has unsaved changes. Close without saving?`)) return;
  const index = state.order.indexOf(path);
  state.tabs.delete(path);
  state.order = state.order.filter((item) => item !== path);
  if (state.activePath === path) {
    state.activePath = state.order[index] || state.order[index - 1] || state.order.at(-1) || "";
  }
  updateEditorForActiveTab();
  persistWorkspaceState();
}

async function openFile(path, line = 0) {
  try {
    if (!state.tabs.has(path)) {
      const file = await api(`/api/v1/workspace/file?path=${encodeURIComponent(path)}`);
      state.tabs.set(path, {
        ...file,
        originalContent: file.content,
        dirty: false,
      });
      state.order.push(path);
    }
    activateTab(path);
    if (line > 0) requestAnimationFrame(() => goToLine(line));
  } catch (error) {
    toast(error.message, true);
  }
}

function goToLocation(line, column = 1, endColumn = null) {
  const code = $("code");
  const lines = code.value.split("\n");
  const targetLine = Math.max(1, Math.min(Number(line) || 1, lines.length));
  const lineText = lines[targetLine - 1] || "";
  const targetColumn = Math.max(1, Math.min(Number(column) || 1, lineText.length + 1));
  const lineStart = lines.slice(0, targetLine - 1).reduce((sum, item) => sum + item.length + 1, 0);
  const start = lineStart + targetColumn - 1;
  const requestedEnd = endColumn == null ? targetColumn : Number(endColumn) || targetColumn;
  const end = lineStart + Math.max(targetColumn - 1, Math.min(requestedEnd - 1, lineText.length));
  code.focus();
  code.setSelectionRange(start, Math.max(start, end));
  const lineHeight = parseFloat(getComputedStyle(code).lineHeight) || 20.8;
  code.scrollTop = Math.max(0, (targetLine - 4) * lineHeight);
  syncEditorScroll();
  updateCursorPosition();
  captureActiveTabView();
  persistWorkspaceState();
}

function goToLine(line) {
  goToLocation(line, 1);
}

async function reloadActive(force = false) {
  const tabState = currentTab();
  if (!tabState) return;
  if (tabState.dirty && !force && !window.confirm("Discard unsaved changes and reload the repository version?")) return;
  try {
    const file = await api(`/api/v1/workspace/file?path=${encodeURIComponent(tabState.path)}`);
    state.tabs.set(tabState.path, { ...file, originalContent: file.content, dirty: false });
    updateEditorForActiveTab();
    await runDiagnostics();
    persistWorkspaceState();
    toast("Repository version reloaded.");
  } catch (error) {
    toast(error.message, true);
  }
}

function onEditorInput() {
  const tabState = currentTab();
  if (!tabState) return;
  tabState.content = $("code").value;
  tabState.dirty = tabState.content !== tabState.originalContent;
  tabState.line_count = Math.max(1, tabState.content.split("\n").length);
  tabState.size_bytes = new TextEncoder().encode(tabState.content).length;
  renderLineNumbers(tabState.content);
  renderHighlight(tabState.content, tabState.language);
  renderTabs();
  updateActionState();
  $("file-meta").textContent = `${tabState.line_count} lines · ${tabState.size_bytes} bytes · unsaved`;
  captureActiveTabView();
  persistWorkspaceState();
  scheduleDiagnostics();
}

function scheduleDiagnostics() {
  clearTimeout(state.diagnosticsTimer);
  state.diagnosticsTimer = setTimeout(runDiagnostics, 260);
}

async function runDiagnostics() {
  const tabState = currentTab();
  if (!tabState) return null;
  try {
    const result = await api("/api/v1/workspace/diagnostics", {
      method: "POST",
      body: JSON.stringify({ path: tabState.path, content: tabState.content }),
    });
    state.diagnostics.set(tabState.path, result);
    renderDiagnosticsSummary(result);
    return result;
  } catch (error) {
    toast(error.message, true);
    return null;
  }
}

function renderDiagnosticsSummary(result) {
  const dot = $("diagnostics-dot");
  dot.className = "diagnostics-dot";
  if (!result) {
    $("diagnostics-label").textContent = "Diagnostics pending";
    $("diagnostics-summary").disabled = !currentTab();
    return;
  }
  dot.classList.add(result.status.toLowerCase());
  $("diagnostics-label").textContent = result.errors || result.warnings
    ? `${result.errors} errors · ${result.warnings} warnings`
    : "No diagnostics";
  $("diagnostics-summary").disabled = false;
}

function showDiagnostics() {
  const tabState = currentTab(); if (!tabState) return;
  const result = state.diagnostics.get(tabState.path); const root = $("diagnostics-list"); root.replaceChildren();
  if (!result || !result.items.length) root.append(node("div", "clean-diagnostics", "No diagnostics for the current file."));
  else {
    const list = node("div", "diagnostic-items");
    result.items.forEach((item) => {
      const card = node("button", "diagnostic-item"); card.type = "button";
      card.append(node("strong", "", `${item.severity} · ${item.code || "DIAGNOSTIC"}`));
      card.append(node("p", "", `Line ${item.line}, column ${item.column}${item.end_column ? `–${item.end_column}` : ""} — ${item.message}`));
      card.addEventListener("click", () => {
        const navigate = () => { activateTab(tabState.path); goToLocation(item.line, item.column, item.end_column); $("code").focus(); };
        if ($("diagnostics-dialog").open) { $("diagnostics-dialog").addEventListener("close", () => requestAnimationFrame(navigate), { once: true }); $("diagnostics-dialog").close(); }
        else requestAnimationFrame(navigate);
      });
      list.append(card);
    }); root.append(list);
  }
  $("diagnostics-dialog").showModal();
}


async function reviewDiff() {
  const tabState = currentTab();
  if (!tabState) return;
  try {
    const [diff, diagnostics] = await Promise.all([
      api("/api/v1/workspace/diff", {
        method: "POST",
        body: JSON.stringify({ path: tabState.path, content: tabState.content, expected_sha256: tabState.sha256 }),
      }),
      runDiagnostics(),
    ]);
    $("diff-title").textContent = tabState.path;
    const summary = $("diff-summary");
    summary.replaceChildren(
      node("span", "", diff.changed ? "Changes detected" : "No changes"),
      node("span", "add", `+${diff.additions}`),
      node("span", "del", `−${diff.deletions}`),
      node("span", "", diagnostics ? `${diagnostics.errors} errors · ${diagnostics.warnings} warnings` : "Diagnostics unavailable"),
    );
    $("diff-output").textContent = diff.unified_diff;
    const conflict = Boolean(diff.conflict);
    $("conflict-actions").classList.toggle("hidden", !conflict);
    $("confirm-save").disabled = conflict || !diff.changed || Boolean(diagnostics?.errors);
    $("confirm-save").title = diagnostics?.errors ? "Resolve diagnostics errors before saving." : "";
    $("diff-dialog").showModal();
  } catch (error) {
    toast(error.message, true);
  }
}

async function persistSave() {
  const tabState = currentTab();
  if (!tabState) return;
  try {
    setSaveState("Saving…");
    $("confirm-save").disabled = true;
    const result = await api("/api/v1/workspace/file", {
      method: "POST",
      action: true,
      body: JSON.stringify({
        path: tabState.path,
        content: tabState.content,
        expected_sha256: tabState.sha256,
        actor: "Workspace user",
      }),
    });
    state.tabs.set(tabState.path, { ...result, originalContent: result.content, dirty: false });
    $("diff-dialog").close();
    updateEditorForActiveTab();
    await Promise.all([loadActivity(), loadGit()]);
    persistWorkspaceState();
    toast("Saved atomically after governed diff review.");
  } catch (error) {
    setSaveState("Conflict", true);
    toast(error.message, true);
    $("conflict-actions").classList.remove("hidden");
  } finally {
    $("confirm-save").disabled = false;
  }
}

async function searchRepository(query) {
  state.searchQuery = String(query || "");
  persistWorkspaceState();
  const term = state.searchQuery.trim();
  const tree = $("tree");
  const results = $("search-results");
  if (term.length < 2) {
    tree.classList.remove("hidden");
    results.classList.add("hidden");
    $("search-summary").classList.add("hidden");
    return;
  }
  try {
    const data = await api(`/api/v1/workspace/search?q=${encodeURIComponent(term)}&limit=150`);
    results.replaceChildren();
    data.items.forEach((item) => {
      const button = node("button", "search-result");
      button.type = "button";
      button.append(node("strong", "", `${item.path}${item.line ? `:${item.line}` : ""}`));
      button.append(node("p", "", item.preview || "Match"));
      button.addEventListener("click", () => openFile(item.path, item.line));
      results.append(button);
    });
    if (!data.items.length) results.append(node("div", "empty-panel", "No repository matches."));
    $("search-summary").textContent = `${data.count} matches for “${data.query}”`;
    $("search-summary").classList.remove("hidden");
    tree.classList.add("hidden");
    results.classList.remove("hidden");
  } catch (error) {
    toast(error.message, true);
  }
}

function switchPanel(name) {
  state.activePanel = name;
  persistWorkspaceState();
  qsa(".panel-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.panel === name));
  qsa(".panel-view").forEach((panel) => panel.classList.toggle("active", panel.id === `panel-${name}`));
  if (name === "proof") loadProof();
  if (name === "activity") loadActivity();
  if (name === "git") loadGit();
}

async function runCommand(name) {
  const terminal = $("terminal"); const metadata = state.snapshot?.command_metadata?.[name] || {};
  switchPanel("build"); terminal.textContent = `Running ${metadata.display_name || name}…`; qsa("[data-command]").forEach((button) => { button.disabled = true; });
  try {
    const result = await api("/api/v1/workspace/command", { method: "POST", action: true, body: JSON.stringify({ name }) });
    terminal.textContent = `Action: ${result.display_name || metadata.display_name || name}\nKind: ${result.kind || metadata.kind || "configured"}\nPurpose: ${result.purpose || metadata.purpose || "Configured command"}\nProof check: ${result.proof_check ? "yes" : "no"}\nRepository state: ${result.repository_state_hash || "unknown"}\n\n$ ${result.command}\n\n${result.stdout || ""}${result.stderr ? `\n${result.stderr}` : ""}\n\n[${result.status}] exit ${result.exit_code} · ${result.duration_ms}ms`;
    terminal.scrollTop = terminal.scrollHeight; toast(`${result.display_name || name} ${result.status.toLowerCase()} in ${result.duration_ms}ms`, result.status !== "PASS"); await Promise.all([loadActivity(), loadProof(), loadGit()]);
  } catch (error) { terminal.textContent = error.message; toast(error.message, true); }
  finally { qsa("[data-command]").forEach((button) => { button.disabled = !state.bootstrap.actions_enabled || !state.snapshot.commands?.[button.dataset.command]; }); }
}


async function loadProof() {
  const root = $("proof-content");
  try {
    const report = await api("/api/v1/proof"); root.className = "panel-scroll"; root.replaceChildren();
    const score = Number(report.score || 0); const status = report.final_status || "NOT_RUN"; const checks = Array.isArray(report.checks) ? report.checks : [];
    const canonical = (value) => ["SKIP", "SKIPPED", "NOT_APPLICABLE"].includes(String(value || "").toUpperCase()) ? "NOT_APPLICABLE" : String(value || "UNKNOWN").toUpperCase();
    const passed = checks.filter((item) => canonical(item.status) === "PASS").length; const failed = checks.filter((item) => canonical(item.status) === "FAIL").length; const notApplicable = checks.filter((item) => canonical(item.status) === "NOT_APPLICABLE").length;
    const grid = node("div", "metric-grid"); [["Proof score", `${score}/100`], ["Applicable checks", `${passed}/${Math.max(0, checks.length - notApplicable)}`], ["Failed", failed], ["Not applicable", notApplicable]].forEach(([label, value]) => { const metric = node("div", "metric"); metric.append(node("span", "", label), node("strong", "", value)); grid.append(metric); }); root.append(grid);
    root.append(node("div", `status-badge ${status === "VERIFIED" ? "good" : (status === "NOT_RUN" ? "" : "warn")}`, status));
    const provenance = node("div", "proof-provenance");
    const proofState = report.project_state_hash || report.knowledge_graph?.state_hash || report.repository_state_hash || report.state_hash || "not recorded";
    const workspaceState = state.snapshot?.repository_state_hash || "not recorded";
    [["Proof project state", proofState], ["Current workspace fingerprint", workspaceState], ["Started", report.started_at ? new Date(report.started_at).toLocaleString() : "—"], ["Finished", report.finished_at ? new Date(report.finished_at).toLocaleString() : "—"], ["Sandbox", `${report.sandbox || "unknown"}${report.sandbox_fallback_reason ? ` · ${report.sandbox_fallback_reason}` : ""}`], ["Mutations", `${(report.mutations || []).filter((item) => item.survived === false).length} killed · ${(report.mutations || []).filter((item) => item.survived === true).length} survived`], ["Security", `${(report.security_findings || []).filter((item) => String(item.level).toUpperCase() === "HIGH").length} high findings`]].forEach(([label, value]) => { const row = node("div", "truth-row"); row.append(node("span", "", label), node("span", "", value)); provenance.append(row); });
    const evidence = node("button", "button secondary proof-evidence-link", "Open complete evidence"); evidence.type = "button"; evidence.addEventListener("click", () => { window.location.href = "/#evidence"; }); provenance.append(evidence); root.append(provenance);
    if (checks.length) { const list = node("div", "event-list"); checks.slice(0, 20).forEach((item) => { const card = node("div", "event-item"); const statusLabel = canonical(item.status); card.append(node("strong", "", `${item.name || item.id || "Check"} · ${statusLabel}`)); card.append(node("p", "", item.command || item.message || (statusLabel === "NOT_APPLICABLE" ? "No command configured; excluded from applicable checks." : ""))); list.append(card); }); root.append(list); }
  } catch (error) { root.className = "panel-scroll empty-panel"; root.textContent = error.message; }
}


function showActivityDetail(item) {
  $("activity-detail-title").textContent = `${item.event || "Workspace event"} · ${item.event_id || "unidentified"}`;
  const root = $("activity-detail"); root.replaceChildren();
  const fields = [["Event ID", item.event_id], ["Actor", item.actor || "system"], ["Path", item.path || "workspace"], ["Created", item.created_at ? new Date(item.created_at).toLocaleString() : "—"], ["Command", item.command || "—"], ["Status", item.status || "—"], ["Duration", item.duration_ms != null ? `${item.duration_ms} ms` : "—"], ["Exit code", item.exit_code ?? "—"], ["Repository state", item.repository_state_hash || "—"], ["Before SHA", item.before_sha256 || "—"], ["After SHA", item.after_sha256 || "—"], ["Git tracking", item.git_tracking ? JSON.stringify(item.git_tracking) : "—"], ["Detail", item.detail || "—"]];
  fields.forEach(([label, value]) => { const card = node("div", "metric"); card.append(node("span", "", label), node("strong", "", value)); root.append(card); });
  const output = $("activity-detail-output"); const raw = item.stdout || item.stderr || ""; output.textContent = raw; output.classList.toggle("hidden", !raw); $("activity-dialog").showModal();
}

async function loadActivity() {
  const root = $("activity-content");
  try {
    const data = await api("/api/v1/workspace/events"); const items = [...(data.items || [])].reverse(); root.replaceChildren(); root.className = "panel-scroll";
    if (!items.length) { root.className = "panel-scroll empty-panel"; root.textContent = "No workspace activity recorded."; return; }
    const list = node("div", "event-list");
    items.forEach((item) => { const card = node("button", "event-item event-button"); card.type = "button"; card.append(node("strong", "", item.event)); card.append(node("p", "", `${item.path || "workspace"} · ${item.actor || "system"}`)); card.append(node("p", "", `${item.status || ""}${item.duration_ms != null ? ` ${item.duration_ms}ms` : ""}${item.created_at ? ` · ${new Date(item.created_at).toLocaleString()}` : ""}`)); card.addEventListener("click", () => showActivityDetail(item)); list.append(card); }); root.append(list);
  } catch (error) { root.className = "panel-scroll empty-panel"; root.textContent = error.message; }
}


async function loadGit() {
  const root = $("git-content");
  try {
    const git = await api("/api/v1/workspace/git"); root.replaceChildren(); root.className = "panel-scroll";
    if (!git.available) { $("branch-chip").textContent = "Git unavailable"; root.className = "panel-scroll empty-panel"; root.textContent = git.reason || "Git is unavailable."; return; }
    $("branch-chip").textContent = `${git.branch}${git.dirty ? ` · ${git.items.length} changed` : " · clean"}`;
    const ahead = git.ahead_behind_available ? git.ahead : "N/A"; const behind = git.ahead_behind_available ? git.behind : "N/A";
    const grid = node("div", "metric-grid"); [["Branch", git.branch], ["Commit", git.commit], ["Ahead", ahead], ["Behind", behind], ["Staged", git.summary?.staged || 0], ["Untracked", git.summary?.untracked || 0]].forEach(([label, value]) => { const metric = node("div", "metric"); metric.append(node("span", "", label), node("strong", "", value)); grid.append(metric); }); root.append(grid);
    root.append(node("div", `status-badge ${git.dirty ? "warn" : "good"}`, git.dirty ? "WORKTREE MODIFIED" : "WORKTREE CLEAN"));
    root.append(node("p", "git-truth", `Read-only Git inspection · upstream ${git.upstream || "not configured; ahead/behind unavailable"} · commit/push disabled`));
    const diffOutput = node("pre", "git-diff-output", "Select a changed file to inspect its diff.");
    if (git.items.length) { const list = node("div", "git-list"); git.items.forEach((item) => { const card = node("button", "git-item"); card.type = "button"; const scope = item.untracked ? "untracked" : [item.staged ? "staged" : "", item.unstaged ? "unstaged" : ""].filter(Boolean).join(" + "); card.append(node("strong", "", `${item.status}  ${item.path}`), node("p", "", scope || "changed")); card.addEventListener("click", async () => { try { const staged = item.staged && !item.unstaged; const data = await api(`/api/v1/workspace/git/diff?path=${encodeURIComponent(item.path)}&staged=${staged}`); diffOutput.textContent = data.diff || "No diff available."; } catch (error) { diffOutput.textContent = error.message; } }); list.append(card); }); root.append(list); }
    root.append(diffOutput);
    if (git.commits?.length) { const heading = node("h3", "git-history-title", "Recent commits"); const history = node("div", "event-list"); git.commits.forEach((item) => { const card = node("div", "event-item"); card.append(node("strong", "", `${item.commit} · ${item.subject}`), node("p", "", `${item.author} · ${new Date(item.created_at).toLocaleString()}`)); history.append(card); }); root.append(heading, history); }
  } catch (error) { root.className = "panel-scroll empty-panel"; root.textContent = error.message; }
}


function paletteCommands() {
  const tab = currentTab(); const commands = [];
  if (tab?.dirty) commands.push({ icon: "S", title: "Review diff and save current file", detail: "⌘S · governed atomic save", action: reviewDiff });
  if (tab) commands.push({ icon: "R", title: "Reload current file", detail: "Repository version", action: reloadActive });
  Object.entries(state.snapshot?.commands || {}).filter(([, command]) => Boolean(command)).forEach(([name, command]) => {
    const metadata = state.snapshot?.command_metadata?.[name] || {}; commands.push({ icon: name[0].toUpperCase(), title: `Run ${metadata.display_name || name}`, detail: `${metadata.purpose || "Configured command"} · ${command}`, action: () => runCommand(name) });
  });
  commands.push({ icon: "P", title: "Show Proof panel", detail: "Engineering panel", action: () => switchPanel("proof") }, { icon: "A", title: "Show Activity panel", detail: "Engineering panel", action: () => switchPanel("activity") }, { icon: "G", title: "Show Git panel", detail: "Engineering panel", action: () => switchPanel("git") }, { icon: "↻", title: "Refresh repository explorer", detail: "Workspace", action: loadTree });
  const files = state.flatFiles.map((item) => ({ icon: fileIcon(item.path), title: item.path, detail: languageLabel(item.language), action: () => openFile(item.path) })); return [...commands, ...files];
}


function renderPalette() {
  const term = $("palette-input").value.trim().toLowerCase();
  const all = paletteCommands();
  state.paletteItems = all.filter((item) => !term || `${item.title} ${item.detail}`.toLowerCase().includes(term)).slice(0, 80);
  state.paletteIndex = Math.min(state.paletteIndex, Math.max(0, state.paletteItems.length - 1));
  const root = $("palette-results");
  root.replaceChildren();
  state.paletteItems.forEach((item, index) => {
    const button = node("button", `palette-item${index === state.paletteIndex ? " selected" : ""}`);
    button.type = "button";
    button.append(node("span", "", item.icon), node("strong", "", item.title), node("small", "", item.detail));
    button.addEventListener("mouseenter", () => { state.paletteIndex = index; renderPalette(); });
    button.addEventListener("click", () => executePaletteItem(index));
    root.append(button);
  });
  qs(".palette-item.selected")?.scrollIntoView({ block: "nearest" });
}

function openPalette() {
  state.paletteIndex = 0;
  $("palette-input").value = "";
  renderPalette();
  $("command-palette").showModal();
  requestAnimationFrame(() => $("palette-input").focus());
}

function executePaletteItem(index = state.paletteIndex) {
  const item = state.paletteItems[index];
  if (!item) return;
  $("command-palette").close();
  Promise.resolve(item.action()).catch((error) => toast(error.message, true));
}

function workspaceStorageKey(kind) {
  const repo = state.snapshot?.repo || window.location.pathname;
  return `basalt-workspace:${kind}:${repo}`;
}

function captureActiveTabView() {
  const tabState = currentTab();
  const code = $("code");
  if (!tabState || !code || $("editor-frame").classList.contains("hidden")) return;
  tabState.cursorStart = code.selectionStart;
  tabState.cursorEnd = code.selectionEnd;
  tabState.scrollTop = code.scrollTop;
  tabState.scrollLeft = code.scrollLeft;
}

function persistWorkspaceState() {
  if (state.restoring || !state.snapshot) return;
  try {
    captureActiveTabView();
    let budget = 900000;
    const tabs = state.order.map((path) => {
      const tab = state.tabs.get(path);
      if (!tab) return null;
      const record = {
        path,
        dirty: Boolean(tab.dirty),
        sha256: tab.sha256,
        cursorStart: Number(tab.cursorStart || 0),
        cursorEnd: Number(tab.cursorEnd || tab.cursorStart || 0),
        scrollTop: Number(tab.scrollTop || 0),
        scrollLeft: Number(tab.scrollLeft || 0),
      };
      if (tab.dirty) {
        const size = new TextEncoder().encode(`${tab.content || ""}${tab.originalContent || ""}`).length;
        if (size <= budget && size <= 400000) {
          record.content = tab.content;
          record.originalContent = tab.originalContent;
          budget -= size;
        } else {
          record.dirty = false;
        }
      }
      return record;
    }).filter(Boolean);
    sessionStorage.setItem(workspaceStorageKey("session"), JSON.stringify({ tabs, activePath: state.activePath }));
    localStorage.setItem(workspaceStorageKey("ui"), JSON.stringify({
      activePanel: state.activePanel,
      searchQuery: state.searchQuery,
    }));
  } catch (error) {
    console.warn("Workspace continuity state could not be saved", error);
  }
}

async function restoreWorkspaceState() {
  state.restoring = true;
  try {
    const ui = JSON.parse(localStorage.getItem(workspaceStorageKey("ui")) || "{}");
    if (["build", "proof", "activity", "git"].includes(ui.activePanel)) state.activePanel = ui.activePanel;
    state.searchQuery = typeof ui.searchQuery === "string" ? ui.searchQuery : "";

    const saved = JSON.parse(sessionStorage.getItem(workspaceStorageKey("session")) || "{}");
    const records = Array.isArray(saved.tabs) ? saved.tabs.slice(0, 24) : [];
    for (const record of records) {
      if (!record?.path || !state.flatFiles.some((item) => item.path === record.path)) continue;
      try {
        const file = await api(`/api/v1/workspace/file?path=${encodeURIComponent(record.path)}`);
        const unchanged = !record.sha256 || record.sha256 === file.sha256;
        const restoreDirty = Boolean(record.dirty && typeof record.content === "string" && typeof record.originalContent === "string");
        const tab = {
          ...file,
          originalContent: restoreDirty ? record.originalContent : file.content,
          content: restoreDirty ? record.content : file.content,
          dirty: restoreDirty && record.content !== record.originalContent,
          cursorStart: record.cursorStart || 0,
          cursorEnd: record.cursorEnd || record.cursorStart || 0,
          scrollTop: record.scrollTop || 0,
          scrollLeft: record.scrollLeft || 0,
        };
        if (restoreDirty && !unchanged) {
          tab.sha256 = record.sha256;
          tab.stale = true;
        }
        state.tabs.set(record.path, tab);
        state.order.push(record.path);
      } catch (_) {
        // A deleted or protected file is intentionally skipped.
      }
    }
    state.activePath = state.tabs.has(saved.activePath) ? saved.activePath : (state.order.at(-1) || "");
    switchPanel(state.activePanel);
    if (state.searchQuery) {
      $("file-search").value = state.searchQuery;
      await searchRepository(state.searchQuery);
    }
  } catch (error) {
    console.warn("Workspace continuity state could not be restored", error);
  } finally {
    state.restoring = false;
  }
}

function installResizer(handleId, side) {
  const handle = $(handleId);
  handle.addEventListener("pointerdown", (event) => {
    handle.setPointerCapture(event.pointerId);
    handle.classList.add("dragging");
    const startX = event.clientX;
    const root = document.documentElement;
    const current = parseFloat(getComputedStyle(root).getPropertyValue(side === "left" ? "--left-width" : "--right-width"));
    const move = (moveEvent) => {
      const delta = moveEvent.clientX - startX;
      const value = side === "left" ? current + delta : current - delta;
      const bounded = Math.max(side === "left" ? 210 : 285, Math.min(side === "left" ? 460 : 560, value));
      root.style.setProperty(side === "left" ? "--left-width" : "--right-width", `${bounded}px`);
      localStorage.setItem(`basalt-${side}-width`, String(bounded));
    };
    const up = () => {
      handle.classList.remove("dragging");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      persistWorkspaceState();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
}

function restorePanelWidths() {
  const left = Number(localStorage.getItem("basalt-left-width"));
  const right = Number(localStorage.getItem("basalt-right-width"));
  if (left) document.documentElement.style.setProperty("--left-width", `${left}px`);
  if (right) document.documentElement.style.setProperty("--right-width", `${right}px`);
}

function installKeyboardShortcuts() {
  window.addEventListener("keydown", (event) => {
    const command = event.metaKey || event.ctrlKey;
    if (command && ["k", "p"].includes(event.key.toLowerCase())) {
      event.preventDefault(); openPalette(); return;
    }
    if (command && event.shiftKey && event.key.toLowerCase() === "f") {
      event.preventDefault(); $("file-search").focus(); return;
    }
    if (command && event.key.toLowerCase() === "s") {
      event.preventDefault(); if (currentTab()?.dirty) reviewDiff(); return;
    }
    if (event.key === "Escape" && $("command-palette").open) $("command-palette").close();
  });
  $("code").addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    event.preventDefault();
    const code = $("code");
    const start = code.selectionStart;
    const end = code.selectionEnd;
    code.setRangeText("  ", start, end, "end");
    onEditorInput();
  });
}

function wireUi() {
  $("code").addEventListener("input", onEditorInput);
  $("code").addEventListener("scroll", () => { syncEditorScroll(); captureActiveTabView(); persistWorkspaceState(); });
  $("code").addEventListener("keyup", () => { updateCursorPosition(); captureActiveTabView(); persistWorkspaceState(); });
  $("code").addEventListener("click", () => { updateCursorPosition(); captureActiveTabView(); persistWorkspaceState(); });
  $("save").addEventListener("click", reviewDiff);
  $("review-diff").addEventListener("click", reviewDiff);
  $("reload-file").addEventListener("click", () => reloadActive(false));
  $("confirm-save").addEventListener("click", persistSave);
  $("reload-conflict").addEventListener("click", async () => { $("diff-dialog").close(); await reloadActive(true); });
  $("diagnostics-summary").addEventListener("click", showDiagnostics);
  $("refresh-tree").addEventListener("click", loadTree);
  $("refresh-proof").addEventListener("click", loadProof);
  $("refresh-activity").addEventListener("click", loadActivity);
  $("refresh-git").addEventListener("click", loadGit);
  $("clear-console").addEventListener("click", () => { $("terminal").textContent = "Console cleared."; });
  $("copy-console").addEventListener("click", async () => {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard access is unavailable.");
      await navigator.clipboard.writeText($("terminal").textContent);
      toast("Console output copied.");
    } catch (error) {
      toast(error.message, true);
    }
  });
  $("palette-button").addEventListener("click", openPalette);
  qsa(".panel-tab").forEach((button) => button.addEventListener("click", () => switchPanel(button.dataset.panel)));
  qsa("[data-command]").forEach((button) => button.addEventListener("click", () => runCommand(button.dataset.command)));

  let searchTimer;
  $("file-search").addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => searchRepository(event.target.value), 180);
  });

  $("palette-input").addEventListener("input", () => { state.paletteIndex = 0; renderPalette(); });
  $("palette-input").addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") { event.preventDefault(); state.paletteIndex = Math.min(state.paletteItems.length - 1, state.paletteIndex + 1); renderPalette(); }
    if (event.key === "ArrowUp") { event.preventDefault(); state.paletteIndex = Math.max(0, state.paletteIndex - 1); renderPalette(); }
    if (event.key === "Enter") { event.preventDefault(); executePaletteItem(); }
  });

  installResizer("left-resizer", "left");
  installResizer("right-resizer", "right");
  installKeyboardShortcuts();
}

async function initialize() {
  restorePanelWidths();
  wireUi();
  state.bootstrap = await api("/api/v1/bootstrap");
  state.snapshot = await api("/api/v1/workspace");
  $("workspace-title").textContent = state.snapshot.product;
  $("workspace-version").textContent = state.snapshot.version;
  $("truth").replaceChildren();
  $("truth").append(node("strong", "", state.snapshot.name));
  [["Project", state.snapshot.project_type], ["Editor", "Governed diff + atomic save"], ["Terminal", "Configured commands only"], ["Arbitrary shell", "Disabled"]].forEach(([label, value]) => {
    const row = node("div", "truth-row"); row.append(node("span", "", label), node("span", "", value)); $("truth").append(row);
  });
  qsa("[data-command]").forEach((button) => {
    const name = button.dataset.command; const command = state.snapshot.commands?.[name]; const metadata = state.snapshot.command_metadata?.[name] || {};
    button.disabled = !state.bootstrap.actions_enabled || !command; button.textContent = metadata.display_name || name[0].toUpperCase() + name.slice(1);
    button.title = command ? `${metadata.purpose || "Configured command"}: ${command}` : `No ${name} command configured`;
  });
  await Promise.all([loadTree(), loadGit(), loadProof(), loadActivity()]);
  await restoreWorkspaceState();
  updateEditorForActiveTab();
  if (currentTab()?.stale) toast("An unsaved tab was restored against a changed repository file. Review the conflict before saving.", true);
  window.addEventListener("beforeunload", persistWorkspaceState);
  persistWorkspaceState();
}

initialize().catch((error) => {
  setSaveState("Error", true);
  toast(error.message, true);
});
