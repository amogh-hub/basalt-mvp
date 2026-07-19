from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    SKIPPED = "SKIPPED"
    WEAK_PROOF = "WEAK_PROOF"


class FinalStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    WEAK_PROOF = "WEAK_PROOF"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"


class PolicyVerdict(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_HUMAN_APPROVAL = "REQUIRE_HUMAN_APPROVAL"
    BLOCK = "BLOCK"


class AgentRunStatus(str, Enum):
    PLANNED = "PLANNED"
    CONTEXT_COMPILED = "CONTEXT_COMPILED"
    PATCH_PROPOSED = "PATCH_PROPOSED"
    POLICY_CHECKED = "POLICY_CHECKED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    APPLYING = "APPLYING"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
    NOT_VERIFIED = "NOT_VERIFIED"
    ROLLED_BACK = "ROLLED_BACK"
    STALE_STATE = "STALE_STATE"
    STUCK = "STUCK"
    FAILED = "FAILED"


@dataclass
class CommandSpec:
    name: str
    command: str | None
    required: bool = False
    timeout_seconds: int = 300
    allow_network: bool = False


@dataclass
class CommandResult:
    name: str
    command: str | None
    status: CheckStatus
    exit_code: int | None = None
    duration_ms: int = 0
    stdout_tail: str = ""
    stderr_tail: str = ""
    message: str = ""
    sandbox: str = "temp"


@dataclass
class SecurityFinding:
    level: str
    file: str
    line: int
    rule: str
    message: str


@dataclass
class MutationResult:
    file: str
    mutation_type: str
    original: str
    replacement: str
    survived: bool
    test_status: CheckStatus
    message: str
    line: int | None = None


@dataclass
class GraphFile:
    path: str
    language: str
    hash: str
    size_bytes: int = 0
    modified_ns: int = 0
    is_test: bool = False


@dataclass
class GraphSymbol:
    file: str
    name: str
    kind: str
    line: int
    signature: str = ""
    id: str = ""
    qualified_name: str = ""
    end_line: int = 0
    parent: str = ""
    docstring: str = ""
    return_type: str = ""
    decorators: list[str] = field(default_factory=list)


@dataclass
class GraphEdge:
    source: str
    target: str
    edge_type: str
    source_file: str = ""
    target_file: str = ""
    line: int = 0
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeatureNode:
    id: str
    name: str
    description: str = ""
    files: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    source: str = "inferred"
    confidence: float = 0.5


@dataclass
class TestMapping:
    test_file: str
    source_file: str
    symbol: str = ""
    reason: str = ""
    confidence: float = 0.5


@dataclass
class GraphFreshness:
    fresh: bool
    reason: str
    current_state_hash: str = ""
    stored_state_hash: str = ""
    changed_files: list[str] = field(default_factory=list)
    new_files: list[str] = field(default_factory=list)
    removed_files: list[str] = field(default_factory=list)


@dataclass
class ImpactAnalysis:
    target: str
    found: bool
    risk_level: str
    impacted_files: list[str] = field(default_factory=list)
    impacted_symbols: list[str] = field(default_factory=list)
    impacted_tests: list[str] = field(default_factory=list)
    impacted_features: list[str] = field(default_factory=list)
    impacted_routes: list[str] = field(default_factory=list)
    reasons: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ContextPack:
    context_pack_id: str
    project_state_hash: str
    created_at: str
    task: str
    task_type: str
    agent_role: str
    token_budget: int
    estimated_tokens: int
    target_entities: list[str] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    symbols: list[dict[str, Any]] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    schemas: list[str] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    freshness: dict[str, Any] = field(default_factory=dict)
    selection_reasons: list[dict[str, Any]] = field(default_factory=list)
    context_precision_score: float = 0.0


@dataclass
class KnowledgeGraph:
    graph_version: str = "2.1"
    parser_version: str = ""
    state_hash: str = ""
    built_at: str = ""
    fresh: bool = False
    files_scanned: int = 0
    files: list[GraphFile] = field(default_factory=list)
    symbols: list[GraphSymbol] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    features: list[FeatureNode] = field(default_factory=list)
    test_mappings: list[TestMapping] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)
    routes: list[str] = field(default_factory=list)
    schemas: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    reused_files: list[str] = field(default_factory=list)
    removed_files: list[str] = field(default_factory=list)
    store_path: str | None = None


@dataclass
class FixSuggestion:
    title: str
    severity: str
    category: str
    problem: str
    recommended_change: str
    affected_files: list[str] = field(default_factory=list)
    verification_command: str | None = None


@dataclass
class GeneratedArtifact:
    name: str
    path: str
    purpose: str


@dataclass
class PatchHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str] = field(default_factory=list)


@dataclass
class PatchFileChange:
    old_path: str
    new_path: str
    change_type: str
    hunks: list[PatchHunk] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0


@dataclass
class PatchStats:
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    changed_lines: int = 0
    paths: list[str] = field(default_factory=list)
    test_only: bool = False
    contains_binary: bool = False


