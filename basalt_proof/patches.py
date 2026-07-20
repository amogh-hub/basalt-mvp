from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .models import CheckStatus, FixSuggestion, GeneratedArtifact, ProofReport


def build_fix_suggestions(report: ProofReport) -> list[FixSuggestion]:
    suggestions: list[FixSuggestion] = []

    for check in report.checks:
        if check.status == CheckStatus.FAIL:
            severity = "HIGH" if check.name in {"build", "test", "typecheck"} else "MEDIUM"
            suggestions.append(
                FixSuggestion(
                    title=f"Fix failing {check.name} check",
                    severity=severity,
                    category="verification",
                    problem=f"The `{check.name}` command failed: `{check.command}`.",
                    recommended_change=(
                        "Open the command output in the Proof Report, fix the first root-cause error, "
                        "then rerun Basalt. Do not suppress the check unless the check itself is invalid."
                    ),
                    verification_command=check.command or "basalt verify .",
                )
            )
        elif check.status == CheckStatus.SKIPPED and check.name == "test":
            suggestions.append(
                FixSuggestion(
                    title="Add a real test command",
                    severity="HIGH",
                    category="proof_strength",
                    problem="No test command is configured, so Basalt cannot prove behavior.",
                    recommended_change="Add tests and configure `commands.test` in basalt.yaml.",
                    verification_command="basalt verify .",
                )
            )

    low_groups: dict[str, list] = defaultdict(list)
    for finding in report.security_findings:
        level = finding.level.upper()
        if level == "LOW":
            low_groups[finding.rule].append(finding)
            continue
        if level == "HIGH":
            suggestions.append(
                FixSuggestion(
                    title=f"Resolve policy-blocking finding: {finding.rule}",
                    severity="HIGH",
                    category="security_policy",
                    problem=f"{finding.message} at `{finding.file}:{finding.line}`.",
                    recommended_change=(
                        "Remove the secret or risky operation. Use environment variables, a secret vault, "
                        "least-privilege configuration, or an expand-and-contract migration plan."
                    ),
                    affected_files=[finding.file],
                    verification_command="basalt verify .",
                )
            )
        else:
            suggestions.append(
                FixSuggestion(
                    title=f"Review security warning: {finding.rule}",
                    severity=level,
                    category="security_review",
                    problem=f"{finding.message} at `{finding.file}:{finding.line}`.",
                    recommended_change="Review and fix the line, or document why it is safe.",
                    affected_files=[finding.file],
                    verification_command="basalt verify .",
                )
            )

    for rule, findings in sorted(low_groups.items()):
        affected = list(dict.fromkeys(finding.file for finding in findings))[:8]
        suggestions.append(
            FixSuggestion(
                title=f"Optional cleanup: {rule}",
                severity="LOW",
                category="maintainability",
                problem=f"Basalt found {len(findings)} low-severity `{rule}` finding(s).",
                recommended_change="Address during normal cleanup; these findings do not block verification.",
                affected_files=affected,
                verification_command="basalt verify .",
            )
        )

    for mutation in [item for item in report.mutations if item.survived]:
        suggestions.append(
            FixSuggestion(
                title=f"Strengthen tests for {mutation.file}",
                severity="HIGH",
                category="mutation_testing",
                problem=(
                    f"A `{mutation.mutation_type}` mutation survived in `{mutation.file}` "
                    f"(`{mutation.original}` -> `{mutation.replacement}`)."
                ),
                recommended_change=(
                    "Add tests that fail when this logic changes. Focus on boundaries, negative paths, "
                    "authorization checks, expected errors, and contract assertions."
                ),
                affected_files=[mutation.file],
                verification_command="basalt verify .",
            )
        )

    if not report.knowledge_graph.test_files:
        suggestions.append(
            FixSuggestion(
                title="Add a test suite mapped to behavior",
                severity="HIGH",
                category="proof_strength",
                problem="Basalt did not find test files in the AST-backed project graph.",
                recommended_change="Create tests for core behavior and configure the test command in basalt.yaml.",
                verification_command="basalt verify .",
            )
        )

    if report.score < 90 and not any(item.severity in {"HIGH", "MEDIUM"} for item in suggestions):
        suggestions.append(
            FixSuggestion(
                title="Raise proof score above 90",
                severity="MEDIUM",
                category="quality",
                problem=f"Proof score is {report.score}/100.",
                recommended_change="Add missing checks, reduce warnings, and improve mutation strength.",
                verification_command="basalt verify .",
            )
        )
    return suggestions


