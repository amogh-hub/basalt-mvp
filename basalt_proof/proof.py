from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .knowledge_graph import build_project_graph, write_graph_artifacts
from .config import load_config
from .models import CheckStatus, CommandSpec, FinalStatus, GeneratedArtifact, ProofReport
from .mutation import run_mutation_sample
from .patches import build_fix_suggestions, write_patch_artifacts
from .runner import CommandExecutor
from .security import scan_repo
from .workspace import Workspace


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _score_components(report: ProofReport) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = [{"label": "Base proof score", "delta": 100}]
    required_names = {"build", "test", "typecheck"}
    for check in report.checks:
        if check.status == CheckStatus.FAIL:
            delta = -25 if check.name in required_names else -12
            components.append({"label": f"Failed {check.name} check", "delta": delta})
        elif check.status == CheckStatus.SKIPPED and check.name in {"build", "lint", "typecheck"}:
            components.append({"label": f"Skipped {check.name} check", "delta": -2})
        elif check.status == CheckStatus.SKIPPED and check.name == "test":
            components.append({"label": "Skipped test check", "delta": -25})

    high = sum(1 for finding in report.security_findings if finding.level.upper() == "HIGH")
    medium = sum(1 for finding in report.security_findings if finding.level.upper() == "MEDIUM")
    security_penalty = min(40, high * 20 + medium * 8)
    if security_penalty:
        components.append(
            {
                "label": f"Security/policy findings ({high} high, {medium} medium)",
                "delta": -security_penalty,
            }
        )

    survived = sum(1 for mutation in report.mutations if mutation.survived)
    killed = sum(1 for mutation in report.mutations if not mutation.survived)
    if survived:
        components.append({"label": f"Survived mutations ({survived})", "delta": -min(40, 18 * survived)})
    elif killed:
        components.append({"label": f"Killed mutations ({killed})", "delta": min(4, killed * 2)})

    if not report.knowledge_graph.test_files:
        components.append({"label": "No test files detected", "delta": -15})
    if report.knowledge_graph.files_scanned == 0:
        components.append({"label": "No source files scanned", "delta": -5})
    return components


def _score_report(report: ProofReport) -> int:
    report.score_breakdown = _score_components(report)
    score = sum(int(component["delta"]) for component in report.score_breakdown)
    return max(0, min(100, score))


def _final_status(report: ProofReport, min_verified_score: int = 80) -> FinalStatus:
    high_security = [finding for finding in report.security_findings if finding.level.upper() == "HIGH"]
    if high_security:
        return FinalStatus.BLOCKED_BY_POLICY
    if any(check.status == CheckStatus.FAIL for check in report.checks):
        return FinalStatus.NOT_VERIFIED
    if any(mutation.survived for mutation in report.mutations):
        return FinalStatus.WEAK_PROOF
    if report.risks:
        return FinalStatus.NEEDS_HUMAN_REVIEW
    if report.score > 0 and report.score < min_verified_score:
        return FinalStatus.NEEDS_HUMAN_REVIEW
    return FinalStatus.VERIFIED


def _risk_model(security_findings) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []
    if any(
        finding.rule.startswith("drop_") or finding.rule in {"truncate", "destructive_alter"}
        for finding in security_findings
    ):
        risks.append(
            {
                "level": "HIGH",
                "area": "database",
                "message": "Destructive migration requires expand-and-contract approval.",
            }
        )
    if any(finding.rule in {"auth_bypass_comment", "hardcoded_admin_true"} for finding in security_findings):
        risks.append(
            {
                "level": "MEDIUM",
                "area": "auth",
                "message": "Auth or permission logic requires review.",
            }
        )
    return risks


def verify_repo(
    repo_path: Path,
    keep_workspace: bool = False,
    sandbox_override: str | None = None,
    output_dir: Path | None = None,
) -> ProofReport:
    repo_path = repo_path.resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        raise FileNotFoundError(f"Repository path not found: {repo_path}")

    started_at = _now()
    config = load_config(repo_path)
    graph_store = output_dir / "knowledge-graph.sqlite3" if output_dir else None
    graph_exclude = sorted(set(config.scan_exclude + config.graph_exclude))
    graph = build_project_graph(
        repo_path,
        store_path=graph_store,
        excluded_paths=graph_exclude,
    )
    sandbox_requested = sandbox_override or config.sandbox or "auto"
    executor = CommandExecutor(
        sandbox=sandbox_requested,
        docker_image=config.docker_image,
        docker_network=config.docker_network,
        fallback_to_temp=config.docker_fallback,
    )

    with Workspace(repo_path, keep=keep_workspace) as workspace:
        checks = []
        for spec in config.commands:
            result = executor.run(spec, workspace.path)
            checks.append(result)
            if spec.name == "install" and result.status == CheckStatus.FAIL:
                break

        security_findings = []
        if config.security_scan != "off":
            security_findings = scan_repo(
                workspace.path,
                block_destructive_migrations=config.block_destructive_migrations,
                block_secrets=config.block_secrets,
                excluded_paths=config.scan_exclude,
            )

        test_spec = config.command_by_name("test")
        mutation_spec = test_spec
        if config.mutation_test_command:
            mutation_spec = CommandSpec(
                name="mutation_test",
                command=config.mutation_test_command,
                required=True,
                timeout_seconds=test_spec.timeout_seconds if test_spec else 600,
            )
        tests_passed = any(check.name == "test" and check.status == CheckStatus.PASS for check in checks)
        mutations = []
        if config.mutation_sample and tests_passed:
            mutations = run_mutation_sample(
                workspace.path,
                mutation_spec,
                executor=executor,
                max_mutations=config.mutation_max,
                include_paths=config.mutation_include,
                exclude_paths=config.mutation_exclude,
                per_file=config.mutation_per_file,
            )

        risks = _risk_model(security_findings)
        report = ProofReport(
            project_name=config.project_name,
            repo_path=str(repo_path),
            started_at=started_at,
            finished_at=_now(),
            final_status=FinalStatus.NOT_VERIFIED,
            score=0,
            sandbox=executor.effective_sandbox,
            sandbox_requested=sandbox_requested,
            sandbox_fallback_reason=executor.fallback_reason,
            project_type=config.project_type,
            project_state_hash=graph.state_hash,
            checks=checks,
            security_findings=security_findings,
            mutations=mutations,
            knowledge_graph=graph,
            risks=risks,
            evidence_dir=str(workspace.path) if keep_workspace else None,
        )
        report.score = _score_report(report)
        report.final_status = _final_status(report, config.min_verified_score)
        report.fix_suggestions = build_fix_suggestions(report)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        graph_paths = write_graph_artifacts(graph, output_dir)
        graph_artifacts = [
            GeneratedArtifact("Project Graph JSON", str(graph_paths[0]), "Machine-readable AST-anchored project graph"),
            GeneratedArtifact("Project Graph Markdown", str(graph_paths[1]), "Human-readable project graph summary"),
            GeneratedArtifact("Graph Manifest", str(graph_paths[2]), "File hashes and project-state freshness evidence"),
        ]
        if graph_store:
            graph_artifacts.append(
                GeneratedArtifact(
                    "Knowledge Graph SQLite",
                    str(graph_store),
                    "Persistent relational graph store for files, symbols, edges, features, and tests",
                )
            )
        patch_artifacts = write_patch_artifacts(report, output_dir)
        report.artifacts.extend(graph_artifacts + patch_artifacts)
        report.patch_plan_path = next((artifact.path for artifact in patch_artifacts if artifact.name == "Patch Plan"), None)

    return report