@dataclass
class PolicyDecision:
    verdict: PolicyVerdict
    risk_level: str
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    required_approvals: list[str] = field(default_factory=list)
    required_locks: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    denied_capabilities: list[str] = field(default_factory=list)
    patch_stats: PatchStats = field(default_factory=PatchStats)


@dataclass
class AgentAction:
    agent_role: str
    action: str
    status: str
    summary: str
    started_at: str
    finished_at: str
    tools_used: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)


@dataclass
class ApprovalRecord:
    required: bool
    approved: bool = False
    actor: str = ""
    reason: str = ""
    approved_at: str = ""
    token_hash: str = ""
    token_used: bool = False
    rejected: bool = False
    rejected_at: str = ""


@dataclass
class VerificationDelta:
    before_status: str
    after_status: str
    before_score: int
    after_score: int
    score_delta: int
    before_survived_mutations: int
    after_survived_mutations: int
    before_high_findings: int
    after_high_findings: int
    before_failed_checks: int
    after_failed_checks: int
    improved: bool
    accepted: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class AgentRun:
    run_id: str
    task: str
    agent_role: str
    repo_path: str
    created_at: str
    updated_at: str
    status: AgentRunStatus
    base_state_hash: str
    current_state_hash: str = ""
    context_pack_id: str = ""
    targets: list[str] = field(default_factory=list)
    candidate_patch_path: str = ""
    proposal_source: str = ""
    attempt: int = 1
    max_attempts: int = 3
    patch_hashes: list[str] = field(default_factory=list)
    policy_decision: PolicyDecision | None = None
    approval: ApprovalRecord | None = None
    agent_actions: list[AgentAction] = field(default_factory=list)
    impacted_files: list[str] = field(default_factory=list)
    impacted_tests: list[str] = field(default_factory=list)
    impacted_features: list[str] = field(default_factory=list)
    before_report_path: str = ""
    after_report_path: str = ""
    verification_delta: VerificationDelta | None = None
    backup_dir: str = ""
    applied_files: list[str] = field(default_factory=list)
    rollback_performed: bool = False
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        if self.policy_decision:
            data["policy_decision"]["verdict"] = self.policy_decision.verdict.value
        return data


@dataclass
class ProofReport:
    project_name: str
    repo_path: str
    started_at: str
    finished_at: str
    final_status: FinalStatus
    score: int
    sandbox: str = "temp"
    sandbox_requested: str = "temp"
    sandbox_fallback_reason: str | None = None
    project_type: str = "unknown"
    checks: list[CommandResult] = field(default_factory=list)
    security_findings: list[SecurityFinding] = field(default_factory=list)
    mutations: list[MutationResult] = field(default_factory=list)
    knowledge_graph: KnowledgeGraph = field(default_factory=KnowledgeGraph)
    fix_suggestions: list[FixSuggestion] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[GeneratedArtifact] = field(default_factory=list)
    score_breakdown: list[dict[str, Any]] = field(default_factory=list)
    evidence_dir: str | None = None
    dashboard_path: str | None = None
    patch_plan_path: str | None = None
    basalt_version: str = "2.5.0b4"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["final_status"] = self.final_status.value
        for check in data["checks"]:
            check["status"] = check["status"].value if hasattr(check["status"], "value") else check["status"]
        for mutation in data["mutations"]:
            mutation["test_status"] = (
                mutation["test_status"].value
                if hasattr(mutation["test_status"], "value")
                else mutation["test_status"]
            )
        return data


@dataclass
class BasaltConfig:
    project_name: str
    project_type: str = "unknown"
    commands: list[CommandSpec] = field(default_factory=list)
    mutation_sample: bool = True
    mutation_max: int = 8
    mutation_per_file: int = 2
    mutation_test_command: str | None = None
    mutation_include: list[str] = field(default_factory=list)
    mutation_exclude: list[str] = field(default_factory=list)
    security_scan: str = "basic"
    scan_exclude: list[str] = field(default_factory=list)
    max_test_failures: int = 0
    min_verified_score: int = 80
    block_secrets: bool = True
    block_destructive_migrations: bool = True
    require_human_approval_for_deploy: bool = True
    generate_dashboard: bool = True
    generate_patch_plan: bool = True
    generate_pr_pack: bool = True
    sandbox: str = "auto"
    docker_image: str | None = None
    docker_network: str = "install-only"
    docker_fallback: bool = True
    graph_auto_refresh: bool = True
    graph_exclude: list[str] = field(default_factory=list)
    context_token_budget: int = 12000
    agents_enabled: bool = True
    agent_max_files: int = 8
    agent_max_changed_lines: int = 400
    agent_max_attempts: int = 3
    agent_require_human_approval_for_source: bool = True
    agent_allow_test_only_auto_apply: bool = False
    agent_protected_paths: list[str] = field(default_factory=list)
    agent_allowed_roles: list[str] = field(default_factory=list)

    def command_by_name(self, name: str) -> CommandSpec | None:
        return next((cmd for cmd in self.commands if cmd.name == name), None)
