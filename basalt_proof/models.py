from __future__ import annotations

from dataclasses import dataclass, field, asdict
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


@dataclass
class CommandSpec:
    name: str
    command: str | None
    required: bool = False
    timeout_seconds: int = 300


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


@dataclass
class GraphSymbol:
    file: str
    name: str
    kind: str
    line: int
    signature: str = ""


@dataclass
class GraphEdge:
    source: str
    target: str
    edge_type: str


@dataclass
class KnowledgeGraph:
    files_scanned: int = 0
    symbols: list[GraphSymbol] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)


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
class ProofReport:
    project_name: str
    repo_path: str
    started_at: str
    finished_at: str
    final_status: FinalStatus
    score: int
    sandbox: str = "temp"
    project_type: str = "unknown"
    checks: list[CommandResult] = field(default_factory=list)
    security_findings: list[SecurityFinding] = field(default_factory=list)
    mutations: list[MutationResult] = field(default_factory=list)
    knowledge_graph: KnowledgeGraph = field(default_factory=KnowledgeGraph)
    fix_suggestions: list[FixSuggestion] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[GeneratedArtifact] = field(default_factory=list)
    evidence_dir: str | None = None
    dashboard_path: str | None = None
    patch_plan_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["final_status"] = self.final_status.value
        for check in data["checks"]:
            check["status"] = check["status"].value if hasattr(check["status"], "value") else check["status"]
        for mutation in data["mutations"]:
            mutation["test_status"] = mutation["test_status"].value if hasattr(mutation["test_status"], "value") else mutation["test_status"]
        return data


@dataclass
class BasaltConfig:
    project_name: str
    project_type: str = "unknown"
    commands: list[CommandSpec] = field(default_factory=list)
    mutation_sample: bool = True
    mutation_max: int = 8
    security_scan: str = "basic"
    max_test_failures: int = 0
    block_secrets: bool = True
    block_destructive_migrations: bool = True
    require_human_approval_for_deploy: bool = True
    generate_dashboard: bool = True
    generate_patch_plan: bool = True
    generate_pr_pack: bool = True
    sandbox: str = "temp"
    docker_image: str | None = None

    def command_by_name(self, name: str) -> CommandSpec | None:
        return next((cmd for cmd in self.commands if cmd.name == name), None)
