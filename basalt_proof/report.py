from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .models import ProofReport


def write_json_report(report: ProofReport, output_path: Path) -> None:
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")


def _status_icon(status: str) -> str:
    return {
        "PASS": "✅",
        "FAIL": "❌",
        "WARNING": "⚠️",
        "SKIPPED": "⏭️",
        "WEAK_PROOF": "⚠️",
    }.get(status, "•")


def _acceptance_sentence(report: ProofReport) -> str:
    if report.final_status.value == "VERIFIED":
        return "Basalt marks this repository as **VERIFIED** based on configured proof checks."
    if report.final_status.value == "WEAK_PROOF":
        return "Basalt marks this repository as **WEAK_PROOF** because injected mutations survived. Strengthen tests before trusting the build."
    if report.final_status.value == "BLOCKED_BY_POLICY":
        return "Basalt marks this repository as **BLOCKED_BY_POLICY** due to a high-risk governance violation."
    if report.final_status.value == "NEEDS_HUMAN_REVIEW":
        return "Basalt marks this repository as **NEEDS_HUMAN_REVIEW** because proof passed but a risk or low proof score still requires approval."
    return "Basalt marks this repository as **NOT_VERIFIED**. Fix failed checks and rerun verification."


def render_markdown(report: ProofReport) -> str:
    lines: list[str] = []
    lines.append("# Basalt Proof Report")
    lines.append("")
    lines.append(f"**Basalt version:** `{report.basalt_version}`")
    lines.append(f"**Project:** {report.project_name}")
    lines.append(f"**Repository:** `{report.repo_path}`")
    lines.append(f"**Project Type:** `{report.project_type}`")
    lines.append(f"**Final Status:** `{report.final_status.value}`")
    lines.append(f"**Proof Score:** `{report.score}/100`")
    lines.append(f"**Sandbox requested:** `{report.sandbox_requested}`")
    lines.append(f"**Sandbox used:** `{report.sandbox}`")
    if report.sandbox_fallback_reason:
        lines.append(f"**Sandbox fallback:** {report.sandbox_fallback_reason}")
    lines.append("")
    lines.append("## Executive Verdict")
    lines.append("")
    lines.append(_acceptance_sentence(report))
    lines.append("")

    configured_checks = [check for check in report.checks if check.status.value != "SKIPPED"]
    configured_total = len(configured_checks)
    configured_passed = sum(1 for check in configured_checks if check.status.value == "PASS")
    skipped_checks = len(report.checks) - configured_total

    lines.append("## Checks")
    lines.append("")
    lines.append(f"**Configured checks passed:** `{configured_passed}/{configured_total}` · **Skipped:** `{skipped_checks}`")
    lines.append("")
    lines.append("| Check | Status | Sandbox | Command | Duration | Message |")
    lines.append("|---|---:|---|---|---:|---|")
    for check in report.checks:
        status = check.status.value
        command = f"`{check.command}`" if check.command else "—"
        message = (check.message or "").replace("|", "\\|")
        lines.append(
            f"| {check.name} | {_status_icon(status)} {status} | `{check.sandbox}` | {command} | {check.duration_ms} ms | {message} |"
        )
    lines.append("")

    lines.append("## Proof Score Breakdown")
    lines.append("")
    lines.append("| Component | Delta |")
    lines.append("|---|---:|")
    for component in report.score_breakdown:
        delta = int(component.get("delta", 0))
        sign = "+" if delta > 0 else ""
        lines.append(f"| {component.get('label', '')} | `{sign}{delta}` |")
    lines.append(f"| **Final score** | **`{report.score}/100`** |")
    lines.append("")

    levels = Counter(finding.level.upper() for finding in report.security_findings)
    lines.append("## Security, Policy, Dependency & Quality Findings")
    lines.append("")
    lines.append(
        f"**Summary:** HIGH `{levels.get('HIGH', 0)}` · MEDIUM `{levels.get('MEDIUM', 0)}` · LOW `{levels.get('LOW', 0)}`"
    )
    lines.append("")
    if report.security_findings:
        lines.append("| Level | File | Line | Rule | Message |")
        lines.append("|---|---|---:|---|---|")
        for finding in report.security_findings:
            message = finding.message.replace("|", "\\|")
            lines.append(f"| {finding.level} | `{finding.file}` | {finding.line} | {finding.rule} | {message} |")
    else:
        lines.append("No security, policy, dependency, or quality findings detected by the alpha scanner.")
    lines.append("")

    lines.append("## Mutation Testing")
    lines.append("")
    if report.mutations:
        lines.append("| File | Line | Mutation | Result | Meaning |")
        lines.append("|---|---:|---|---|---|")
        for mutation in report.mutations:
            result = "SURVIVED" if mutation.survived else "KILLED"
            icon = "⚠️" if mutation.survived else "✅"
            lines.append(
                f"| `{mutation.file}` | {mutation.line or '—'} | {mutation.mutation_type}: `{mutation.original}` → `{mutation.replacement}` | {icon} {result} | {mutation.message} |"
            )
    else:
        lines.append("Mutation testing did not run or no mutation candidates were found.")
    lines.append("")

    lines.append("## AST-Anchored Project Knowledge Graph")
    lines.append("")
    lines.append(f"- Graph version: `{report.knowledge_graph.graph_version}`")
    lines.append(f"- Parser version: `{report.knowledge_graph.parser_version}`")
    lines.append(f"- Project state hash: `{report.knowledge_graph.state_hash}`")
    lines.append(f"- Fresh: `{report.knowledge_graph.fresh}`")
    lines.append(f"- Files scanned: {report.knowledge_graph.files_scanned}")
    lines.append(f"- Symbols found: {len(report.knowledge_graph.symbols)}")
    lines.append(f"- Edges found: {len(report.knowledge_graph.edges)}")
    lines.append(f"- Test files found: {len(report.knowledge_graph.test_files)}")
    lines.append(f"- Test mappings: {len(report.knowledge_graph.test_mappings)}")
    lines.append(f"- Features mapped: {len(report.knowledge_graph.features)}")
    lines.append(f"- API routes: {len(report.knowledge_graph.routes)}")
    lines.append(f"- Database schemas: {len(report.knowledge_graph.schemas)}")
    if report.knowledge_graph.languages:
        lines.append(
            "- Languages: "
            + ", ".join(f"{name} ({count})" for name, count in sorted(report.knowledge_graph.languages.items()))
        )
    if report.knowledge_graph.symbols:
        lines.append("")
        lines.append("Top symbols:")
        for symbol in report.knowledge_graph.symbols[:12]:
            lines.append(
                f"- `{symbol.kind}` `{symbol.qualified_name or symbol.name}` "
                f"in `{symbol.file}:{symbol.line}`"
            )
    if report.knowledge_graph.features:
        lines.append("")
        lines.append("Top feature mappings:")
        for feature in report.knowledge_graph.features[:10]:
            lines.append(
                f"- **{feature.name}** — {len(feature.files)} files, "
                f"{len(feature.tests)} tests (`{feature.source}`)"
            )
    lines.append("")

    if report.risks:
        lines.append("## Risks / Human Review")
        lines.append("")
        for risk in report.risks:
            lines.append(f"- **{risk.get('level', 'UNKNOWN')} / {risk.get('area', 'general')}:** {risk.get('message', '')}")
        lines.append("")

    lines.append("## Patch Suggestions")
    lines.append("")
    if report.fix_suggestions:
        for suggestion in report.fix_suggestions:
            files = (
                f" Affected: {', '.join('`' + file + '`' for file in suggestion.affected_files)}."
                if suggestion.affected_files
                else ""
            )
            lines.append(f"- **[{suggestion.severity}] {suggestion.title}:** {suggestion.problem}{files}")
    else:
        lines.append("No fix suggestions required.")
    lines.append("")

    lines.append("## Generated Artifacts")
    lines.append("")
    if report.artifacts:
        for artifact in report.artifacts:
            lines.append(f"- **{artifact.name}:** `{artifact.path}` — {artifact.purpose}")
    else:
        lines.append("No extra artifacts generated.")
    lines.append("")

    lines.append("## PR Acceptance Rule")
    lines.append("")
    lines.append(
        "Do not merge until Basalt returns `VERIFIED`, or until every remaining high-risk item is explicitly approved by a human reviewer."
    )
    lines.append("")
    return "\n".join(lines)


def write_markdown_report(report: ProofReport, output_path: Path) -> None:
    output_path.write_text(render_markdown(report), encoding="utf-8")
