from __future__ import annotations

import fnmatch
import re
from pathlib import PurePosixPath
from typing import Iterable

from .models import BasaltConfig, ImpactAnalysis, PatchFileChange, PolicyDecision, PolicyVerdict
from .patch_engine import added_lines, patch_stats
from .security import AUTH_RISK_PATTERNS, DESTRUCTIVE_SQL_PATTERNS, SECRET_PATTERNS


READ_ONLY_ROLES = {"SecurityAgent", "CodeReviewAgent", "ProductAgent", "UXAgent"}
GENERAL_SOURCE_ROLES = {"ImplementationAgent", "BuilderAgent", "BackendAgent"}
KNOWN_ROLES = {
    "ImplementationAgent",
    "BuilderAgent",
    "FrontendAgent",
    "BackendAgent",
    "DatabaseAgent",
    "TestingAgent",
    "SecurityAgent",
    "DevOpsAgent",
    "DocumentationAgent",
    "CodeReviewAgent",
    "ProductAgent",
    "UXAgent",
}

ROLE_TOOLS = {
    "ImplementationAgent": ["context.read", "graph.query", "patch.propose", "sandbox.verify"],
    "BuilderAgent": ["context.read", "graph.query", "patch.propose", "sandbox.verify"],
    "FrontendAgent": ["context.read", "frontend.edit", "frontend.test", "sandbox.verify"],
    "BackendAgent": ["context.read", "backend.edit", "backend.test", "sandbox.verify"],
    "DatabaseAgent": ["context.read", "schema.propose", "migration.validate", "sandbox.verify"],
    "TestingAgent": ["context.read", "test.write", "mutation.feedback", "sandbox.verify"],
    "SecurityAgent": ["context.read", "security.scan", "policy.review"],
    "DevOpsAgent": ["context.read", "ci.propose", "rollback.plan", "sandbox.verify"],
    "DocumentationAgent": ["context.read", "docs.write"],
    "CodeReviewAgent": ["context.read", "patch.review", "policy.review"],
    "ProductAgent": ["context.read", "requirement.review", "risk.map"],
    "UXAgent": ["context.read", "flow.review"],
}

_DENIED_BY_ROLE = {
    "TestingAgent": ["production_source.write", "database.write", "deployment.write"],
    "FrontendAgent": ["database.write", "deployment.write"],
    "BackendAgent": ["production_secrets.read", "deployment.write"],
    "DatabaseAgent": ["destructive_migration.execute", "deployment.write"],
    "DevOpsAgent": ["production_deploy.execute"],
    "DocumentationAgent": ["production_source.write", "architecture.change"],
    "SecurityAgent": ["patch.apply", "shipping_code"],
    "CodeReviewAgent": ["patch.apply", "code.execute_outside_sandbox"],
}

_SECRET_FILE_RE = re.compile(r"(^|/)(\.env(?:\..*)?|.*\.(?:pem|key|p12|pfx))$", re.IGNORECASE)
_FRONTEND_RE = re.compile(r"(^|/)(frontend|web|client|ui|src/components|src/pages|app)/", re.IGNORECASE)
_TEST_RE = re.compile(r"(^|/)(tests?|__tests__)/|(^|/)(test_.*\.py|.*_(?:test|spec)\.py|.*\.(?:test|spec)\.[jt]sx?)$", re.IGNORECASE)
_DOC_RE = re.compile(r"(^|/)(docs?/|README(?:\.[^/]*)?$|CHANGELOG(?:\.[^/]*)?$|.*\.md$)", re.IGNORECASE)
_DB_RE = re.compile(r"(^|/)(db|database|migrations?|schema)/|\.sql$", re.IGNORECASE)
_DEVOPS_RE = re.compile(r"(^|/)(\.github/workflows|infra|deploy|deployment|terraform|k8s|helm)/|(^|/)(Dockerfile|docker-compose[^/]*)$", re.IGNORECASE)
_AUTH_RE = re.compile(r"(^|/|[_-])(auth|login|session|permission|role|rbac|oauth|jwt)([_./-]|$)", re.IGNORECASE)
_PAYMENT_RE = re.compile(r"(^|/|[_-])(payment|billing|stripe|checkout|invoice)([_./-]|$)", re.IGNORECASE)
_CONTRACT_RE = re.compile(r"(^|/)(schemas?|contracts?|types?)/|(?:schema|contract|openapi|swagger)\.(?:json|ya?ml)$", re.IGNORECASE)
_LOCKFILE_RE = re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|uv\.lock)$", re.IGNORECASE)