def render_patch_plan(report: ProofReport) -> str:
    lines: list[str] = [
        "# Basalt Proof-to-PR Patch Plan",
        "",
        f"**Project:** {report.project_name}",
        f"**Current verdict:** `{report.final_status.value}`",
        f"**Proof score:** `{report.score}/100`",
        f"**Sandbox:** `{report.sandbox}`",
        "",
        "This plan is generated from deterministic checks, security and dependency findings, mutation testing, and AST-backed project signals.",
        "",
    ]
    if not report.fix_suggestions:
        lines.append("No fix suggestions required. The project is verified under the configured proof policy.")
        return "\n".join(lines) + "\n"

    lines += ["## Recommended branch", "", "```bash", "git checkout -b basalt/proof-hardening", "```", ""]
    for index, suggestion in enumerate(report.fix_suggestions, start=1):
        lines += [
            f"## {index}. {suggestion.title}",
            "",
            f"- **Severity:** {suggestion.severity}",
            f"- **Category:** {suggestion.category}",
        ]
        if suggestion.affected_files:
            lines.append(f"- **Affected files:** {', '.join('`' + file + '`' for file in suggestion.affected_files)}")
        lines += [
            f"- **Problem:** {suggestion.problem}",
            f"- **Recommended change:** {suggestion.recommended_change}",
        ]
        if suggestion.verification_command:
            lines.append(f"- **Verify with:** `{suggestion.verification_command}`")
        lines.append("")

    lines += [
        "## PR acceptance rule",
        "",
        "Do not merge until Basalt returns `VERIFIED`, or until every remaining high-risk item is explicitly approved by a human reviewer.",
        "",
    ]
    return "\n".join(lines)


def render_github_pr_description(report: ProofReport) -> str:
    lines = [
        "# Basalt Proof Evidence",
        "",
        f"Project: `{report.project_name}`",
        f"Basalt verdict: `{report.final_status.value}`",
        f"Proof score: `{report.score}/100`",
        f"Sandbox: `{report.sandbox}`",
        "",
        "## Required changes",
    ]
    if report.fix_suggestions:
        for suggestion in report.fix_suggestions:
            lines.append(f"- [{suggestion.severity}] {suggestion.title}: {suggestion.problem}")
    else:
        lines.append("- No changes required. Basalt marked the repository verified.")
    lines += [
        "",
        "## Verification checklist",
        "- [ ] `basalt verify .` returns `VERIFIED` or documented human-review exceptions",
        "- [ ] No blocking security findings remain",
        "- [ ] Survived mutations are killed by improved tests or explicitly accepted with rationale",
        "- [ ] Proof report and dashboard are attached",
    ]
    return "\n".join(lines) + "\n"


def write_patch_artifacts(report: ProofReport, output_dir: Path) -> list[GeneratedArtifact]:
    artifacts: list[GeneratedArtifact] = []
    patch_path = output_dir / "basalt-patch-plan.md"
    patch_path.write_text(render_patch_plan(report), encoding="utf-8")
    artifacts.append(GeneratedArtifact("Patch Plan", str(patch_path), "PR-ready remediation plan"))

    pr_path = output_dir / "github-pr-description.md"
    pr_path.write_text(render_github_pr_description(report), encoding="utf-8")
    artifacts.append(
        GeneratedArtifact("GitHub PR Description", str(pr_path), "Copy/paste PR body for proof-hardening branch")
    )
    return artifacts
