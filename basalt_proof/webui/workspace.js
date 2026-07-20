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
  renderTabs();
  markActiveTreePath();
  if (!tabState) {
    $("empty-editor").classList.remove("hidden");
    $("editor-frame").classList.add("hidden");
    $("breadcrumbs").textContent = "Select a file from the repository";
    $("footer-path").textContent = "No file selected";
    $("footer-language").textContent = "Plain Text";
    $("diagnostics-label").textContent = "No file selected";
    $("diagnostics-summary").disabled = true;
    updateActionState();
    return;
  }
  $("empty-editor").classList.add("hidden");
  $("editor-frame").classList.remove("hidden");
  $("code").disabled = false;
  $("code").value = tabState.content;
  $("breadcrumbs").textContent = tabState.path.split("/").join("  /  ");
  $("footer-path").textContent = tabState.path;
  $("footer-language").textContent = languageLabel(tabState.language);
  $("file-meta").textContent = `${tabState.line_count || Math.max(1, tabState.content.split("\n").length)} lines · ${tabState.size_bytes} bytes · ${tabState.sha256.slice(0, 12)}`;
  renderLineNumbers(tabState.content);
  renderHighlight(tabState.content, tabState.language);
  syncEditorScroll();
  renderDiagnosticsSummary(state.diagnostics.get(tabState.path));
  updateCursorPosition();
  updateActionState();
}

