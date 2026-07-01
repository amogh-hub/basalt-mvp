from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .ast_graph import build_knowledge_graph
from .config import load_config
from .models import CheckStatus, FinalStatus, GeneratedArtifact, ProofReport
from .mutation import run_mutation_sample
from .patches import build_fix_suggestions, write_patch_artifacts
from .runner import CommandExecutor
from .security import scan_repo
from .workspace import Workspace


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _score_report(report: ProofReport) -> int:
    score = 100
    required_names = {"build", "test", "typecheck"}
    for check in report.checks:
        if check.status == CheckStatus.FAIL:
            score -= 25 if check.name in required_names else 12
        elif check.status == CheckStatus.SKIPPED and check.name in {"build", "lint", "typecheck"}:
            score -= 2
        elif check.status == CheckStatus.SKIPPED and check.name == "test":
            score -= 25
    high = sum(1 for f in report.security_findings if f.level.upper() == "HIGH")
    medium = sum(1 for f in report.security_findings if f.level.upper() == "MEDIUM")
    score -= min(40, high * 20 + medium * 8)
    survived = sum(1 for mutation in report.mutations if mutation.survived)
    killed = sum(1 for mutation in report.mutations if not mutation.survived)
    if survived:
        score -= min(40, 18 * survived)
    elif killed:
        score += 2
    if not report.knowledge_graph.test_files:
        score -= 15
    if report.knowledge_graph.files_scanned == 0:
        score -= 5
    return max(0, min(100, score))


def _final_status(report: ProofReport) -> FinalStatus:
    required_failures = [c for c in report.checks if c.status == CheckStatus.FAIL and c.name in {"build", "typecheck", "test"}]
    any_failures = [c for c in report.checks if c.status == CheckStatus.FAIL]
    if required_failures or any_failures:
        return FinalStatus.NOT_VERIFIED
    high_security = [f for f in report.security_findings if f.level.upper() == "HIGH"]
    if high_security:
        return FinalStatus.BLOCKED_BY_POLICY
    if any(m.survived for m in report.mutations):
        return FinalStatus.WEAK_PROOF
    if report.risks:
        return FinalStatus.NEEDS_HUMAN_REVIEW
    return FinalStatus.VERIFIED


def _risk_model(security_findings) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []
    if any(f.rule.startswith("drop_") or f.rule in {"truncate", "destructive_alter"} for f in security_findings):
        risks.append({"level": "HIGH", "area": "database", "message": "Destructive migration requires expand-and-contract approval."})
    if any(f.rule in {"auth_bypass_comment", "hardcoded_admin_true"} for f in security_findings):
        risks.append({"level": "MEDIUM", "area": "auth", "message": "Auth or permission logic requires review."})
    return risks


def verify_repo(repo_path: Path, keep_workspace: bool = False, sandbox_override: str | None = None, output_dir: Path | None = None) -> ProofReport:
    repo_path = repo_path.resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        raise FileNotFoundError(f"Repository path not found: {repo_path}")

    started_at = _now()
    config = load_config(repo_path)
    sandbox = sandbox_override or config.sandbox or "temp"
    executor = CommandExecutor(sandbox=sandbox, docker_image=config.docker_image)

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
            )

        graph = build_knowledge_graph(workspace.path)
        test_spec = config.command_by_name("test")
        tests_passed = any(c.name == "test" and c.status == CheckStatus.PASS for c in checks)
        mutations = []
        if config.mutation_sample and tests_passed:
            mutations = run_mutation_sample(workspace.path, test_spec, executor=executor, max_mutations=config.mutation_max)

        risks = _risk_model(security_findings)

        report = ProofReport(
            project_name=config.project_name,
            repo_path=str(repo_path),
            started_at=started_at,
            finished_at=_now(),
            final_status=FinalStatus.NOT_VERIFIED,
            score=0,
            sandbox=sandbox,
            project_type=config.project_type,
            checks=checks,
            security_findings=security_findings,
            mutations=mutations,
            knowledge_graph=graph,
            risks=risks,
            evidence_dir=str(workspace.path) if keep_workspace else None,
        )
        report.score = _score_report(report)
        report.final_status = _final_status(report)
        report.fix_suggestions = build_fix_suggestions(report)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        # Patch artifacts are produced after final status and suggestions are known.
        patch_artifacts = write_patch_artifacts(report, output_dir)
        report.artifacts.extend(patch_artifacts)
        report.patch_plan_path = next((a.path for a in patch_artifacts if a.name == "Patch Plan"), None)

    return report
