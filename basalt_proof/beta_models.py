from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class WorkspaceRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    DEVELOPER = "DEVELOPER"
    REVIEWER = "REVIEWER"
    VIEWER = "VIEWER"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DeploymentStatus(str, Enum):
    PACKAGED = "PACKAGED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    PROMOTED = "PROMOTED"
    ROLLED_BACK = "ROLLED_BACK"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class UserRecord:
    user_id: str
    email: str
    display_name: str
    created_at: str
    status: str = "ACTIVE"


@dataclass(frozen=True)
class TeamRecord:
    team_id: str
    name: str
    slug: str
    created_at: str
    created_by: str
    status: str = "ACTIVE"


@dataclass(frozen=True)
class MembershipRecord:
    team_id: str
    user_id: str
    role: WorkspaceRole
    created_at: str
    invited_by: str = ""


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    team_id: str
    name: str
    slug: str
    repo_path: str
    template: str
    created_at: str
    created_by: str
    status: str = "ACTIVE"
    default_branch: str = "main"
    privacy_mode: str = "local"


@dataclass
class BetaJob:
    job_id: str
    project_id: str
    job_type: str
    status: JobStatus
    payload: dict[str, Any]
    created_by: str
    created_at: str
    updated_at: str
    idempotency_key: str = ""
    attempts: int = 0
    max_attempts: int = 2
    worker_id: str = ""
    lease_expires_at: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    cancellation_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class ProviderProfile:
    provider_id: str
    kind: str
    display_name: str
    model: str
    base_url: str
    api_key_env: str
    enabled: bool
    configured: bool
    privacy_modes: tuple[str, ...] = ("local", "standard")
    capabilities: tuple[str, ...] = ("reasoning", "code")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["privacy_modes"] = list(self.privacy_modes)
        data["capabilities"] = list(self.capabilities)
        return data


@dataclass
class DeploymentRecord:
    deployment_id: str
    project_id: str
    environment: str
    status: DeploymentStatus
    artifact_path: str
    artifact_sha256: str
    source_path: str
    proof_status: str
    proof_score: int
    created_by: str
    created_at: str
    updated_at: str
    approved_by: str = ""
    approval_reason: str = ""
    promoted_at: str = ""
    rollback_of: str = ""
    rollback_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data
