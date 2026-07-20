from __future__ import annotations

import hashlib
import json
import secrets
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .autofix import generate_fix_files, render_unified_patch
from .config import load_config
from .context_compiler import compile_context_for_repo
from .knowledge_graph import analyze_impact, build_project_graph, write_graph_artifacts
from .models import (
    AgentAction,
    AgentRun,
    AgentRunStatus,
    ApprovalRecord,
    ImpactAnalysis,
    PatchStats,
    PolicyDecision,
    PolicyVerdict,
    VerificationDelta,
)
from .patch_engine import (
    PatchError,
    apply_patch,
    create_backup,
    parse_unified_diff,
    patch_as_dict,
    patch_sha256,
    patch_stats,
    render_patch_summary,
    restore_backup,
    validate_patch_applies,
)
from .policy_kernel import evaluate_patch_policy, render_policy_markdown
from .proof import verify_repo


class AgentRunError(RuntimeError):
    """Raised when an agent run cannot safely advance."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id(task: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(f"{task}|{secrets.token_hex(8)}".encode("utf-8")).hexdigest()[:10]
    return f"run_{stamp}_{digest}"


def _run_root(repo: Path, out_dir: Path | None = None) -> Path:
    base = out_dir.resolve() if out_dir else repo.resolve() / ".basalt"
    root = base / "agent-runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run_dir(repo: Path, run_id: str, out_dir: Path | None = None) -> Path:
    return _run_root(repo, out_dir) / run_id


def _action(role: str, action: str, status: str, summary: str, tools: list[str], artifacts: list[str] | None = None, risks: list[str] | None = None) -> AgentAction:
    timestamp = _now()
    return AgentAction(
        agent_role=role,
        action=action,
        status=status,
        summary=summary,
        started_at=timestamp,
        finished_at=timestamp,
        tools_used=tools,
        artifacts=artifacts or [],
        risk_flags=risks or [],
    )


def _policy_from_dict(data: dict[str, Any] | None) -> PolicyDecision | None:
    if not data:
        return None
    stats_data = data.get("patch_stats") or {}
    stats = PatchStats(**stats_data)
    return PolicyDecision(
        verdict=PolicyVerdict(data["verdict"]),
        risk_level=data.get("risk_level", "UNKNOWN"),
        reasons=list(data.get("reasons") or []),
        risk_flags=list(data.get("risk_flags") or []),
        required_approvals=list(data.get("required_approvals") or []),
        required_locks=list(data.get("required_locks") or []),
        allowed_tools=list(data.get("allowed_tools") or []),
        denied_capabilities=list(data.get("denied_capabilities") or []),
        patch_stats=stats,
    )


def _approval_from_dict(data: dict[str, Any] | None) -> ApprovalRecord | None:
    return ApprovalRecord(**data) if data else None


def _delta_from_dict(data: dict[str, Any] | None) -> VerificationDelta | None:
    return VerificationDelta(**data) if data else None


def _action_from_dict(data: dict[str, Any]) -> AgentAction:
    return AgentAction(**data)


def _run_from_dict(data: dict[str, Any]) -> AgentRun:
    return AgentRun(
        run_id=data["run_id"],
        task=data["task"],
        agent_role=data["agent_role"],
        repo_path=data["repo_path"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        status=AgentRunStatus(data["status"]),
        base_state_hash=data["base_state_hash"],
        current_state_hash=data.get("current_state_hash", ""),
        context_pack_id=data.get("context_pack_id", ""),
        targets=list(data.get("targets") or []),
        candidate_patch_path=data.get("candidate_patch_path", ""),
        proposal_source=data.get("proposal_source", ""),
        attempt=int(data.get("attempt", 1)),
        max_attempts=int(data.get("max_attempts", 3)),
        patch_hashes=list(data.get("patch_hashes") or []),
        policy_decision=_policy_from_dict(data.get("policy_decision")),
        approval=_approval_from_dict(data.get("approval")),
        agent_actions=[_action_from_dict(item) for item in data.get("agent_actions") or []],
        impacted_files=list(data.get("impacted_files") or []),
        impacted_tests=list(data.get("impacted_tests") or []),
        impacted_features=list(data.get("impacted_features") or []),
        before_report_path=data.get("before_report_path", ""),
        after_report_path=data.get("after_report_path", ""),
        verification_delta=_delta_from_dict(data.get("verification_delta")),
        backup_dir=data.get("backup_dir", ""),
        applied_files=list(data.get("applied_files") or []),
        rollback_performed=bool(data.get("rollback_performed", False)),
        message=data.get("message", ""),
    )


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_run(run: AgentRun, run_dir: Path) -> None:
    run.updated_at = _now()
    _write_json(run_dir / "run.json", run.to_dict())
    _write_summary(run, run_dir / "run-summary.md")
    root = run_dir.parent
    index_path = root / "index.json"
    entries: list[dict[str, Any]] = []
    if index_path.exists():
        try:
            entries = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []
    entries = [item for item in entries if item.get("run_id") != run.run_id]
    entries.append(
        {
            "run_id": run.run_id,
            "task": run.task,
            "agent_role": run.agent_role,
            "status": run.status.value,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "risk": run.policy_decision.risk_level if run.policy_decision else "UNKNOWN",
        }
    )
    entries.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    _write_json(index_path, entries)
    with (root / "audit.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp": run.updated_at,
                    "run_id": run.run_id,
                    "status": run.status.value,
                    "message": run.message,
                    "attempt": run.attempt,
                },
                sort_keys=True,
            )
            + "\n"
        )


def _write_summary(run: AgentRun, path: Path) -> None:
    lines = [
        "# Basalt Agent-Assisted Safe Fix Run",
        "",
        f"- Run: `{run.run_id}`",
        f"- Status: `{run.status.value}`",
        f"- Task: {run.task}",
        f"- Authoring role: `{run.agent_role}`",
        f"- Base state: `{run.base_state_hash}`",
        f"- Attempt: `{run.attempt}/{run.max_attempts}`",
        f"- Message: {run.message}",
        "",
    ]
    if run.policy_decision:
        lines.extend(
            [
                "## Policy",
                "",
                f"- Verdict: `{run.policy_decision.verdict.value}`",
                f"- Risk: `{run.policy_decision.risk_level}`",
                f"- Files: `{run.policy_decision.patch_stats.files_changed}`",
                f"- Changed lines: `{run.policy_decision.patch_stats.changed_lines}`",
                "",
            ]
        )
    if run.approval:
        lines.extend(
            [
                "## Approval",
                "",
                f"- Required: `{run.approval.required}`",
                f"- Approved: `{run.approval.approved}`",
                f"- Actor: `{run.approval.actor or '—'}`",
                f"- Token used: `{run.approval.token_used}`",
                "",
            ]
        )
    if run.verification_delta:
        delta = run.verification_delta
        lines.extend(
            [
                "## Verification delta",
                "",
                f"- Verdict: `{delta.before_status}` → `{delta.after_status}`",
                f"- Score: `{delta.before_score}` → `{delta.after_score}` ({delta.score_delta:+d})",
                f"- Survived mutations: `{delta.before_survived_mutations}` → `{delta.after_survived_mutations}`",
                f"- High findings: `{delta.before_high_findings}` → `{delta.after_high_findings}`",
                f"- Accepted: `{delta.accepted}`",
                "",
            ]
        )
    lines.extend(["## Agent court", ""])
    for action in run.agent_actions:
        lines.append(f"- **{action.agent_role} / {action.action}:** `{action.status}` — {action.summary}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_agent_run(repo: Path, run_id: str, out_dir: Path | None = None) -> tuple[AgentRun, Path]:
    run_dir = _run_dir(repo, run_id, out_dir)
    state_path = run_dir / "run.json"
    if not state_path.exists():
        raise AgentRunError(f"Agent run not found: {run_id}")
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AgentRunError(f"Agent run state is corrupt: {state_path}") from exc
    return _run_from_dict(data), run_dir


def list_agent_runs(repo: Path, out_dir: Path | None = None) -> list[dict[str, Any]]:
    index = _run_root(repo, out_dir) / "index.json"
    if not index.exists():
        return []
    try:
        return json.loads(index.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _report_metrics(data: dict[str, Any]) -> dict[str, int | str]:
    return {
        "status": str(data.get("final_status", "UNKNOWN")),
        "score": int(data.get("score", 0)),
        "survived": sum(1 for item in data.get("mutations", []) if item.get("survived") is True),
        "high": sum(1 for item in data.get("security_findings", []) if str(item.get("level", "")).upper() == "HIGH"),
        "failed": sum(1 for item in data.get("checks", []) if str(item.get("status", "")) == "FAIL"),
    }


def _verification_delta(before: dict[str, Any], after: dict[str, Any]) -> VerificationDelta:
    b = _report_metrics(before)
    a = _report_metrics(after)
    reasons: list[str] = []
    accepted = True
    if a["status"] != "VERIFIED":
        accepted = False
        reasons.append(f"After-patch verdict is {a['status']}, not VERIFIED.")
    if int(a["score"]) < int(b["score"]):
        accepted = False
        reasons.append("Proof score regressed.")
    if int(a["survived"]) > int(b["survived"]):
        accepted = False
        reasons.append("More mutations survived after the patch.")
    if int(a["high"]) > int(b["high"]):
        accepted = False
        reasons.append("The patch introduced additional high-severity findings.")
    if int(a["failed"]) > int(b["failed"]):
        accepted = False
        reasons.append("The patch introduced additional failed checks.")
    improved = (
        int(a["score"]) > int(b["score"])
        or int(a["survived"]) < int(b["survived"])
        or int(a["failed"]) < int(b["failed"])
        or (b["status"] != "VERIFIED" and a["status"] == "VERIFIED")
    )
    if accepted and not reasons:
        reasons.append("Patch passed proof without regression.")
    return VerificationDelta(
        before_status=str(b["status"]),
        after_status=str(a["status"]),
        before_score=int(b["score"]),
        after_score=int(a["score"]),
        score_delta=int(a["score"]) - int(b["score"]),
        before_survived_mutations=int(b["survived"]),
        after_survived_mutations=int(a["survived"]),
        before_high_findings=int(b["high"]),
        after_high_findings=int(a["high"]),
        before_failed_checks=int(b["failed"]),
        after_failed_checks=int(a["failed"]),
        improved=improved,
        accepted=accepted,
        reasons=reasons,
    )


def _write_delta(delta: VerificationDelta, run_dir: Path) -> None:
    _write_json(run_dir / "verification-delta.json", asdict(delta))
    lines = [
        "# Basalt Verification Delta",
        "",
        f"- Status: `{delta.before_status}` → `{delta.after_status}`",
        f"- Score: `{delta.before_score}` → `{delta.after_score}` ({delta.score_delta:+d})",
        f"- Survived mutations: `{delta.before_survived_mutations}` → `{delta.after_survived_mutations}`",
        f"- High findings: `{delta.before_high_findings}` → `{delta.after_high_findings}`",
        f"- Failed checks: `{delta.before_failed_checks}` → `{delta.after_failed_checks}`",
        f"- Improved: `{delta.improved}`",
        f"- Accepted: `{delta.accepted}`",
        "",
        "## Decision reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in delta.reasons)
    (run_dir / "verification-delta.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _collect_impacts(graph, targets: list[str], patch_paths: list[str]) -> list[ImpactAnalysis]:
    impacts: list[ImpactAnalysis] = []
    seen: set[str] = set()
    for target in targets + patch_paths:
        if target in seen:
            continue
        seen.add(target)
        result = analyze_impact(graph, target, depth=3)
        if result.found:
            impacts.append(result)
    return impacts


def _aggregate_impact(impacts: list[ImpactAnalysis]) -> tuple[list[str], list[str], list[str]]:
    files: list[str] = []
    tests: list[str] = []
    features: list[str] = []
    for impact in impacts:
        files.extend(impact.impacted_files)
        tests.extend(impact.impacted_tests)
        features.extend(impact.impacted_features)
    return sorted(set(files)), sorted(set(tests)), sorted(set(features))


def _write_proposal(run: AgentRun, changes, impacts: list[ImpactAnalysis], run_dir: Path) -> None:
    decision = run.policy_decision
    proposal = {
        "patch_id": f"patch_{patch_sha256((run_dir / 'candidate.patch').read_text(encoding='utf-8'))[:16]}",
        "base_state_version": run.base_state_hash,
        "agent_role": run.agent_role,
        "summary": run.task,
        "files_changed": decision.patch_stats.paths if decision else [],
        "risk_flags": decision.risk_flags if decision else [],
        "required_locks": decision.required_locks if decision else [],
        "tests_to_run": run.impacted_tests,
        "assumptions": [],
        "attempt": run.attempt,
        "proposal_source": run.proposal_source,
        "changes": patch_as_dict(changes),
        "impact_analyses": [asdict(item) for item in impacts],
    }
    _write_json(run_dir / "patch-proposal.json", proposal)
    transaction = {
        "run_id": run.run_id,
        "base_state": run.base_state_hash,
        "current_state": run.current_state_hash or run.base_state_hash,
        "state_transition": None,
        "commit_authority": "BasaltOrchestrator",
        "human_approval_required": bool(run.approval and run.approval.required),
        "policy_verdict": decision.verdict.value if decision else "UNKNOWN",
        "status": run.status.value,
    }
    _write_json(run_dir / "state-transaction.json", transaction)


def plan_agent_fix(
    repo: Path,
    task: str,
    agent_role: str = "ImplementationAgent",
    targets: list[str] | None = None,
    patch_file: Path | None = None,
    out_dir: Path | None = None,
    sandbox: str | None = None,
    token_budget: int | None = None,
) -> AgentRun:
    repo = repo.resolve()
    if not repo.exists() or not repo.is_dir():
        raise AgentRunError(f"Repository not found: {repo}")
    config = load_config(repo)
    run_id = _new_run_id(task)
    run_dir = _run_dir(repo, run_id, out_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    target_list = list(dict.fromkeys(targets or []))

    graph_store = repo / ".basalt" / "knowledge-graph.sqlite3"
    graph_exclude = sorted(set(config.scan_exclude + config.graph_exclude))
    graph = build_project_graph(repo, graph_store, graph_exclude)
    write_graph_artifacts(graph, repo / ".basalt")
    run = AgentRun(
        run_id=run_id,
        task=task,
        agent_role=agent_role,
        repo_path=str(repo),
        created_at=_now(),
        updated_at=_now(),
        status=AgentRunStatus.PLANNED,
        base_state_hash=graph.state_hash,
        current_state_hash=graph.state_hash,
        targets=target_list,
        max_attempts=config.agent_max_attempts,
        message="Safe-fix plan created against current project truth.",
    )
    run.agent_actions.append(
        _action(
            "PlannerAgent",
            "scope_task",
            "PASS",
            f"Bound task to {len(target_list)} explicit target(s) at state {graph.state_hash[:12]}.",
            ["graph.query", "impact.map"],
        )
    )
    _write_run(run, run_dir)

    context_dir = run_dir / "context"
    pack, context_artifacts = compile_context_for_repo(
        repo,
        context_dir,
        task=task,
        agent_role=agent_role,
        targets=target_list,
        token_budget=max(500, token_budget or config.context_token_budget),
        excluded_paths=graph_exclude,
        refresh=config.graph_auto_refresh,
    )
    run.context_pack_id = pack.context_pack_id
    run.status = AgentRunStatus.CONTEXT_COMPILED
    run.agent_actions.append(
        _action(
            "ContextCompiler",
            "compile_context",
            "PASS",
            f"Compiled {len(pack.files)} focused files within {pack.estimated_tokens}/{pack.token_budget} tokens.",
            ["context.compile", "graph.read"],
            [str(path) for path in context_artifacts],
        )
    )
    _write_run(run, run_dir)

    before_dir = run_dir / "before-verification"
    before_report = verify_repo(repo, sandbox_override=sandbox, output_dir=before_dir)
    before_path = run_dir / "before-proof.json"
    _write_json(before_path, before_report.to_dict())
    run.before_report_path = str(before_path)

    if patch_file:
        patch_text = patch_file.resolve().read_text(encoding="utf-8")
        proposal_source = f"external:{patch_file.resolve()}"
    else:
        generated = generate_fix_files(repo, before_report)
        if not generated:
            run.status = AgentRunStatus.NOT_VERIFIED
            run.message = "No bounded deterministic patch could be generated. Supply an external unified diff for policy review."
            run.agent_actions.append(
                _action(
                    agent_role,
                    "propose_patch",
                    "NO_PROPOSAL",
                    run.message,
                    ["proof.read", "mutation.feedback"],
                )
            )
            _write_run(run, run_dir)
            return run
        patch_text = render_unified_patch(generated)
        proposal_source = "built-in-proof-hardening"

    try:
        changes = parse_unified_diff(patch_text)
        validate_patch_applies(repo, changes)
    except (OSError, PatchError) as exc:
        run.status = AgentRunStatus.BLOCKED_BY_POLICY
        run.message = f"Candidate patch rejected before policy review: {exc}"
        run.agent_actions.append(
            _action(agent_role, "propose_patch", "REJECTED", run.message, ["patch.parse", "patch.check"])
        )
        _write_run(run, run_dir)
        return run

    candidate_path = run_dir / "candidate.patch"
    candidate_path.write_text(patch_text, encoding="utf-8")
    (run_dir / "candidate-patch.md").write_text(render_patch_summary(changes), encoding="utf-8")
    run.candidate_patch_path = str(candidate_path)
    run.proposal_source = proposal_source
    patch_hash = patch_sha256(patch_text)
    run.patch_hashes.append(patch_hash)
    run.status = AgentRunStatus.PATCH_PROPOSED
    run.agent_actions.append(
        _action(
            agent_role,
            "propose_patch",
            "PASS",
            f"Proposed an atomic patch changing {patch_stats(changes).files_changed} file(s).",
            ["patch.propose"],
            [str(candidate_path)],
        )
    )

    impacts = _collect_impacts(graph, target_list, patch_stats(changes).paths)
    run.impacted_files, run.impacted_tests, run.impacted_features = _aggregate_impact(impacts)
    run.agent_actions.append(
        _action(
            "TestingAgent",
            "select_proof_scope",
            "PASS",
            f"Selected {len(run.impacted_tests)} mapped test file(s) plus the full configured proof suite.",
            ["impact.read", "tests.map", "mutation.feedback"],
        )
    )

    decision = evaluate_patch_policy(
        config,
        agent_role,
        changes,
        impacts,
        base_state_hash=run.base_state_hash,
        current_state_hash=graph.state_hash,
    )
    run.policy_decision = decision
    _write_json(run_dir / "policy-decision.json", _policy_to_dict(decision))
    (run_dir / "policy-decision.md").write_text(render_policy_markdown(decision), encoding="utf-8")
    run.agent_actions.append(
        _action(
            "SecurityAgent",
            "security_review",
            "BLOCK" if decision.verdict == PolicyVerdict.BLOCK else "PASS",
            f"Policy scan produced {len(decision.risk_flags)} risk flag(s).",
            ["security.scan", "secrets.detect", "migration.guard"],
            risks=decision.risk_flags,
        )
    )
    run.agent_actions.append(
        _action(
            "CodeReviewAgent",
            "adversarial_review",
            decision.verdict.value,
            "; ".join(decision.reasons[:3]),
            ["patch.review", "capability.check", "atomicity.check"],
            risks=decision.risk_flags,
        )
    )
    run.status = AgentRunStatus.POLICY_CHECKED

    if decision.verdict == PolicyVerdict.BLOCK:
        run.status = AgentRunStatus.BLOCKED_BY_POLICY
        run.approval = ApprovalRecord(required=False)
        run.message = "Policy Kernel blocked the patch. It cannot be approved or applied."
    elif decision.verdict == PolicyVerdict.REQUIRE_HUMAN_APPROVAL:
        run.status = AgentRunStatus.AWAITING_APPROVAL
        run.approval = ApprovalRecord(required=True)
        run.message = "Patch is proof-ready but requires explicit human approval before repository mutation."
    else:
        run.status = AgentRunStatus.APPROVED
        run.approval = ApprovalRecord(required=False, approved=True, actor="Policy Kernel", reason="Low-risk auto-approval permitted by project policy", approved_at=_now())
        run.message = "Low-risk patch was approved by configured policy and is ready for sandboxed application."

    _write_proposal(run, changes, impacts, run_dir)
    _write_run(run, run_dir)
    return run


def _policy_to_dict(decision: PolicyDecision) -> dict[str, Any]:
    data = asdict(decision)
    data["verdict"] = decision.verdict.value
    return data


def approve_agent_run(
    repo: Path,
    run_id: str,
    actor: str,
    reason: str,
    out_dir: Path | None = None,
) -> tuple[AgentRun, str]:
    run, run_dir = load_agent_run(repo, run_id, out_dir)
    if run.status != AgentRunStatus.AWAITING_APPROVAL or not run.approval or not run.approval.required:
        raise AgentRunError(f"Run {run_id} is not awaiting human approval (status={run.status.value}).")
    if run.policy_decision and run.policy_decision.verdict == PolicyVerdict.BLOCK:
        raise AgentRunError("A policy-blocked patch cannot be approved.")
    token = secrets.token_urlsafe(24)
    run.approval.approved = True
    run.approval.actor = actor.strip()
    run.approval.reason = reason.strip()
    run.approval.approved_at = _now()
    run.approval.token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    run.approval.token_used = False
    run.status = AgentRunStatus.APPROVED
    run.message = "Human approval recorded. The one-time token is required to apply this patch."
    run.agent_actions.append(
        _action(
            "HumanApprover",
            "approve_patch",
            "APPROVED",
            f"{actor} approved the governed patch: {reason}",
            ["approval.sign"],
        )
    )
    approval_data = asdict(run.approval)
    approval_data["token_hash"] = run.approval.token_hash
    _write_json(run_dir / "approval.json", approval_data)
    _write_run(run, run_dir)
    return run, token


def reject_agent_run(
    repo: Path,
    run_id: str,
    actor: str,
    reason: str,
    out_dir: Path | None = None,
) -> AgentRun:
    run, run_dir = load_agent_run(repo, run_id, out_dir)
    if run.status in {AgentRunStatus.VERIFIED, AgentRunStatus.ROLLED_BACK, AgentRunStatus.APPLYING, AgentRunStatus.VERIFYING}:
        raise AgentRunError(f"Run {run_id} cannot be rejected from status {run.status.value}.")
    run.approval = run.approval or ApprovalRecord(required=True)
    run.approval.rejected = True
    run.approval.rejected_at = _now()
    run.approval.actor = actor
    run.approval.reason = reason
    run.status = AgentRunStatus.REJECTED
    run.message = f"Patch rejected by {actor}: {reason}"
    run.agent_actions.append(_action("HumanApprover", "reject_patch", "REJECTED", run.message, ["approval.reject"]))
    _write_json(run_dir / "approval.json", asdict(run.approval))
    _write_run(run, run_dir)
    return run


def _validate_token(run: AgentRun, token: str | None) -> None:
    if not run.approval:
        raise AgentRunError("Approval state is missing.")
    if not run.approval.required:
        return
    if not run.approval.approved:
        raise AgentRunError("Patch has not been approved.")
    if run.approval.token_used:
        raise AgentRunError("Approval token has already been used.")
    if not token:
        raise AgentRunError("A one-time approval token is required.")
    supplied = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not secrets.compare_digest(supplied, run.approval.token_hash):
        raise AgentRunError("Approval token is invalid.")


def apply_agent_run(
    repo: Path,
    run_id: str,
    approval_token: str | None = None,
    out_dir: Path | None = None,
    sandbox: str | None = None,
) -> AgentRun:
    repo = repo.resolve()
    run, run_dir = load_agent_run(repo, run_id, out_dir)
    if run.status != AgentRunStatus.APPROVED:
        raise AgentRunError(f"Run {run_id} is not approved for apply (status={run.status.value}).")
    if not run.policy_decision or run.policy_decision.verdict == PolicyVerdict.BLOCK:
        raise AgentRunError("Policy Kernel did not authorize this patch.")
    _validate_token(run, approval_token)

    config = load_config(repo)
    graph_exclude = sorted(set(config.scan_exclude + config.graph_exclude))
    graph = build_project_graph(repo, repo / ".basalt" / "knowledge-graph.sqlite3", graph_exclude)
    if graph.state_hash != run.base_state_hash:
        run.status = AgentRunStatus.STALE_STATE
        run.current_state_hash = graph.state_hash
        run.message = "Project truth changed after proposal. Re-plan the patch against the new state."
        run.agent_actions.append(
            _action("StateCoordinator", "compare_and_swap", "STALE", run.message, ["state.compare"])
        )
        _write_run(run, run_dir)
        return run

    patch_text = Path(run.candidate_patch_path).read_text(encoding="utf-8")
    changes = parse_unified_diff(patch_text)
    validate_patch_applies(repo, changes)
    backup_dir = run_dir / "backup"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    create_backup(repo, changes, backup_dir)
    run.backup_dir = str(backup_dir)
    run.status = AgentRunStatus.APPLYING
    run.message = "State lock acquired; applying atomic patch."
    run.agent_actions.append(
        _action(
            "StateCoordinator",
            "compare_and_swap",
            "PASS",
            f"Confirmed current_state == base_state {run.base_state_hash[:12]}.",
            ["state.compare", "contract.lock"],
        )
    )
    _write_run(run, run_dir)

    try:
        run.applied_files = apply_patch(repo, changes)
        if run.approval:
            run.approval.token_used = True
            _write_json(run_dir / "approval.json", asdict(run.approval))
        run.status = AgentRunStatus.VERIFYING
        run.message = "Patch applied atomically; full proof is running in an isolated sandbox."
        run.agent_actions.append(
            _action(
                "BasaltOrchestrator",
                "apply_transaction",
                "PASS",
                f"Applied {len(run.applied_files)} file change(s) with rollback snapshot.",
                ["patch.apply", "snapshot.create"],
                run.applied_files,
            )
        )
        _write_run(run, run_dir)

        after_dir = run_dir / "after-verification"
        after_report = verify_repo(repo, sandbox_override=sandbox, output_dir=after_dir)
        after_path = run_dir / "after-proof.json"
        _write_json(after_path, after_report.to_dict())
        run.after_report_path = str(after_path)
        before_data = json.loads(Path(run.before_report_path).read_text(encoding="utf-8"))
        after_data = after_report.to_dict()
        delta = _verification_delta(before_data, after_data)
        run.verification_delta = delta
        _write_delta(delta, run_dir)
        run.agent_actions.append(
            _action(
                "TestingAgent",
                "verify_patch",
                "PASS" if delta.accepted else "FAIL",
                "; ".join(delta.reasons),
                ["sandbox.run", "tests.run", "mutation.run", "security.scan", "proof.compare"],
                [str(after_path), str(run_dir / "verification-delta.json")],
            )
        )

        if not delta.accepted:
            restore_backup(repo, backup_dir)
            run.rollback_performed = True
            run.status = AgentRunStatus.ROLLED_BACK
            run.current_state_hash = run.base_state_hash
            run.message = "Patch failed the no-regression proof gate and was rolled back automatically."
            run.agent_actions.append(
                _action(
                    "LoopGovernor",
                    "reject_and_rollback",
                    "ROLLED_BACK",
                    run.message,
                    ["proof.compare", "snapshot.restore"],
                )
            )
        else:
            refreshed = build_project_graph(
                repo,
                repo / ".basalt" / "knowledge-graph.sqlite3",
                graph_exclude,
                force=True,
            )
            write_graph_artifacts(refreshed, repo / ".basalt")
            run.current_state_hash = refreshed.state_hash
            run.status = AgentRunStatus.VERIFIED
            run.message = "Patch committed as a verified state transaction."
            run.agent_actions.append(
                _action(
                    "BasaltOrchestrator",
                    "commit_transaction",
                    "VERIFIED",
                    f"Committed state {run.base_state_hash[:12]} → {refreshed.state_hash[:12]} after proof.",
                    ["state.commit", "graph.refresh", "context.invalidate"],
                )
            )
            transaction_path = run_dir / "state-transaction.json"
            _write_json(
                transaction_path,
                {
                    "run_id": run.run_id,
                    "base_state": run.base_state_hash,
                    "current_state": refreshed.state_hash,
                    "state_transition": f"{run.base_state_hash} -> {refreshed.state_hash}",
                    "commit_authority": "BasaltOrchestrator",
                    "human_approval_required": bool(run.approval and run.approval.required),
                    "human_approver": run.approval.actor if run.approval else "Policy Kernel",
                    "policy_verdict": run.policy_decision.verdict.value,
                    "proof_accepted": True,
                    "status": run.status.value,
                },
            )
    except Exception as exc:
        if backup_dir.exists():
            try:
                restore_backup(repo, backup_dir)
                run.rollback_performed = True
            except Exception as rollback_exc:  # pragma: no cover - catastrophic path
                run.message = f"Apply failed: {exc}; rollback also failed: {rollback_exc}"
                run.status = AgentRunStatus.FAILED
                _write_run(run, run_dir)
                raise AgentRunError(run.message) from rollback_exc
        run.status = AgentRunStatus.ROLLED_BACK
        run.message = f"Apply or verification failed and repository was rolled back: {exc}"
        run.agent_actions.append(
            _action("LoopGovernor", "exception_rollback", "ROLLED_BACK", run.message, ["snapshot.restore"])
        )
    _write_run(run, run_dir)
    return run


def rollback_agent_run(
    repo: Path,
    run_id: str,
    actor: str,
    reason: str,
    out_dir: Path | None = None,
) -> AgentRun:
    repo = repo.resolve()
    run, run_dir = load_agent_run(repo, run_id, out_dir)
    if run.status != AgentRunStatus.VERIFIED:
        raise AgentRunError(f"Only a VERIFIED run can be manually rolled back (status={run.status.value}).")
    backup_dir = Path(run.backup_dir)
    config = load_config(repo)
    graph_exclude = sorted(set(config.scan_exclude + config.graph_exclude))
    current = build_project_graph(
        repo,
        repo / ".basalt" / "knowledge-graph.sqlite3",
        graph_exclude,
    )
    if run.current_state_hash and current.state_hash != run.current_state_hash:
        raise AgentRunError(
            "Repository changed after this verified transaction. Refusing rollback to avoid overwriting newer work."
        )
    restore_backup(repo, backup_dir)
    graph = build_project_graph(repo, repo / ".basalt" / "knowledge-graph.sqlite3", graph_exclude, force=True)
    write_graph_artifacts(graph, repo / ".basalt")
    run.current_state_hash = graph.state_hash
    run.rollback_performed = True
    run.status = AgentRunStatus.ROLLED_BACK
    run.message = f"Verified transaction rolled back by {actor}: {reason}"
    run.agent_actions.append(
        _action("HumanApprover", "manual_rollback", "ROLLED_BACK", run.message, ["snapshot.restore", "graph.refresh"])
    )
    _write_run(run, run_dir)
    return run


def revise_agent_run(
    repo: Path,
    run_id: str,
    patch_file: Path,
    out_dir: Path | None = None,
) -> AgentRun:
    repo = repo.resolve()
    run, run_dir = load_agent_run(repo, run_id, out_dir)
    if run.status not in {
        AgentRunStatus.AWAITING_APPROVAL,
        AgentRunStatus.REJECTED,
        AgentRunStatus.BLOCKED_BY_POLICY,
        AgentRunStatus.NOT_VERIFIED,
        AgentRunStatus.ROLLED_BACK,
    }:
        raise AgentRunError(f"Run {run_id} cannot be revised from status {run.status.value}.")
    if run.attempt >= run.max_attempts:
        run.status = AgentRunStatus.STUCK
        run.message = f"Loop Governor stopped the run after {run.max_attempts} attempts."
        run.agent_actions.append(
            _action("LoopGovernor", "enforce_attempt_limit", "STUCK", run.message, ["attempt.count"])
        )
        _write_run(run, run_dir)
        return run

    config = load_config(repo)
    graph_exclude = sorted(set(config.scan_exclude + config.graph_exclude))
    graph = build_project_graph(repo, repo / ".basalt" / "knowledge-graph.sqlite3", graph_exclude)
    if graph.state_hash != run.base_state_hash:
        run.status = AgentRunStatus.STALE_STATE
        run.current_state_hash = graph.state_hash
        run.message = "Cannot revise: repository state changed. Create a new plan."
        _write_run(run, run_dir)
        return run

    patch_text = patch_file.resolve().read_text(encoding="utf-8")
    new_hash = patch_sha256(patch_text)
    if new_hash in run.patch_hashes:
        run.status = AgentRunStatus.STUCK
        run.message = "Loop Governor detected an oscillating/repeated patch proposal."
        run.agent_actions.append(
            _action("LoopGovernor", "detect_oscillation", "STUCK", run.message, ["patch.hash_history"])
        )
        _write_run(run, run_dir)
        return run

    changes = parse_unified_diff(patch_text)
    validate_patch_applies(repo, changes)
    run.attempt += 1
    run.patch_hashes.append(new_hash)
    candidate_path = run_dir / f"candidate-attempt-{run.attempt}.patch"
    candidate_path.write_text(patch_text, encoding="utf-8")
    (run_dir / f"candidate-attempt-{run.attempt}.md").write_text(render_patch_summary(changes), encoding="utf-8")
    run.candidate_patch_path = str(candidate_path)
    run.proposal_source = f"revision:{patch_file.resolve()}"

    impacts = _collect_impacts(graph, run.targets, patch_stats(changes).paths)
    run.impacted_files, run.impacted_tests, run.impacted_features = _aggregate_impact(impacts)
    decision = evaluate_patch_policy(
        config,
        run.agent_role,
        changes,
        impacts,
        base_state_hash=run.base_state_hash,
        current_state_hash=graph.state_hash,
    )
    run.policy_decision = decision
    run.verification_delta = None
    run.approval = ApprovalRecord(required=decision.verdict == PolicyVerdict.REQUIRE_HUMAN_APPROVAL)
    run.agent_actions.append(
        _action(
            run.agent_role,
            "revise_patch",
            decision.verdict.value,
            f"Submitted attempt {run.attempt}/{run.max_attempts} with a new patch hash.",
            ["patch.propose", "patch.check"],
            [str(candidate_path)],
            decision.risk_flags,
        )
    )
    if decision.verdict == PolicyVerdict.BLOCK:
        run.status = AgentRunStatus.BLOCKED_BY_POLICY
        run.message = "Revised patch remains blocked by policy."
    elif decision.verdict == PolicyVerdict.REQUIRE_HUMAN_APPROVAL:
        run.status = AgentRunStatus.AWAITING_APPROVAL
        run.message = "Revised patch passed policy and awaits fresh human approval."
    else:
        run.status = AgentRunStatus.APPROVED
        run.approval = ApprovalRecord(required=False, approved=True, actor="Policy Kernel", reason="Low-risk auto-approval permitted", approved_at=_now())
        run.message = "Revised patch is approved by low-risk policy."
    _write_json(run_dir / f"policy-decision-attempt-{run.attempt}.json", _policy_to_dict(decision))
    (run_dir / f"policy-decision-attempt-{run.attempt}.md").write_text(render_policy_markdown(decision), encoding="utf-8")
    _write_proposal(run, changes, impacts, run_dir)
    _write_run(run, run_dir)
    return run
