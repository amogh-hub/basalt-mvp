from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .factory_models import FactoryTask, ModelAssignment


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    model: str
    family: str
    capabilities: tuple[str, ...]
    privacy_modes: tuple[str, ...]
    cost_tier: int
    available: bool = True


DEFAULT_PROFILES = [
    ModelProfile("local", "basalt-deterministic-planner", "basalt-rules", ("planning", "requirements", "routing", "review", "architecture", "security"), ("local", "private", "standard"), 0, True),
    ModelProfile("local", "basalt-template-codegen", "basalt-templates", ("code", "tests", "docs", "ui"), ("local", "private", "standard"), 0, True),
    ModelProfile("openai-compatible", "configured-reasoning-model", "external-reasoning", ("planning", "architecture", "review", "security"), ("standard",), 2, bool(os.environ.get("BASALT_MODEL_ENDPOINT"))),
    ModelProfile("openai-compatible", "configured-code-model", "external-code", ("code", "tests", "ui", "docs"), ("standard",), 1, bool(os.environ.get("BASALT_MODEL_ENDPOINT"))),
]


ROLE_CAPABILITY = {
    "ProductAgent": "requirements",
    "ArchitectureAgent": "architecture",
    "UIDesignAgent": "ui",
    "FrontendAgent": "ui",
    "BackendAgent": "code",
    "DatabaseAgent": "architecture",
    "TestingAgent": "tests",
    "SecurityAgent": "security",
    "CodeReviewAgent": "review",
    "DocumentationAgent": "docs",
    "PerformanceAgent": "review",
    "DevOpsAgent": "code",
}


class ModelRouter:
    def __init__(self, profiles: list[ModelProfile] | None = None) -> None:
        self.profiles = list(profiles or DEFAULT_PROFILES)

    def route(self, task: FactoryTask, privacy_mode: str = "local") -> ModelAssignment:
        capability = ROLE_CAPABILITY.get(task.agent_role, "planning")
        candidates = [
            profile
            for profile in self.profiles
            if profile.available and capability in profile.capabilities and privacy_mode in profile.privacy_modes
        ]
        if not candidates and privacy_mode != "local":
            candidates = [profile for profile in self.profiles if profile.available and capability in profile.capabilities]
        if not candidates:
            raise ValueError(f"No available model can satisfy {task.agent_role}/{capability} in {privacy_mode} mode.")
        selected = sorted(candidates, key=lambda item: (item.cost_tier, item.provider != "local", item.model))[0]
        review_model = ""
        diversity = False
        if task.risk_level in {"HIGH", "CRITICAL"}:
            reviewers = [
                profile
                for profile in self.profiles
                if profile.available
                and "review" in profile.capabilities
                and profile.family != selected.family
                and privacy_mode in profile.privacy_modes
            ]
            if reviewers:
                reviewer = sorted(reviewers, key=lambda item: item.cost_tier)[0]
                review_model = f"{reviewer.provider}/{reviewer.model}"
                diversity = True
        return ModelAssignment(
            task_id=task.task_id,
            agent_role=task.agent_role,
            provider=selected.provider,
            model=selected.model,
            family=selected.family,
            routing_reason=f"Cheapest available {capability}-capable model within {privacy_mode} privacy mode.",
            estimated_cost_usd=0.0 if selected.provider == "local" else 0.01,
            privacy_mode=privacy_mode,
            review_model=review_model,
            diversity_enforced=diversity,
        )

    def route_graph(self, tasks: list[FactoryTask], privacy_mode: str = "local") -> list[ModelAssignment]:
        return [self.route(task, privacy_mode=privacy_mode) for task in tasks]

    def inventory(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.profiles]


class OpenAICompatibleAdapter:
    """Optional provider-neutral JSON chat adapter. It is never called unless explicitly configured."""

    def __init__(self, endpoint: str | None = None, api_key: str | None = None, timeout: int = 60) -> None:
        self.endpoint = endpoint or os.environ.get("BASALT_MODEL_ENDPOINT", "")
        self.api_key = api_key or os.environ.get("BASALT_MODEL_API_KEY", "")
        self.timeout = timeout
        if not self.endpoint:
            raise ValueError("BASALT_MODEL_ENDPOINT is not configured.")

    def complete_json(self, model: str, system: str, user: str) -> dict[str, Any]:
        body = json.dumps(
            {
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Configured model request failed: {exc}") from exc
        content = payload.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Configured model did not return valid JSON.") from exc


def write_model_assignments(assignments: list[ModelAssignment], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "model-assignments.json"
    path.write_text(json.dumps([asdict(item) for item in assignments], indent=2), encoding="utf-8")
    return path