function activateTab(path) {
  if (!state.tabs.has(path)) return;
  state.activePath = path;
  updateEditorForActiveTab();
  scheduleDiagnostics();
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

function goToLine(line) {
  const code = $("code");
  const lines = code.value.split("\n");
  const target = Math.max(1, Math.min(Number(line) || 1, lines.length));
  const position = lines.slice(0, target - 1).reduce((sum, item) => sum + item.length + 1, 0);
  code.focus();
  code.setSelectionRange(position, position);
  const lineHeight = parseFloat(getComputedStyle(code).lineHeight) || 20.8;
  code.scrollTop = Math.max(0, (target - 4) * lineHeight);
  syncEditorScroll();
  updateCursorPosition();
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
  const tabState = currentTab();
  if (!tabState) return;
  const result = state.diagnostics.get(tabState.path);
  const root = $("diagnostics-list");
  root.replaceChildren();
  if (!result || !result.items.length) {
    root.append(node("div", "clean-diagnostics", "No diagnostics for the current file."));
  } else {
    const list = node("div", "diagnostic-items");
    result.items.forEach((item) => {
      const card = node("button", "diagnostic-item");
      card.type = "button";
      card.append(node("strong", "", `${item.severity} · ${item.code || "DIAGNOSTIC"}`));
      card.append(node("p", "", `Line ${item.line}, column ${item.column} — ${item.message}`));
      card.addEventListener("click", () => { $("diagnostics-dialog").close(); goToLine(item.line); });
      list.append(card);
    });
    root.append(list);
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
  const term = query.trim();
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
  qsa(".panel-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.panel === name));
  qsa(".panel-view").forEach((panel) => panel.classList.toggle("active", panel.id === `panel-${name}`));
  if (name === "proof") loadProof();
  if (name === "activity") loadActivity();
  if (name === "git") loadGit();
}

async function runCommand(name) {
  const terminal = $("terminal");
  switchPanel("build");
  terminal.textContent = `Running ${name}…`;
  qsa("[data-command]").forEach((button) => { button.disabled = true; });
  try {
    const result = await api("/api/v1/workspace/command", {
      method: "POST",
      action: true,
      body: JSON.stringify({ name }),
    });
    terminal.textContent = `$ ${result.command}\n\n${result.stdout || ""}${result.stderr ? `\n${result.stderr}` : ""}\n\n[${result.status}] ${result.duration_ms}ms`;
    terminal.scrollTop = terminal.scrollHeight;
    toast(`${name} ${result.status.toLowerCase()} in ${result.duration_ms}ms`, result.status !== "PASS");
    await Promise.all([loadActivity(), loadProof()]);
  } catch (error) {
    terminal.textContent = error.message;
    toast(error.message, true);
  } finally {
    qsa("[data-command]").forEach((button) => {
      button.disabled = !state.bootstrap.actions_enabled || !state.snapshot.commands?.[button.dataset.command];
    });
  }
}

async function loadProof() {
  const root = $("proof-content");
  try {
    const report = await api("/api/v1/proof");
    root.className = "panel-scroll";
    root.replaceChildren();
    const score = Number(report.score || 0);
    const status = report.final_status || "NOT_RUN";
    const checks = Array.isArray(report.checks) ? report.checks : [];
    const passed = checks.filter((item) => item.status === "PASS").length;
    const failed = checks.filter((item) => item.status === "FAIL").length;
    const skipped = checks.filter((item) => item.status === "SKIP").length;
    const grid = node("div", "metric-grid");
    [["Proof score", `${score}/100`], ["Checks", `${passed}/${checks.length || 0}`], ["Failed", failed], ["Skipped", skipped]].forEach(([label, value]) => {
      const metric = node("div", "metric");
      metric.append(node("span", "", label), node("strong", "", value));
      grid.append(metric);
    });
    root.append(grid);
    const badgeClass = status === "VERIFIED" ? "good" : (status === "NOT_RUN" ? "" : "warn");
    root.append(node("div", `status-badge ${badgeClass}`, status));
    if (checks.length) {
      const list = node("div", "event-list");
      checks.slice(0, 20).forEach((item) => {
        const card = node("div", "event-item");
        card.append(node("strong", "", `${item.name || item.id || "Check"} · ${item.status || "UNKNOWN"}`));
        card.append(node("p", "", item.command || item.message || ""));
        list.append(card);
      });
      root.append(list);
    }
  } catch (error) {
    root.className = "panel-scroll empty-panel";
    root.textContent = error.message;
  }
}

async function loadActivity() {
  const root = $("activity-content");
  try {
    const data = await api("/api/v1/workspace/events");
    const items = [...(data.items || [])].reverse();
    root.replaceChildren();
    root.className = "panel-scroll";
    if (!items.length) {
      root.className = "panel-scroll empty-panel";
      root.textContent = "No workspace activity recorded.";
      return;
    }
    const list = node("div", "event-list");
    items.forEach((item) => {
      const card = node("div", "event-item");
      card.append(node("strong", "", item.event));
      card.append(node("p", "", `${item.path || "workspace"} · ${item.actor || "system"}`));
      card.append(node("p", "", `${item.detail || ""}${item.created_at ? ` · ${new Date(item.created_at).toLocaleString()}` : ""}`));
      list.append(card);
    });
    root.append(list);
  } catch (error) {
    root.className = "panel-scroll empty-panel";
    root.textContent = error.message;
  }
}

async function loadGit() {
  const root = $("git-content");
  try {
    const git = await api("/api/v1/workspace/git");
    root.replaceChildren();
    root.className = "panel-scroll";
    if (!git.available) {
      $("branch-chip").textContent = "Git unavailable";
      root.className = "panel-scroll empty-panel";
      root.textContent = git.reason || "Git is unavailable.";
      return;
    }
    $("branch-chip").textContent = `${git.branch}${git.dirty ? ` · ${git.items.length} changed` : " · clean"}`;
    const grid = node("div", "metric-grid");
    [["Branch", git.branch], ["Commit", git.commit], ["Ahead", git.ahead], ["Behind", git.behind]].forEach(([label, value]) => {
      const metric = node("div", "metric"); metric.append(node("span", "", label), node("strong", "", value)); grid.append(metric);
    });
    root.append(grid);
    const badge = node("div", `status-badge ${git.dirty ? "warn" : "good"}`, git.dirty ? "WORKTREE MODIFIED" : "WORKTREE CLEAN");
    root.append(badge);
    if (git.items.length) {
      const list = node("div", "git-list");
      git.items.forEach((item) => {
        const card = node("button", "git-item");
        card.type = "button";
        card.append(node("strong", "", `${item.status}  ${item.path}`));
        card.addEventListener("click", () => openFile(item.path.replace(/^.* -> /, "")));
        list.append(card);
      });
      root.append(list);
    }
  } catch (error) {
    root.className = "panel-scroll empty-panel";
    root.textContent = error.message;
  }
}

function paletteCommands() {
  const commands = [
    { icon: "S", title: "Review diff and save current file", detail: "⌘S", action: reviewDiff },
    { icon: "R", title: "Reload current file", detail: "Repository version", action: reloadActive },
    { icon: "T", title: "Run test command", detail: "Build control", action: () => runCommand("test") },
    { icon: "L", title: "Run lint command", detail: "Build control", action: () => runCommand("lint") },
    { icon: "B", title: "Run build command", detail: "Build control", action: () => runCommand("build") },
    { icon: "P", title: "Show Proof panel", detail: "Engineering panel", action: () => switchPanel("proof") },
    { icon: "A", title: "Show Activity panel", detail: "Engineering panel", action: () => switchPanel("activity") },
    { icon: "G", title: "Show Git panel", detail: "Engineering panel", action: () => switchPanel("git") },
    { icon: "↻", title: "Refresh repository explorer", detail: "Workspace", action: loadTree },
  ];
  const files = state.flatFiles.map((item) => ({
    icon: fileIcon(item.path), title: item.path, detail: languageLabel(item.language), action: () => openFile(item.path),
  }));
  return [...commands, ...files];
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
  $("code").addEventListener("scroll", syncEditorScroll);
  $("code").addEventListener("keyup", updateCursorPosition);
  $("code").addEventListener("click", updateCursorPosition);
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
    button.disabled = !state.bootstrap.actions_enabled || !state.snapshot.commands?.[button.dataset.command];
    button.title = state.snapshot.commands?.[button.dataset.command] || `No ${button.dataset.command} command configured`;
  });
  await Promise.all([loadTree(), loadGit(), loadProof(), loadActivity()]);
  updateEditorForActiveTab();
}

initialize().catch((error) => {
  setSaveState("Error", true);
  toast(error.message, true);
});
