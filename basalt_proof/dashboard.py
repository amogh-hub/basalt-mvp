from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path

from .models import ProofReport


def _esc(value: object) -> str:
    return html.escape(str(value))


def _status_color(status: str) -> str:
    return {
        "VERIFIED": "#12b76a",
        "WEAK_PROOF": "#f79009",
        "NOT_VERIFIED": "#f04438",
        "BLOCKED_BY_POLICY": "#b42318",
        "NEEDS_HUMAN_REVIEW": "#7a5af8",
    }.get(status, "#667085")


def _risk_label(report: ProofReport) -> str:
    if report.final_status.value == "BLOCKED_BY_POLICY":
        return "High"
    if report.final_status.value in {"WEAK_PROOF", "NOT_VERIFIED", "NEEDS_HUMAN_REVIEW"}:
        return "Medium"
    return "Low"


def _finding_class(level: str) -> str:
    return {"HIGH": "bad", "MEDIUM": "warn", "LOW": "muted"}.get(level.upper(), "muted")


def render_dashboard(report: ProofReport) -> str:
    data = json.dumps(report.to_dict(), indent=2)
    status = report.final_status.value
    status_color = _status_color(status)
    checks_rows = "".join(
        "<tr>"
        f"<td>{_esc(check.name)}</td>"
        f"<td><span class='pill'>{_esc(check.status.value)}</span></td>"
        f"<td>{_esc(check.sandbox)}</td>"
        f"<td><code>{_esc(check.command or '—')}</code></td>"
        f"<td>{_esc(check.duration_ms)} ms</td>"
        f"<td>{_esc(check.message)}</td>"
        "</tr>"
        for check in report.checks
    )
    mutation_rows = "".join(
        "<tr>"
        f"<td>{_esc(mutation.file)}:{_esc(mutation.line or '—')}</td>"
        f"<td>{_esc(mutation.mutation_type)}<br><span class='mut'>{_esc(mutation.original)} → {_esc(mutation.replacement)}</span></td>"
        f"<td><span class='pill {'bad' if mutation.survived else 'good'}'>{'SURVIVED' if mutation.survived else 'KILLED'}</span></td>"
        f"<td>{_esc(mutation.message)}</td>"
        "</tr>"
        for mutation in report.mutations
    ) or "<tr><td colspan='4'>No mutation results.</td></tr>"
    security_rows = "".join(
        "<tr>"
        f"<td><span class='pill {_finding_class(finding.level)}'>{_esc(finding.level)}</span></td>"
        f"<td>{_esc(finding.file)}:{_esc(finding.line)}</td>"
        f"<td>{_esc(finding.rule)}</td>"
        f"<td>{_esc(finding.message)}</td>"
        "</tr>"
        for finding in report.security_findings
    ) or "<tr><td colspan='4'>No security, policy, dependency, or quality findings.</td></tr>"
    suggestion_cards = "".join(
        "<div class='card'>"
        f"<h3>{_esc(suggestion.title)}</h3>"
        f"<p><b>{_esc(suggestion.severity)} · {_esc(suggestion.category)}</b></p>"
        f"<p>{_esc(suggestion.problem)}</p>"
        f"<p class='mut'>{_esc(suggestion.recommended_change)}</p>"
        "</div>"
        for suggestion in report.fix_suggestions
    ) or "<div class='card'><h3>No patch suggestions</h3><p>This repository passed the configured proof policy.</p></div>"
    symbols_preview = "".join(
        f"<li><code>{_esc(symbol.kind)}</code> {_esc(symbol.name)} <span>{_esc(symbol.file)}:{_esc(symbol.line)}</span></li>"
        for symbol in report.knowledge_graph.symbols[:40]
    ) or "<li>No symbols found.</li>"
    artifacts = "".join(
        f"<li><b>{_esc(artifact.name)}</b>: <code>{_esc(artifact.path)}</code> — {_esc(artifact.purpose)}</li>"
        for artifact in report.artifacts
    ) or "<li>No extra artifacts.</li>"
    score_rows = "".join(
        f"<tr><td>{_esc(component.get('label', ''))}</td><td>{int(component.get('delta', 0)):+d}</td></tr>"
        for component in report.score_breakdown
    )
    killed = sum(1 for mutation in report.mutations if not mutation.survived)
    survived = sum(1 for mutation in report.mutations if mutation.survived)
    configured_checks = [check for check in report.checks if check.status.value != "SKIPPED"]
    configured_total = len(configured_checks)
    configured_passed = sum(1 for check in configured_checks if check.status.value == "PASS")
    skipped_checks = len(report.checks) - configured_total
    configured_summary = f"{configured_passed}/{configured_total}" if configured_total else "0/0"
    skipped_summary = f"{skipped_checks} skipped" if skipped_checks else "No skipped checks"
    levels = Counter(finding.level.upper() for finding in report.security_findings)
    language_summary = ", ".join(
        f"{name}: {count}" for name, count in sorted(report.knowledge_graph.languages.items())
    ) or "No source languages detected"
    fallback_note = (
        f"<div class='notice'>Docker was requested but unavailable. Basalt used an isolated temporary workspace instead: {_esc(report.sandbox_fallback_reason)}</div>"
        if report.sandbox_fallback_reason
        else ""
    )

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Basalt Command Center — {html.escape(report.project_name)}</title>
<style>
:root {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #101828; background: #f5f7fb; }}
body {{ margin: 0; }}
.hero {{ background: radial-gradient(circle at top left, #344054 0, #101828 42%, #020617 100%); color: white; padding: 36px 40px 70px; }}
.logo {{ letter-spacing: .18em; font-weight: 800; color: #98a2b3; font-size: 12px; }}
h1 {{ margin: 10px 0 8px; font-size: 40px; }}
.subtitle {{ color: #d0d5dd; font-size: 16px; max-width: 920px; }}
.status {{ display:inline-flex; align-items:center; gap:10px; margin-top:20px; padding: 10px 14px; border:1px solid rgba(255,255,255,.2); border-radius:999px; background:rgba(255,255,255,.08); }}
.dot {{ width:12px; height:12px; border-radius:99px; background:{status_color}; box-shadow:0 0 20px {status_color}; }}
main {{ padding: 0 40px 60px; }}
.grid {{ display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:16px; margin-top:-40px; }}
.metric {{ background:white; border-radius:18px; padding:18px; box-shadow: 0 12px 30px rgba(16,24,40,.10); border:1px solid #eaecf0; }}
.metric .k {{ color:#667085; font-size:13px; }}
.metric .v {{ font-size:30px; font-weight:800; margin-top:8px; }}
.metric .sub {{ color:#667085; font-size:12px; margin-top:4px; }}
.section {{ background:white; border:1px solid #eaecf0; border-radius:18px; padding:24px; margin-top:22px; box-shadow:0 8px 24px rgba(16,24,40,.05); }}
.notice {{ background:#fffaeb; border:1px solid #fedf89; color:#7a2e0e; border-radius:14px; padding:14px 16px; margin-top:22px; }}
h2 {{ margin:0 0 14px; }}
table {{ width:100%; border-collapse: collapse; font-size:14px; }}
th, td {{ border-bottom:1px solid #eaecf0; text-align:left; padding:12px 10px; vertical-align:top; }}
th {{ color:#475467; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
code, pre {{ background:#f2f4f7; border-radius:8px; padding:2px 6px; }}
pre {{ padding:18px; overflow:auto; max-height:420px; }}
.pill {{ display:inline-block; border-radius:999px; padding:4px 9px; background:#eef2ff; color:#3538cd; font-size:12px; font-weight:700; }}
.pill.good {{ background:#ecfdf3; color:#027a48; }}
.pill.warn {{ background:#fffaeb; color:#b54708; }}
.pill.bad {{ background:#fef3f2; color:#b42318; }}
.pill.muted {{ background:#f2f4f7; color:#475467; }}
.cards {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap:14px; }}
.card {{ border:1px solid #eaecf0; border-radius:16px; padding:16px; background:#fcfcfd; }}
.card h3 {{ margin:0 0 6px; }}
.mut {{ color:#667085; font-size:13px; }}
ul {{ line-height:1.9; }}
.footer {{ margin-top:28px; color:#667085; font-size:13px; }}
@media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr 1fr; }} main,.hero{{padding-left:20px;padding-right:20px;}} }}
@media (max-width: 560px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<header class="hero">
  <div class="logo">BASALT v2.5 PRIVATE BETA FULL BUILD SYSTEM</div>
  <h1>{_esc(report.project_name)}</h1>
  <div class="subtitle">Proof-first repository verification. Basalt measures whether this repository has enough evidence, security discipline, and test strength to be trusted.</div>
  <div class="status"><span class="dot"></span><b>{_esc(status)}</b><span>Proof Score: {_esc(report.score)}/100</span></div>
</header>
<main>
  <div class="grid">
    <div class="metric"><div class="k">Final Verdict</div><div class="v" style="color:{status_color}">{_esc(status)}</div></div>
    <div class="metric"><div class="k">Proof Score</div><div class="v">{_esc(report.score)}/100</div></div>
    <div class="metric"><div class="k">Configured Checks Passed</div><div class="v">{configured_summary}</div><div class="sub">{skipped_summary}</div></div>
    <div class="metric"><div class="k">Sandbox</div><div class="v">{_esc(report.sandbox)}</div><div class="sub">Requested: {_esc(report.sandbox_requested)}</div></div>
  </div>
  {fallback_note}
  <section class="section"><h2>Proof Summary</h2><div class="cards">
    <div class="card"><h3>Risk</h3><p>{_risk_label(report)}</p></div>
    <div class="card"><h3>Mutation Strength</h3><p>Killed {killed} · Survived {survived}</p></div>
    <div class="card"><h3>Findings</h3><p>High {levels.get('HIGH', 0)} · Medium {levels.get('MEDIUM', 0)} · Low {levels.get('LOW', 0)}</p></div>
    <div class="card"><h3>Languages</h3><p>{_esc(language_summary)}</p></div>
  </div></section>
  <section class="section"><h2>Proof Checks</h2><table><thead><tr><th>Check</th><th>Status</th><th>Sandbox</th><th>Command</th><th>Duration</th><th>Message</th></tr></thead><tbody>{checks_rows}</tbody></table></section>
  <section class="section"><h2>Proof Score Breakdown</h2><table><thead><tr><th>Component</th><th>Delta</th></tr></thead><tbody>{score_rows}<tr><td><b>Final score</b></td><td><b>{report.score}/100</b></td></tr></tbody></table></section>
  <section class="section"><h2>Security, Policy, Dependency & Quality Findings</h2><table><thead><tr><th>Level</th><th>Location</th><th>Rule</th><th>Message</th></tr></thead><tbody>{security_rows}</tbody></table></section>
  <section class="section"><h2>Mutation Testing</h2><p class="mut">Killed: {killed} · Survived: {survived}</p><table><thead><tr><th>File</th><th>Mutation</th><th>Result</th><th>Meaning</th></tr></thead><tbody>{mutation_rows}</tbody></table></section>
  <section class="section"><h2>Patch Plan</h2><div class="cards">{suggestion_cards}</div></section>
  <section class="section"><h2>AST-Anchored Project Knowledge Graph</h2>
    <div class="cards">
      <div class="card"><h3>Project State</h3><p><code>{_esc(report.knowledge_graph.state_hash[:16])}</code></p><p class="mut">Fresh: {_esc(report.knowledge_graph.fresh)} · Parser: {_esc(report.knowledge_graph.parser_version)}</p></div>
      <div class="card"><h3>Code Truth</h3><p>{_esc(report.knowledge_graph.files_scanned)} files · {_esc(len(report.knowledge_graph.symbols))} symbols · {_esc(len(report.knowledge_graph.edges))} edges</p></div>
      <div class="card"><h3>Proof Mapping</h3><p>{_esc(len(report.knowledge_graph.test_files))} tests · {_esc(len(report.knowledge_graph.test_mappings))} file-to-test mappings</p></div>
      <div class="card"><h3>Product Mapping</h3><p>{_esc(len(report.knowledge_graph.features))} features · {_esc(len(report.knowledge_graph.routes))} routes · {_esc(len(report.knowledge_graph.schemas))} schemas</p></div>
    </div>
    <ul>{symbols_preview}</ul>
  </section>
  <section class="section"><h2>Generated Artifacts</h2><ul>{artifacts}</ul><p class="mut">Attach these artifacts to pull requests as proof evidence.</p></section>
  <section class="section"><h2>Raw JSON Evidence</h2><pre>{_esc(data)}</pre></section>
  <div class="footer">Basalt v2.5.0-beta.3 — Private Beta Full Build System. Verified software, not vibes.</div>
</main>
</body>
</html>"""


def write_dashboard(report: ProofReport, output_path: Path) -> None:
    output_path.write_text(render_dashboard(report), encoding="utf-8")
