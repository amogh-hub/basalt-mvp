from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .factory_models import EngineeringPlan, ExecutionEpoch, FactoryTask, ProductBlueprint


EPOCHS = {
    1: ("Shared Truth", "Lock requirements, contracts, schemas, security boundaries, and design rules."),
    2: ("Implementation", "Build dependency-safe product slices against settled contracts."),
    3: ("Verification", "Prove behavior, security, test strength, accessibility, and contract integrity."),
    4: ("Hardening", "Improve maintainability, documentation, performance, and design consistency."),
    5: ("Release", "Assemble verified artifacts, produce evidence, and prepare a reversible release."),
}


@dataclass
class PatchProposalRecord:
    patch_id: str
    task_id: str
    files: list[str]
    locks: list[str] = field(default_factory=list)
    risk_level: str = "LOW"


@dataclass
class PatchBatch:
    batch_id: str
    patch_ids: list[str]
    files: list[str]
    locks: list[str]
    risk_level: str


def _task(
    task_id: str,
    title: str,
    role: str,
    epoch: int,
    *,
    dependencies: list[str] | None = None,
    requirement_ids: list[str] | None = None,
    target_scopes: list[str] | None = None,
    locks: list[str] | None = None,
    risk: str = "LOW",
    artifact: str = "",
) -> FactoryTask:
    return FactoryTask(
        task_id=task_id,
        title=title,
        description=title,
        agent_role=role,
        epoch=epoch,
        epoch_name=EPOCHS[epoch][0],
        dependencies=list(dependencies or []),
        requirement_ids=list(requirement_ids or []),
        target_scopes=list(target_scopes or []),
        required_locks=list(locks or []),
        risk_level=risk,
        expected_artifact=artifact,
    )


def build_task_graph(blueprint: ProductBlueprint, plan: EngineeringPlan) -> tuple[list[FactoryTask], list[ExecutionEpoch]]:
    all_requirements = [item.id for item in blueprint.requirements + blueprint.non_functional_requirements]
    lock_names = [item.name for item in plan.contract_locks]
    tasks: list[FactoryTask] = [
        _task("TASK-ARCH-001", "Finalize architecture and shared contracts", "ArchitectureAgent", 1, requirement_ids=all_requirements, target_scopes=["architecture", "contracts"], locks=lock_names, risk="HIGH", artifact="architecture-contract.json"),
        _task("TASK-PROD-001", "Lock product requirements and acceptance criteria", "ProductAgent", 1, requirement_ids=all_requirements, target_scopes=["requirements", "flows"], locks=["PRODUCT_REQUIREMENTS"], risk="HIGH", artifact="product-blueprint.json"),
        _task("TASK-UI-001", "Apply Basalt Obsidian design system", "UIDesignAgent", 1, target_scopes=["design-tokens", "components"], locks=["BASALT_DESIGN_SYSTEM"], risk="MEDIUM", artifact="basalt-design-tokens.json"),
    ]
    if "DATA_SCHEMA" in lock_names:
        tasks.append(_task("TASK-DATA-001", "Define compatible data schema", "DatabaseAgent", 1, dependencies=["TASK-ARCH-001"], target_scopes=["schema"], locks=["DATA_SCHEMA"], risk="HIGH", artifact="data-contract.json"))

    shared_dependencies = [item.task_id for item in tasks if item.epoch == 1]
    tasks.extend(
        [
            _task("TASK-BE-001", "Implement domain and service layer", "BackendAgent", 2, dependencies=shared_dependencies, requirement_ids=all_requirements, target_scopes=["app", "api"], locks=[name for name in lock_names if name in {"API_CONTRACT", "AUTH_CONTRACT", "PAYMENT_CONTRACT", "DATA_SCHEMA"}], risk="HIGH" if any(item.risk_level in {"HIGH", "CRITICAL"} for item in blueprint.features) else "MEDIUM", artifact="backend-implementation"),
            _task("TASK-FE-001", "Implement product interface", "FrontendAgent", 2, dependencies=["TASK-ARCH-001", "TASK-UI-001"], requirement_ids=all_requirements, target_scopes=["web", "ui"], locks=["BASALT_DESIGN_SYSTEM", *( ["API_CONTRACT"] if "API_CONTRACT" in lock_names else [] )], risk="MEDIUM", artifact="frontend-implementation"),
            _task("TASK-TEST-001", "Implement requirement-linked automated tests", "TestingAgent", 3, dependencies=["TASK-BE-001", "TASK-FE-001"], requirement_ids=all_requirements, target_scopes=["tests"], risk="MEDIUM", artifact="test-suite"),
            _task("TASK-SEC-001", "Run adversarial security review", "SecurityAgent", 3, dependencies=["TASK-BE-001", "TASK-FE-001"], requirement_ids=[item.id for item in blueprint.non_functional_requirements if item.risk_level in {"HIGH", "CRITICAL"}], target_scopes=["security", "policy"], risk="HIGH", artifact="security-review.json"),
            _task("TASK-REV-001", "Review implementation against locked contracts", "CodeReviewAgent", 3, dependencies=["TASK-TEST-001", "TASK-SEC-001"], target_scopes=["review", "contracts"], locks=lock_names, risk="HIGH", artifact="review-verdict.json"),
            _task("TASK-DOC-001", "Generate operator and developer documentation", "DocumentationAgent", 4, dependencies=["TASK-REV-001"], target_scopes=["docs"], risk="LOW", artifact="README.md"),
            _task("TASK-PERF-001", "Check maintainability and performance baseline", "PerformanceAgent", 4, dependencies=["TASK-REV-001"], target_scopes=["performance", "quality"], risk="MEDIUM", artifact="hardening-report.json"),
            _task("TASK-REL-001", "Assemble verified release and provenance manifest", "DevOpsAgent", 5, dependencies=["TASK-DOC-001", "TASK-PERF-001"], target_scopes=["release", "proof"], risk="HIGH", artifact="factory-manifest.json"),
        ]
    )
    validate_task_graph(tasks)
    epochs = [
        ExecutionEpoch(number=number, name=name, purpose=purpose, task_ids=[task.task_id for task in tasks if task.epoch == number])
        for number, (name, purpose) in EPOCHS.items()
    ]
    return tasks, epochs


