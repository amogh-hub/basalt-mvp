from __future__ import annotations

import html
import json
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


def render_dashboard(report: ProofReport) -> str:
    data = json.dumps(report.to_dict(), indent=2)
    status = report.final_status.value
    status_color = _status_color(status)
    checks_rows = "".join(
        f"<tr><td>{_esc(c.name)}</td><td><span class='pill'>{_esc(c.status.value)}</span></td><td><code>{_esc(c.command or '—')}</code></td><td>{_esc(c.duration_ms)} ms</td><td>{_esc(c.message)}</td></tr>"
        for c in report.checks
    )
    mutation_rows = "".join(
        f"<tr><td>{_esc(m.file)}</td><td>{_esc(m.mutation_type)}<br><span class='mut'>{_esc(m.original)} → {_esc(m.replacement)}</span></td><td><span class='pill {'bad' if m.survived else 'good'}'>{'SURVIVED' if m.survived else 'KILLED'}</span></td><td>{_esc(m.message)}</td></tr>"
        for m in report.mutations
    ) or "<tr><td colspan='4'>No mutation results.</td></tr>"
    security_rows = "".join(
        f"<tr><td><span class='pill {'bad' if f.level.upper() == 'HIGH' else 'warn'}'>{_esc(f.level)}</span></td><td>{_esc(f.file)}:{_esc(f.line)}</td><td>{_esc(f.rule)}</td><td>{_esc(f.message)}</td></tr>"
        for f in report.security_findings
    ) or "<tr><td colspan='4'>No security, policy, dependency, or quality findings.</td></tr>"
    suggestion_cards = "".join(
        f"<div class='card'><h3>{_esc(s.title)}</h3><p><b>{_esc(s.severity)} · {_esc(s.category)}</b></p><p>{_esc(s.problem)}</p><p class='mut'>{_esc(s.recommended_change)}</p></div>"
        for s in report.fix_suggestions
    ) or "<div class='card'><h3>No patch suggestions</h3><p>This repo passed the configured MVP proof policy.</p></div>"
    symbols_preview = "".join(
        f"<li><code>{_esc(sym.kind)}</code> {_esc(sym.name)} <span>{_esc(sym.file)}:{_esc(sym.line)}</span></li>"
        for sym in report.knowledge_graph.symbols[:40]
    ) or "<li>No symbols found.</li>"
    artifacts = "".join(
        f"<li><b>{_esc(a.name)}</b>: <code>{_esc(a.path)}</code> — {_esc(a.purpose)}</li>"
        for a in report.artifacts
    ) or "<li>No extra artifacts.</li>"
    killed = sum(1 for m in report.mutations if not m.survived)
    survived = sum(1 for m in report.mutations if m.survived)
    total_checks = len(report.checks)
    passed_checks = sum(1 for c in report.checks if c.status.value == "PASS")
    configured_checks = [c for c in report.checks if c.status.value != "SKIPPED"]
    configured_total = len(configured_checks)
    configured_passed = sum(1 for c in configured_checks if c.status.value == "PASS")
    skipped_checks = total_checks - configured_total
    if configured_total:
        configured_summary = f"{configured_passed}/{configured_total}"
    else:
        configured_summary = "0/0"
    skipped_summary = f"{skipped_checks} skipped" if skipped_checks else "No skipped checks"

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Basalt Command Center — {html.escape(report.project_name)}</title>
<style>
:root {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #101828; background: #f5f7fb; }}
body {{ margin: 0; }}
.hero {{ background: radial-gradient(circle at top left, #344054 0, #101828 42%, #020617 100%); color: white; padding: 36px 40px; }}
.logo {{ letter-spacing: .18em; font-weight: 800; color: #98a2b3; font-size: 12px; }}
h1 {{ margin: 10px 0 8px; font-size: 40px; }}
.subtitle {{ color: #d0d5dd; font-size: 16px; max-width: 920px; }}
.status {{ display:inline-flex; align-items:center; gap:10px; margin-top:20px; padding: 10px 14px; border:1px solid rgba(255,255,255,.2); border-radius:999px; background:rgba(255,255,255,.08); }}
.dot {{ width:12px; height:12px; border-radius:99px; background:{status_color}; box-shadow:0 0 20px {status_color}; }}
main {{ padding: 28px 40px 60px; }}
.grid {{ display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:16px; margin-top:-40px; }}
.metric {{ background:white; border-radius:18px; padding:18px; box-shadow: 0 12px 30px rgba(16,24,40,.10); border:1px solid #eaecf0; }}
.metric .k {{ color:#667085; font-size:13px; }}
.metric .v {{ font-size:30px; font-weight:800; margin-top:8px; }}
.metric .sub {{ color:#667085; font-size:12px; margin-top:4px; }}
.section {{ background:white; border:1px solid #eaecf0; border-radius:18px; padding:24px; margin-top:22px; box-shadow:0 8px 24px rgba(16,24,40,.05); }}
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
  <div class="logo">BASALT COMMAND CENTER</div>
  <h1>{_esc(report.project_name)}</h1>
  <div class="subtitle">Proof-first repository verification. Basalt checks whether this repo is actually trustworthy enough to ship, not just whether it looks correct.</div>
  <div class="status"><span class="dot"></span><b>{_esc(status)}</b><span>Proof Score: {_esc(report.score)}/100</span></div>
</header>
<main>
  <div class="grid">
    <div class="metric"><div class="k">Final Verdict</div><div class="v" style="color:{status_color}">{_esc(status)}</div></div>
    <div class="metric"><div class="k">Proof Score</div><div class="v">{_esc(report.score)}/100</div></div>
    <div class="metric"><div class="k">Configured Checks Passed</div><div class="v">{configured_summary}</div><div class="sub">{skipped_summary}</div></div>
    <div class="metric"><div class="k">Risk Level</div><div class="v">{_risk_label(report)}</div></div>
  </div>
  <section class="section"><h2>Proof Checks</h2><table><thead><tr><th>Check</th><th>Status</th><th>Command</th><th>Duration</th><th>Message</th></tr></thead><tbody>{checks_rows}</tbody></table></section>
  <section class="section"><h2>Security, Policy, Dependency & Quality Findings</h2><table><thead><tr><th>Level</th><th>Location</th><th>Rule</th><th>Message</th></tr></thead><tbody>{security_rows}</tbody></table></section>
  <section class="section"><h2>Mutation Testing</h2><p class="mut">Killed: {killed} · Survived: {survived}</p><table><thead><tr><th>File</th><th>Mutation</th><th>Result</th><th>Meaning</th></tr></thead><tbody>{mutation_rows}</tbody></table></section>
  <section class="section"><h2>Patch Plan</h2><div class="cards">{suggestion_cards}</div></section>
  <section class="section"><h2>AST-Anchored Project Graph Preview</h2><p>{_esc(report.knowledge_graph.files_scanned)} files scanned, {_esc(len(report.knowledge_graph.symbols))} symbols found, {_esc(len(report.knowledge_graph.edges))} edges found, {_esc(len(report.knowledge_graph.test_files))} test files.</p><ul>{symbols_preview}</ul></section>
  <section class="section"><h2>Generated Artifacts</h2><ul>{artifacts}</ul><p class="mut">Use these artifacts as PR evidence and review material.</p></section>
  <section class="section"><h2>Raw JSON Evidence</h2><pre>{_esc(data)}</pre></section>
  <div class="footer">Basalt MVP v1.5 — Proof-to-PR final demo MVP. This is not the full autonomous Basalt product; it is the core proof engine.</div>
</main>
</body>
</html>"""


def write_dashboard(report: ProofReport, output_path: Path) -> None:
    output_path.write_text(render_dashboard(report), encoding="utf-8")