_DANGEROUS_ADDED_PATTERNS = [
    ("dangerous_shell", re.compile(r"(?i)(rm\s+-rf|curl\s+[^\n|]*\|\s*(?:sh|bash)|wget\s+[^\n|]*\|\s*(?:sh|bash)|sudo\s+|chmod\s+777)")),
    ("dynamic_eval", re.compile(r"(?i)\b(eval|exec)\s*\(")),
    ("shell_true", re.compile(r"(?i)shell\s*=\s*true")),
]


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    normalized = path.strip("/")
    for pattern in patterns:
        candidate = pattern.strip().strip("/")
        if not candidate:
            continue
        if fnmatch.fnmatch(normalized, candidate) or fnmatch.fnmatch(normalized, candidate + "/**"):
            return True
        if normalized == candidate or normalized.startswith(candidate + "/"):
            return True
    return False


def _role_allows_path(role: str, path: str) -> bool:
    if role in GENERAL_SOURCE_ROLES:
        return not _DB_RE.search(path) and not _DEVOPS_RE.search(path)
    if role == "FrontendAgent":
        return bool(_FRONTEND_RE.search(path) or _TEST_RE.search(path) or _DOC_RE.search(path))
    if role == "TestingAgent":
        return bool(_TEST_RE.search(path))
    if role == "DatabaseAgent":
        return bool(_DB_RE.search(path) or _TEST_RE.search(path) or _DOC_RE.search(path))
    if role == "DevOpsAgent":
        return bool(_DEVOPS_RE.search(path) or _TEST_RE.search(path) or _DOC_RE.search(path))
    if role == "DocumentationAgent":
        return bool(_DOC_RE.search(path))
    return False


def _impact_risk(impacts: Iterable[ImpactAnalysis]) -> str:
    levels = {item.risk_level.upper() for item in impacts}
    if "HIGH" in levels:
        return "HIGH"
    if "MEDIUM" in levels:
        return "MEDIUM"
    return "LOW"