def validate_task_graph(tasks: list[FactoryTask]) -> None:
    ids = {task.task_id for task in tasks}
    if len(ids) != len(tasks):
        raise ValueError("Task graph contains duplicate task identifiers.")
    for task in tasks:
        missing = [item for item in task.dependencies if item not in ids]
        if missing:
            raise ValueError(f"Task {task.task_id} has missing dependencies: {', '.join(missing)}")
        for dependency in task.dependencies:
            dep = next(item for item in tasks if item.task_id == dependency)
            if dep.epoch > task.epoch:
                raise ValueError(f"Task {task.task_id} depends on later epoch task {dependency}.")
    visiting: set[str] = set()
    visited: set[str] = set()
    lookup = {item.task_id: item for item in tasks}

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError("Task graph contains a dependency cycle.")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in lookup[task_id].dependencies:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in ids:
        visit(task_id)


def aggregate_patch_proposals(proposals: list[PatchProposalRecord]) -> list[PatchBatch]:
    remaining = list(proposals)
    batches: list[PatchBatch] = []
    severity = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    while remaining:
        group = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            group_files = set().union(*(set(item.files) for item in group))
            group_locks = set().union(*(set(item.locks) for item in group))
            for candidate in list(remaining):
                if group_files.intersection(candidate.files) or group_locks.intersection(candidate.locks):
                    group.append(candidate)
                    remaining.remove(candidate)
                    changed = True
        risk = max((item.risk_level for item in group), key=lambda item: severity.get(item, 0))
        batches.append(
            PatchBatch(
                batch_id=f"batch-{len(batches)+1:03d}",
                patch_ids=[item.patch_id for item in group],
                files=sorted(set().union(*(set(item.files) for item in group))),
                locks=sorted(set().union(*(set(item.locks) for item in group))),
                risk_level=risk,
            )
        )
    return batches


def write_task_graph_artifacts(tasks: list[FactoryTask], epochs: list[ExecutionEpoch], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"tasks": [asdict(item) for item in tasks], "epochs": [asdict(item) for item in epochs]}
    json_path = out_dir / "factory-task-graph.json"
    md_path = out_dir / "factory-task-graph.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = ["# Dependency-Aware Factory Task Graph", ""]
    for epoch in epochs:
        lines.extend([f"## Epoch {epoch.number} — {epoch.name}", epoch.purpose, ""])
        for task in [item for item in tasks if item.epoch == epoch.number]:
            deps = ", ".join(task.dependencies) or "none"
            lines.append(f"- `{task.task_id}` **{task.title}** — {task.agent_role}; dependencies: {deps}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return [json_path, md_path]
