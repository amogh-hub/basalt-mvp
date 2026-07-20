from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class FactoryRunStatus(str, Enum):
    INTAKE = "INTAKE"
    BLUEPRINTED = "BLUEPRINTED"
    PREVENTION_LOCKED = "PREVENTION_LOCKED"
    PLANNED = "PLANNED"
    BUILDING = "BUILDING"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class Assumption:
    id: str
    text: str
    confidence: float
    risk: str
    source: str = "product-brain"
    status: str = "OPEN"


@dataclass
class ProductRequirement:
    id: str
    title: str
    statement: str
    priority: str = "MUST"
    risk_level: str = "LOW"
    acceptance_criteria: list[str] = field(default_factory=list)
    source_feature: str = ""


@dataclass
class ProductFeature:
    id: str
    name: str
    description: str
    risk_level: str = "LOW"
    requirements: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class UserFlow:
    id: str
    name: str
    actor: str
    steps: list[str] = field(default_factory=list)
    success_condition: str = ""


@dataclass
class ProductBlueprint:
    blueprint_id: str
    name: str
    prompt: str
    template: str
    target_users: list[str]
    created_at: str
    version: int = 1
    product_summary: str = ""
    features: list[ProductFeature] = field(default_factory=list)
    requirements: list[ProductRequirement] = field(default_factory=list)
    user_flows: list[UserFlow] = field(default_factory=list)
    non_functional_requirements: list[ProductRequirement] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    architecture_hint: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""


@dataclass
class ContractLock:
    name: str
    scope: str
    reason: str
    risk_level: str
    owner: str = "ProductBrain"
    state: str = "LOCKED"


@dataclass
class TestPlanItem:
    id: str
    requirement_id: str
    test_type: str
    description: str
    required: bool = True
    owner_role: str = "TestingAgent"


@dataclass
class EngineeringPlan:
    plan_id: str
    blueprint_id: str
    created_at: str
    status: str
    architecture: dict[str, Any]
    contract_locks: list[ContractLock] = field(default_factory=list)
    test_plan: list[TestPlanItem] = field(default_factory=list)
    risk_controls: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    state_hash: str = ""


@dataclass
class FactoryTask:
    task_id: str
    title: str
    description: str
    agent_role: str
    epoch: int
    epoch_name: str
    dependencies: list[str] = field(default_factory=list)
    requirement_ids: list[str] = field(default_factory=list)
    target_scopes: list[str] = field(default_factory=list)
    required_locks: list[str] = field(default_factory=list)
    risk_level: str = "LOW"
    expected_artifact: str = ""
    status: str = "PLANNED"


@dataclass
class ExecutionEpoch:
    number: int
    name: str
    purpose: str
    task_ids: list[str] = field(default_factory=list)
    status: str = "PLANNED"


@dataclass
class ModelAssignment:
    task_id: str
    agent_role: str
    provider: str
    model: str
    family: str
    routing_reason: str
    estimated_cost_usd: float = 0.0
    privacy_mode: str = "local"
    review_model: str = ""
    diversity_enforced: bool = False


@dataclass
class AgentExecutionRecord:
    task_id: str
    agent_role: str
    status: str
    started_at: str
    finished_at: str
    summary: str
    artifacts: list[str] = field(default_factory=list)
    model_assignment: dict[str, Any] = field(default_factory=dict)
    risk_flags: list[str] = field(default_factory=list)
    execution_mode: str = "DETERMINISTIC_LOCAL"
    dependency_ids: list[str] = field(default_factory=list)


@dataclass
class FactoryRun:
    run_id: str
    repo_path: str
    product_name: str
    prompt: str
    template: str
    created_at: str
    updated_at: str
    status: FactoryRunStatus
    blueprint_path: str = ""
    engineering_plan_path: str = ""
    task_graph_path: str = ""
    manifest_path: str = ""
    target_path: str = ""
    staging_path: str = ""
    base_state_version: int = 0
    committed_state_version: int = 0
    project_state_hash: str = ""
    proof_report_path: str = ""
    proof_status: str = ""
    proof_score: int = 0
    tasks: list[FactoryTask] = field(default_factory=list)
    epochs: list[ExecutionEpoch] = field(default_factory=list)
    model_assignments: list[ModelAssignment] = field(default_factory=list)
    agent_records: list[AgentExecutionRecord] = field(default_factory=list)
    required_locks: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
