from __future__ import annotations

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

    for finding in report.security_findings:
        if finding.level.upper() == "HIGH":
            suggestions.append(
                FixSuggestion(
                    title=f"Resolve policy-blocking finding: {finding.rule}",
                    severity="HIGH",
                    category="security_policy",
                    problem=f"{finding.message} at `{finding.file}:{finding.line}`.",
                    recommended_change=(
                        "Remove the secret/risky operation from source. Use environment variables, a secret vault, "
                        "or an expand-and-contract migration plan for data-destructive changes."
                    ),
                    affected_files=[finding.file],
                    verification_command="basalt verify .",
                )
            )
        else:
            suggestions.append(
                FixSuggestion(
                    title=f"Review security warning: {finding.rule}",
                    severity="MEDIUM",
                    category="security_review",
                    problem=f"{finding.message} at `{finding.file}:{finding.line}`.",
                    recommended_change="Review and fix the line, or document why it is safe.",
                    affected_files=[finding.file],
                    verification_command="basalt verify .",
                )
            )

    survived = [m for m in report.mutations if m.survived]
    for mutation in survived:
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
                    "Add tests that fail when this logic is changed. Focus on boundary cases, negative paths, "
                    "auth/permission checks, expected error behavior, and schema/contract assertions."
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

    if report.score < 90 and not suggestions:
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
    lines: list[str] = []
    lines.append("# Basalt Proof-to-PR Patch Plan")
    lines.append("")
    lines.append(f"**Project:** {report.project_name}")
    lines.append(f"**Current verdict:** `{report.final_status.value}`")
    lines.append(f"**Proof score:** `{report.score}/100`")
    lines.append("")
    lines.append("This is a PR-ready remediation plan generated from deterministic checks, security scan findings, mutation testing, and AST-backed project graph signals.")
    lines.append("")
    if not report.fix_suggestions:
        lines.append("No fix suggestions required. The project is verified under the configured proof policy.")
        return "\n".join(lines) + "\n"

    lines.append("## Recommended branch")
    lines.append("")
    lines.append("```bash")
    lines.append("git checkout -b basalt/proof-hardening")
    lines.append("```")
    lines.append("")

    for i, suggestion in enumerate(report.fix_suggestions, start=1):
        lines.append(f"## {i}. {suggestion.title}")
        lines.append("")
        lines.append(f"- **Severity:** {suggestion.severity}")
        lines.append(f"- **Category:** {suggestion.category}")
        if suggestion.affected_files:
            lines.append(f"- **Affected files:** {', '.join('`' + f + '`' for f in suggestion.affected_files)}")
        lines.append(f"- **Problem:** {suggestion.problem}")
        lines.append(f"- **Recommended change:** {suggestion.recommended_change}")
        if suggestion.verification_command:
            lines.append(f"- **Verify with:** `{suggestion.verification_command}`")
        lines.append("")

    lines.append("## PR acceptance rule")
    lines.append("")
    lines.append("Do not merge until Basalt returns `VERIFIED`, or until every remaining high-risk item is explicitly approved by a human reviewer.")
    lines.append("")
    return "\n".join(lines)


def render_github_pr_description(report: ProofReport) -> str:
    lines = [
        "# Basalt Proof Hardening PR",
        "",
        f"Project: `{report.project_name}`",
        f"Current Basalt verdict: `{report.final_status.value}`",
        f"Proof score: `{report.score}/100`",
        "",
        "## Why this PR exists",
        "Basalt found proof, policy, mutation, or security gaps that prevent the repo from being trusted as production-ready.",
        "",
        "## Required changes",
    ]
    if report.fix_suggestions:
        for s in report.fix_suggestions:
            lines.append(f"- [{s.severity}] {s.title}: {s.problem}")
    else:
        lines.append("- No changes required. Basalt marked the repo verified.")
    lines += [
        "",
        "## Verification checklist",
        "- [ ] `basalt verify .` returns `VERIFIED` or documented human review exceptions",
        "- [ ] No blocking security findings remain",
        "- [ ] Survived mutations are killed by improved tests or explicitly accepted with rationale",
        "- [ ] Proof report attached to PR",
    ]
    return "\n".join(lines) + "\n"


def write_patch_artifacts(report: ProofReport, output_dir: Path) -> list[GeneratedArtifact]:
    artifacts: list[GeneratedArtifact] = []
    patch_path = output_dir / "basalt-patch-plan.md"
    patch_path.write_text(render_patch_plan(report), encoding="utf-8")
    artifacts.append(GeneratedArtifact("Patch Plan", str(patch_path), "PR-ready remediation plan"))

    pr_path = output_dir / "github-pr-description.md"
    pr_path.write_text(render_github_pr_description(report), encoding="utf-8")
    artifacts.append(GeneratedArtifact("GitHub PR Description", str(pr_path), "Copy/paste PR body for proof-hardening branch"))
    return artifacts