def evaluate_patch_policy(
    config: BasaltConfig,
    role: str,
    changes: list[PatchFileChange],
    impacts: list[ImpactAnalysis],
    base_state_hash: str,
    current_state_hash: str,
) -> PolicyDecision:
    stats = patch_stats(changes)
    reasons: list[str] = []
    flags: list[str] = []
    approvals: list[str] = []
    locks: list[str] = []
    blocked = False

    allowed_roles = set(config.agent_allowed_roles or KNOWN_ROLES)
    if not config.agents_enabled:
        blocked = True
        reasons.append("Agent-assisted fixes are disabled by project policy.")
        flags.append("agents_disabled")
    if role not in KNOWN_ROLES or role not in allowed_roles:
        blocked = True
        reasons.append(f"Agent role `{role}` is not enabled for this project.")
        flags.append("unknown_or_disabled_role")
    if role in READ_ONLY_ROLES:
        blocked = True
        reasons.append(f"{role} is review-only and cannot author or apply code patches.")
        flags.append("capability_scope_violation")

    if not base_state_hash or base_state_hash != current_state_hash:
        blocked = True
        reasons.append("Patch base state does not match current project truth.")
        flags.append("stale_base_state")

    if stats.files_changed > config.agent_max_files:
        blocked = True
        reasons.append(
            f"Patch changes {stats.files_changed} files, exceeding the atomic patch limit of {config.agent_max_files}."
        )
        flags.append("atomic_file_limit_exceeded")
    if stats.changed_lines > config.agent_max_changed_lines:
        blocked = True
        reasons.append(
            f"Patch changes {stats.changed_lines} lines, exceeding the atomic line limit of {config.agent_max_changed_lines}."
        )
        flags.append("atomic_line_limit_exceeded")

    for change in changes:
        path = change.new_path if change.new_path != "/dev/null" else change.old_path
        if change.change_type == "delete":
            blocked = True
            reasons.append(f"Phase 3 does not allow agent-authored file deletion: `{path}`.")
            flags.append("file_deletion")
        if _SECRET_FILE_RE.search(path):
            blocked = True
            reasons.append(f"Secret-bearing file is outside every agent capability: `{path}`.")
            flags.append("secret_file")
        if _matches_any(path, config.agent_protected_paths):
            blocked = True
            reasons.append(f"Project policy protects `{path}` from agent modification.")
            flags.append("protected_path")
        if role in KNOWN_ROLES and role not in READ_ONLY_ROLES and not _role_allows_path(role, path):
            blocked = True
            reasons.append(f"{role} does not have capability to modify `{path}`.")
            flags.append("capability_scope_violation")
        if _LOCKFILE_RE.search(path):
            blocked = True
            reasons.append(f"Lockfiles cannot be edited by an agent patch in Phase 3: `{path}`.")
            flags.append("lockfile_change")
        if _DEVOPS_RE.search(path):
            flags.append("deployment_or_ci_change")
            locks.append("DEPLOYMENT_CONFIG")
            approvals.extend(["human", "devops_review"])
        if _DB_RE.search(path):
            flags.append("database_schema_change")
            locks.append("DATABASE_SCHEMA")
            approvals.extend(["human", "database_review"])
        if _AUTH_RE.search(path):
            flags.append("auth_or_permission_change")
            locks.append("AUTH_CONTRACT")
            approvals.extend(["human", "architecture_review", "security_review"])
        if _PAYMENT_RE.search(path):
            flags.append("payment_logic_change")
            locks.append("PAYMENT_LOGIC")
            approvals.extend(["human", "architecture_review", "security_review"])
        if _CONTRACT_RE.search(path):
            flags.append("contract_change")
            locks.append("API_CONTRACT")
            approvals.extend(["human", "architecture_review"])

    for path, line_number, line in added_lines(changes):
        for rule, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                blocked = True
                reasons.append(f"Possible secret introduced in `{path}:{line_number}` ({rule}).")
                flags.append("secret_introduction")
        for rule, pattern in DESTRUCTIVE_SQL_PATTERNS:
            if pattern.search(line):
                blocked = True
                reasons.append(f"Destructive migration statement introduced in `{path}:{line_number}` ({rule}).")
                flags.append("destructive_migration")
        for rule, pattern in AUTH_RISK_PATTERNS:
            if pattern.search(line):
                blocked = True
                reasons.append(f"Security downgrade pattern introduced in `{path}:{line_number}` ({rule}).")
                flags.append("security_downgrade")
        for rule, pattern in _DANGEROUS_ADDED_PATTERNS:
            if pattern.search(line):
                blocked = True
                reasons.append(f"Dangerous code pattern introduced in `{path}:{line_number}` ({rule}).")
                flags.append(rule)

    impact_risk = _impact_risk(impacts)
    if impact_risk == "HIGH":
        flags.append("high_change_impact")
        approvals.extend(["human", "code_review"])
    elif impact_risk == "MEDIUM":
        flags.append("medium_change_impact")
        approvals.append("human")

    if blocked:
        verdict = PolicyVerdict.BLOCK
        risk_level = "HIGH"
    else:
        source_change = not stats.test_only
        requires_human = (
            source_change and config.agent_require_human_approval_for_source
        ) or (stats.test_only and not config.agent_allow_test_only_auto_apply) or bool(approvals)
        if requires_human:
            verdict = PolicyVerdict.REQUIRE_HUMAN_APPROVAL
            approvals.append("human")
        else:
            verdict = PolicyVerdict.ALLOW
        risk_level = "HIGH" if impact_risk == "HIGH" or locks else ("MEDIUM" if impact_risk == "MEDIUM" or source_change else "LOW")
        if not reasons:
            reasons.append(
                "Patch is within the agent capability boundary and may proceed only through sandbox verification."
            )

    return PolicyDecision(
        verdict=verdict,
        risk_level=risk_level,
        reasons=list(dict.fromkeys(reasons)),
        risk_flags=list(dict.fromkeys(flags)),
        required_approvals=list(dict.fromkeys(approvals)),
        required_locks=list(dict.fromkeys(locks)),
        allowed_tools=ROLE_TOOLS.get(role, []),
        denied_capabilities=_DENIED_BY_ROLE.get(role, []),
        patch_stats=stats,
    )


def render_policy_markdown(decision: PolicyDecision) -> str:
    lines = [
        "# Basalt Policy Kernel Decision",
        "",
        f"- Verdict: `{decision.verdict.value}`",
        f"- Risk: `{decision.risk_level}`",
        f"- Files: `{decision.patch_stats.files_changed}`",
        f"- Changed lines: `{decision.patch_stats.changed_lines}`",
        f"- Test-only: `{decision.patch_stats.test_only}`",
        "",
        "## Reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in decision.reasons)
    lines.extend(["", "## Risk flags", ""])
    if decision.risk_flags:
        lines.extend(f"- `{flag}`" for flag in decision.risk_flags)
    else:
        lines.append("- None")
    lines.extend(["", "## Required approvals", ""])
    if decision.required_approvals:
        lines.extend(f"- `{approval}`" for approval in decision.required_approvals)
    else:
        lines.append("- None")
    lines.extend(["", "## Required locks", ""])
    if decision.required_locks:
        lines.extend(f"- `{lock}`" for lock in decision.required_locks)
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"
