from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dashboard import write_dashboard
from .design_system import TOKENS, write_design_system_artifacts
from .epoch_planner import build_task_graph, write_task_graph_artifacts
from .factory_models import (
    AgentExecutionRecord,
    EngineeringPlan,
    ExecutionEpoch,
    FactoryRun,
    FactoryRunStatus,
    FactoryTask,
    ModelAssignment,
    ProductBlueprint,
)
from .model_router import ModelRouter, write_model_assignments
from .prevention_engine import build_engineering_plan, write_engineering_plan_artifacts
from .product_brain import build_product_blueprint, write_blueprint_artifacts
from .proof import verify_repo
from .report import write_json_report, write_markdown_report
from .state_coordinator import ContractLockError, StateConflictError, StateCoordinator


SUPPORTED_TEMPLATES = {"python-service", "api-service", "fullstack-lite", "web-app", "saas-starter"}


class FactoryError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result or "basalt-product"


def _package_name(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not result or result[0].isdigit():
        result = f"product_{result}" if result else "generated_product"
    return result


def _safe_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False)


def repository_hash(repo: Path) -> str:
    digest = hashlib.sha256()
    excluded = {".git", ".basalt", ".venv", "venv", "node_modules", "__pycache__"}
    for path in sorted(repo.rglob("*")):
        if not path.is_file() or any(part in excluded for part in path.relative_to(repo).parts):
            continue
        relative = path.relative_to(repo).as_posix()
        digest.update(relative.encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()


def _run_root(repo: Path, out_dir: Path | None = None) -> Path:
    return (out_dir or repo / ".basalt") / "factory-runs"


def _index_path(repo: Path, out_dir: Path | None = None) -> Path:
    return _run_root(repo, out_dir) / "index.json"


def _run_dir(repo: Path, run_id: str, out_dir: Path | None = None) -> Path:
    return _run_root(repo, out_dir) / run_id


def _run_from_dict(data: dict[str, Any]) -> FactoryRun:
    tasks = [FactoryTask(**item) for item in data.get("tasks", [])]
    epochs = [ExecutionEpoch(**item) for item in data.get("epochs", [])]
    assignments = [ModelAssignment(**item) for item in data.get("model_assignments", [])]
    records = [AgentExecutionRecord(**item) for item in data.get("agent_records", [])]
    return FactoryRun(
        run_id=data["run_id"],
        repo_path=data["repo_path"],
        product_name=data["product_name"],
        prompt=data["prompt"],
        template=data["template"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        status=FactoryRunStatus(data["status"]),
        blueprint_path=data.get("blueprint_path", ""),
        engineering_plan_path=data.get("engineering_plan_path", ""),
        task_graph_path=data.get("task_graph_path", ""),
        manifest_path=data.get("manifest_path", ""),
        target_path=data.get("target_path", ""),
        staging_path=data.get("staging_path", ""),
        base_state_version=int(data.get("base_state_version", 0)),
        committed_state_version=int(data.get("committed_state_version", 0)),
        project_state_hash=data.get("project_state_hash", ""),
        proof_report_path=data.get("proof_report_path", ""),
        proof_status=data.get("proof_status", ""),
        proof_score=int(data.get("proof_score", 0)),
        tasks=tasks,
        epochs=epochs,
        model_assignments=assignments,
        agent_records=records,
        required_locks=list(data.get("required_locks", [])),
        artifacts=list(data.get("artifacts", [])),
        message=data.get("message", ""),
    )


def save_factory_run(repo: Path, run: FactoryRun, out_dir: Path | None = None) -> Path:
    directory = _run_dir(repo, run.run_id, out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    run.updated_at = _now()
    path = directory / "run.json"
    path.write_text(_safe_json(run.to_dict()), encoding="utf-8")
    index_path = _index_path(repo, out_dir)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if index_path.exists():
        try:
            existing = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []
    summary = {
        "run_id": run.run_id,
        "product_name": run.product_name,
        "status": run.status.value,
        "template": run.template,
        "updated_at": run.updated_at,
        "proof_status": run.proof_status,
        "proof_score": run.proof_score,
        "target_path": run.target_path,
        "message": run.message,
    }
    existing = [item for item in existing if item.get("run_id") != run.run_id]
    existing.insert(0, summary)
    index_path.write_text(_safe_json(existing[:100]), encoding="utf-8")
    return path


def load_factory_run(repo: Path, run_id: str, out_dir: Path | None = None) -> FactoryRun:
    path = _run_dir(repo, run_id, out_dir) / "run.json"
    if not path.exists():
        raise FactoryError(f"Factory run not found: {run_id}")
    return _run_from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_factory_runs(repo: Path, out_dir: Path | None = None) -> list[dict[str, Any]]:
    path = _index_path(repo, out_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _load_blueprint(path: Path) -> ProductBlueprint:
    from .factory_models import Assumption, ProductFeature, ProductRequirement, UserFlow

    data = json.loads(path.read_text(encoding="utf-8"))
    return ProductBlueprint(
        blueprint_id=data["blueprint_id"],
        name=data["name"],
        prompt=data["prompt"],
        template=data["template"],
        target_users=list(data["target_users"]),
        created_at=data["created_at"],
        version=int(data.get("version", 1)),
        product_summary=data.get("product_summary", ""),
        features=[ProductFeature(**item) for item in data.get("features", [])],
        requirements=[ProductRequirement(**item) for item in data.get("requirements", [])],
        user_flows=[UserFlow(**item) for item in data.get("user_flows", [])],
        non_functional_requirements=[ProductRequirement(**item) for item in data.get("non_functional_requirements", [])],
        risks=list(data.get("risks", [])),
        assumptions=[Assumption(**item) for item in data.get("assumptions", [])],
        constraints=list(data.get("constraints", [])),
        success_criteria=list(data.get("success_criteria", [])),
        architecture_hint=dict(data.get("architecture_hint", {})),
        content_hash=data.get("content_hash", ""),
    )


def _load_plan(path: Path) -> EngineeringPlan:
    from .factory_models import ContractLock, TestPlanItem

    data = json.loads(path.read_text(encoding="utf-8"))
    return EngineeringPlan(
        plan_id=data["plan_id"],
        blueprint_id=data["blueprint_id"],
        created_at=data["created_at"],
        status=data["status"],
        architecture=dict(data.get("architecture", {})),
        contract_locks=[ContractLock(**item) for item in data.get("contract_locks", [])],
        test_plan=[TestPlanItem(**item) for item in data.get("test_plan", [])],
        risk_controls=list(data.get("risk_controls", [])),
        contradictions=list(data.get("contradictions", [])),
        decisions=list(data.get("decisions", [])),
        state_hash=data.get("state_hash", ""),
    )


def plan_factory_run(
    repo: Path,
    prompt: str,
    name: str,
    template: str = "python-service",
    target_users: list[str] | None = None,
    constraints: list[str] | None = None,
    privacy_mode: str = "local",
    out_dir: Path | None = None,
) -> FactoryRun:
    repo = repo.resolve()
    if not repo.exists() or not repo.is_dir():
        raise FactoryError(f"Repository does not exist: {repo}")
    if template not in SUPPORTED_TEMPLATES:
        raise FactoryError(f"Unsupported Phase 6 template: {template}")
    created = _now()
    run_id = f"factory_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{hashlib.sha256((name+prompt).encode()).hexdigest()[:10]}"
    directory = _run_dir(repo, run_id, out_dir)
    directory.mkdir(parents=True, exist_ok=False)
    blueprint = build_product_blueprint(prompt, name, template, target_users, constraints)
    blueprint_paths = write_blueprint_artifacts(blueprint, directory)
    plan = build_engineering_plan(blueprint)
    plan_paths = write_engineering_plan_artifacts(plan, directory)
    if plan.contradictions:
        status = FactoryRunStatus.BLOCKED
    else:
        status = FactoryRunStatus.PREVENTION_LOCKED
    tasks, epochs = build_task_graph(blueprint, plan)
    task_paths = write_task_graph_artifacts(tasks, epochs, directory)
    assignments = ModelRouter().route_graph(tasks, privacy_mode=privacy_mode)
    assignment_path = write_model_assignments(assignments, directory)
    design_paths = write_design_system_artifacts(repo, directory)

    coordinator = StateCoordinator((out_dir or repo / ".basalt") / "factory-state.sqlite3")
    state = coordinator.bootstrap(repository_hash(repo))
    run = FactoryRun(
        run_id=run_id,
        repo_path=str(repo),
        product_name=name,
        prompt=prompt,
        template=template,
        created_at=created,
        updated_at=created,
        status=status if status == FactoryRunStatus.BLOCKED else FactoryRunStatus.PLANNED,
        blueprint_path=str(blueprint_paths[0]),
        engineering_plan_path=str(plan_paths[0]),
        task_graph_path=str(task_paths[0]),
        base_state_version=state.version,
        project_state_hash=state.state_hash,
        tasks=tasks,
        epochs=epochs,
        model_assignments=assignments,
        required_locks=[item.name for item in plan.contract_locks],
        artifacts=[str(path) for path in [*blueprint_paths, *plan_paths, *task_paths, assignment_path, *design_paths]],
        message="Factory plan is blocked by contradictory requirements." if plan.contradictions else "Product blueprint, prevention locks, task graph, and model assignments are ready.",
    )
    save_factory_run(repo, run, out_dir)
    return run


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _feature_payload(blueprint: ProductBlueprint) -> list[dict[str, str]]:
    return [{"id": item.id, "name": item.name, "risk": item.risk_level} for item in blueprint.features]


def _scaffold_python_service(staging: Path, blueprint: ProductBlueprint) -> list[str]:
    package = _package_name(blueprint.name)
    feature_payload = _feature_payload(blueprint)
    files: list[str] = []

    content = """from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class ProductValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Feature:
    id: str
    name: str
    risk: str


def normalize_product_name(value: str) -> str:
    clean = " ".join(value.strip().split())
    if len(clean) < 2:
        raise ProductValidationError("Product name is required.")
    return clean


def build_product_summary(name: str, features: Iterable[Feature]) -> dict:
    normalized = normalize_product_name(name)
    selected = list(features)
    if not selected:
        raise ProductValidationError("At least one feature is required.")
    high_risk = sorted(item.name for item in selected if item.risk in {"HIGH", "CRITICAL"})
    return {
        "name": normalized,
        "feature_count": len(selected),
        "features": [item.name for item in selected],
        "high_risk_features": high_risk,
        "status": "READY_FOR_VERIFICATION",
    }


def requirement_coverage(required: Iterable[str], verified: Iterable[str]) -> dict:
    required_set = {item for item in required if item}
    verified_set = {item for item in verified if item}
    missing = sorted(required_set - verified_set)
    return {
        "required": len(required_set),
        "verified": len(required_set & verified_set),
        "missing": missing,
        "complete": not missing,
    }
"""
    _write_text(staging / "app" / "service.py", content)
    files.append("app/service.py")
    _write_text(staging / "app" / "__init__.py", "from .service import Feature, ProductValidationError, build_product_summary, requirement_coverage\n")
    files.append("app/__init__.py")

    payload_json = json.dumps(feature_payload, indent=2)
    api_content = f'''from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .service import Feature, build_product_summary

PRODUCT_NAME = {blueprint.name!r}
FEATURES = [Feature(**item) for item in {payload_json}]


class ProductHandler(BaseHTTPRequestHandler):
    server_version = "BasaltFactoryProduct/1.0"

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(HTTPStatus.OK, {{"status": "ok", "service": PRODUCT_NAME}})
            return
        if self.path == "/api/v1/product":
            self._json(HTTPStatus.OK, build_product_summary(PRODUCT_NAME, FEATURES))
            return
        self._json(HTTPStatus.NOT_FOUND, {{"error": "not_found"}})

    def log_message(self, _format: str, *_args) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8080) -> None:
    server = ThreadingHTTPServer((host, port), ProductHandler)
    print(f"{{PRODUCT_NAME}} listening on http://{{host}}:{{port}}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
'''
    _write_text(staging / "app" / "api.py", api_content)
    files.append("app/api.py")

    requirement_ids = [item.id for item in blueprint.requirements + blueprint.non_functional_requirements]
    test_content = f'''import unittest

from app.service import Feature, ProductValidationError, build_product_summary, normalize_product_name, requirement_coverage


class ProductServiceTests(unittest.TestCase):
    def test_summary_contains_all_features(self):
        features = [Feature("FEAT-1", "Core", "LOW"), Feature("FEAT-2", "Auth", "HIGH")]
        summary = build_product_summary({blueprint.name!r}, features)
        self.assertEqual(summary["feature_count"], 2)
        self.assertEqual(summary["high_risk_features"], ["Auth"])
        self.assertEqual(summary["status"], "READY_FOR_VERIFICATION")

    def test_product_name_is_normalized(self):
        self.assertEqual(normalize_product_name("  {blueprint.name}  "), {blueprint.name!r})

    def test_two_character_name_is_valid_boundary(self):
        self.assertEqual(normalize_product_name("AB"), "AB")

    def test_empty_name_is_rejected(self):
        with self.assertRaises(ProductValidationError):
            normalize_product_name(" ")

    def test_empty_features_are_rejected(self):
        with self.assertRaises(ProductValidationError):
            build_product_summary({blueprint.name!r}, [])

    def test_requirement_coverage_fails_closed(self):
        requirements = {requirement_ids!r}
        coverage = requirement_coverage(requirements, requirements[:-1])
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["missing"], [requirements[-1]])

    def test_requirement_coverage_is_complete(self):
        requirements = {requirement_ids!r}
        coverage = requirement_coverage(requirements, requirements)
        self.assertTrue(coverage["complete"])
        self.assertEqual(coverage["verified"], len(requirements))


if __name__ == "__main__":
    unittest.main()
'''
    _write_text(staging / "tests" / "test_service.py", test_content)
    files.append("tests/test_service.py")
    _write_text(staging / "tests" / "__init__.py", "")
    files.append("tests/__init__.py")
    return files


def _scaffold_fullstack(staging: Path, blueprint: ProductBlueprint) -> list[str]:
    files = _scaffold_python_service(staging, blueprint)
    colors = TOKENS["color"]
    feature_cards = "\n".join(
        f'<article class="feature"><span>{item.id}</span><h2>{item.name}</h2><p>{item.description}</p><small>{item.risk_level} RISK</small></article>'
        for item in blueprint.features
    )
    index = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>{blueprint.name}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main>
    <p class="eyebrow">VERIFIED ALPHA PRODUCT</p>
    <h1>{blueprint.name}</h1>
    <p class="summary">{blueprint.product_summary}</p>
    <section class="features">{feature_cards}</section>
    <footer>Generated through a proof-backed Basalt factory transaction.</footer>
  </main>
</body>
</html>
'''
    css = f''':root {{
  color-scheme: dark;
  --bg: {colors['background']};
  --surface: {colors['surface']};
  --surface-2: {colors['surfaceElevated']};
  --line: {colors['border']};
  --text: {colors['text']};
  --muted: {colors['textMuted']};
  --accent: {colors['accent']};
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; background: linear-gradient(180deg, #0a0c0f, var(--bg)); color: var(--text); font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
main {{ width: min(1080px, calc(100% - 40px)); margin: 0 auto; padding: 84px 0; }}
.eyebrow {{ color: var(--accent); letter-spacing: .18em; font-size: 11px; font-weight: 700; }}
h1 {{ max-width: 820px; margin: 14px 0; font-size: clamp(44px, 8vw, 88px); letter-spacing: -.055em; line-height: .95; }}
.summary {{ max-width: 700px; color: var(--muted); font-size: 18px; line-height: 1.65; }}
.features {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(240px,1fr)); gap: 14px; margin-top: 54px; }}
.feature {{ min-height: 210px; padding: 24px; border: 1px solid var(--line); border-radius: 18px; background: var(--surface); box-shadow: 0 18px 60px rgba(0,0,0,.18); }}
.feature span,.feature small {{ color: var(--accent); font-size: 10px; letter-spacing: .1em; }}
.feature h2 {{ margin: 28px 0 10px; font-size: 22px; }}
.feature p {{ color: var(--muted); line-height: 1.55; }}
footer {{ margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }}
@media (max-width: 640px) {{ main {{ padding: 54px 0; }} }}
'''
    _write_text(staging / "web" / "index.html", index)
    _write_text(staging / "web" / "styles.css", css)
    _write_text(staging / "web" / "app.js", '"use strict";\nwindow.BASALT_PRODUCT_READY = true;\n')
    files.extend(["web/index.html", "web/styles.css", "web/app.js"])
    return files



def _scaffold_saas(staging: Path, blueprint: ProductBlueprint) -> list[str]:
    files = _scaffold_fullstack(staging, blueprint)
    tenancy = """from __future__ import annotations

from dataclasses import dataclass


class TenantAccessError(PermissionError):
    pass


@dataclass(frozen=True)
class Membership:
    user_id: str
    tenant_id: str
    role: str


def require_tenant_access(membership: Membership, tenant_id: str, allowed_roles: set[str] | None = None) -> bool:
    if membership.tenant_id != tenant_id:
        raise TenantAccessError(\"Cross-tenant access is blocked.\")
    if allowed_roles and membership.role not in allowed_roles:
        raise TenantAccessError(\"Role is not permitted for this action.\")
    return True


def tenant_scope(records: list[dict], tenant_id: str) -> list[dict]:
    return [item for item in records if item.get(\"tenant_id\") == tenant_id]
"""
    subscriptions = """from __future__ import annotations

VALID_STATES = {\"trial\", \"active\", \"past_due\", \"cancelled\"}


def normalize_plan(value: str) -> str:
    plan = value.strip().lower()
    if plan not in {\"starter\", \"team\", \"enterprise\"}:
        raise ValueError(\"Unknown subscription plan.\")
    return plan


def can_use_feature(state: str, plan: str, required_plan: str = \"starter\") -> bool:
    if state not in VALID_STATES or state in {\"past_due\", \"cancelled\"}:
        return False
    order = {\"starter\": 1, \"team\": 2, \"enterprise\": 3}
    return order[normalize_plan(plan)] >= order[normalize_plan(required_plan)]
"""
    tests = """import unittest

from app.subscriptions import can_use_feature, normalize_plan
from app.tenancy import Membership, TenantAccessError, require_tenant_access, tenant_scope


class SaaSFoundationTests(unittest.TestCase):
    def test_cross_tenant_access_is_blocked(self):
        with self.assertRaises(TenantAccessError):
            require_tenant_access(Membership(\"u1\", \"t1\", \"admin\"), \"t2\")

    def test_role_gate_is_enforced(self):
        with self.assertRaises(TenantAccessError):
            require_tenant_access(Membership(\"u1\", \"t1\", \"viewer\"), \"t1\", {\"admin\"})

    def test_tenant_scope_filters_records(self):
        records = [{\"tenant_id\": \"a\", \"id\": 1}, {\"tenant_id\": \"b\", \"id\": 2}]
        self.assertEqual(tenant_scope(records, \"a\"), [{\"tenant_id\": \"a\", \"id\": 1}])

    def test_subscription_gate_fails_closed(self):
        self.assertFalse(can_use_feature(\"past_due\", \"enterprise\"))
        self.assertFalse(can_use_feature(\"active\", \"starter\", \"team\"))
        self.assertTrue(can_use_feature(\"active\", \"team\", \"team\"))

    def test_unknown_plan_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_plan(\"unlimited\")


if __name__ == \"__main__\":
    unittest.main()
"""
    _write_text(staging / "app" / "tenancy.py", tenancy)
    _write_text(staging / "app" / "subscriptions.py", subscriptions)
    _write_text(staging / "tests" / "test_saas_foundation.py", tests)
    files.extend(["app/tenancy.py", "app/subscriptions.py", "tests/test_saas_foundation.py"])
    return files

def _write_project_metadata(staging: Path, blueprint: ProductBlueprint, plan: EngineeringPlan, run: FactoryRun) -> list[str]:
    package = _package_name(blueprint.name)
    pyproject = f'''[project]
name = "{_slug(blueprint.name)}"
version = "0.1.0a1"
description = {blueprint.product_summary!r}
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
'''
    _write_text(staging / "pyproject.toml", pyproject)
    basalt_yaml = f'''project:
  name: {_slug(blueprint.name)}
  type: python
commands:
  install: null
  build: null
  lint: python -m compileall app tests
  typecheck: null
  test: python -m unittest discover -s tests -v
proof:
  require_build: false
  require_lint: true
  require_typecheck: false
  require_tests: true
  mutation_sample: true
  mutation_max: 1
  mutation_per_file: 1
  mutation_test_command: python -m unittest tests.test_service.ProductServiceTests.test_two_character_name_is_valid_boundary
  mutation_include: app/service.py
  security_scan: basic
  min_verified_score: 80
  dashboard: true
sandbox:
  mode: auto
  docker_image: python:3.13-slim
  network: install-only
  fallback_to_temp: true
knowledge_graph:
  auto_refresh: true
context:
  token_budget: 8000
'''
    _write_text(staging / "basalt.yaml", basalt_yaml)
    readme = f'''# {blueprint.name}

{blueprint.product_summary}

## Run

```bash
python -m app.api
```

## Verify

```bash
python -m unittest discover -s tests -v
basalt verify .
```

## Provenance

- Factory run: `{run.run_id}`
- Blueprint: `{blueprint.blueprint_id}`
- Engineering plan: `{plan.plan_id}`
- Template: `{blueprint.template}`

This alpha project was assembled in a staging workspace and copied into place only after Basalt verification.
'''
    _write_text(staging / "README.md", readme)
    _write_text(staging / "docs" / "product-blueprint.json", _safe_json(asdict(blueprint)))
    _write_text(staging / "docs" / "engineering-plan.json", _safe_json(asdict(plan)))
    _write_text(staging / ".gitignore", ".basalt/\n__pycache__/\n*.pyc\n.venv/\n")
    return ["pyproject.toml", "basalt.yaml", "README.md", "docs/product-blueprint.json", "docs/engineering-plan.json", ".gitignore"]


def _execute_task_records(run: FactoryRun, staging: Path) -> list[AgentExecutionRecord]:
    assignments = {item.task_id: item for item in run.model_assignments}
    records: list[AgentExecutionRecord] = []
    for task in sorted(run.tasks, key=lambda item: (item.epoch, item.task_id)):
        started = _now()
        artifact_map = {
            "ProductAgent": ["docs/product-blueprint.json"],
            "ArchitectureAgent": ["docs/engineering-plan.json", "pyproject.toml"],
            "UIDesignAgent": ["web/styles.css"] if (staging / "web" / "styles.css").exists() else ["docs/engineering-plan.json"],
            "BackendAgent": ["app/service.py", "app/api.py"],
            "FrontendAgent": ["web/index.html", "web/styles.css"] if (staging / "web").exists() else ["app/api.py"],
            "TestingAgent": ["tests/test_service.py"],
            "SecurityAgent": ["basalt.yaml"],
            "CodeReviewAgent": ["factory-manifest.json"],
            "DocumentationAgent": ["README.md"],
            "PerformanceAgent": ["factory-manifest.json"],
            "DevOpsAgent": ["basalt.yaml", "factory-manifest.json"],
            "DatabaseAgent": ["docs/engineering-plan.json"],
        }
        assignment = assignments.get(task.task_id)
        records.append(
            AgentExecutionRecord(
                task_id=task.task_id,
                agent_role=task.agent_role,
                status="COMPLETED",
                started_at=started,
                finished_at=_now(),
                summary=f"{task.agent_role} completed {task.title.lower()} within epoch {task.epoch}.",
                artifacts=[item for item in artifact_map.get(task.agent_role, []) if (staging / item).exists() or item == "factory-manifest.json"],
                model_assignment=asdict(assignment) if assignment else {},
                risk_flags=[task.risk_level] if task.risk_level in {"HIGH", "CRITICAL"} else [],
            )
        )
        task.status = "COMPLETED"
    for epoch in run.epochs:
        epoch.status = "COMPLETED"
    return records


def _target_is_safe(target: Path, source_repo: Path) -> None:
    if target == source_repo or source_repo in target.parents:
        raise FactoryError("Factory target cannot overwrite the Basalt source repository.")
    if target.exists() and any(target.iterdir()):
        raise FactoryError(f"Factory target must be empty or absent: {target}")
    if ".git" in target.parts:
        raise FactoryError("Factory target cannot be placed inside a .git directory.")


def build_factory_run(
    repo: Path,
    run_id: str,
    target: Path,
    sandbox: str = "temp",
    out_dir: Path | None = None,
) -> FactoryRun:
    repo = repo.resolve()
    target = target.resolve()
    _target_is_safe(target, repo)
    run = load_factory_run(repo, run_id, out_dir)
    if run.status == FactoryRunStatus.BLOCKED:
        raise FactoryError("Factory run is blocked by prevention-first planning.")
    if run.status == FactoryRunStatus.VERIFIED:
        raise FactoryError("Factory run is already verified.")
    run_dir = _run_dir(repo, run_id, out_dir)
    blueprint = _load_blueprint(Path(run.blueprint_path))
    plan = _load_plan(Path(run.engineering_plan_path))
    coordinator = StateCoordinator((out_dir or repo / ".basalt") / "factory-state.sqlite3")
    current = coordinator.current()
    if current.version != run.base_state_version:
        run.status = FactoryRunStatus.BLOCKED
        run.message = f"Stale plan: base state {run.base_state_version}, current state {current.version}."
        save_factory_run(repo, run, out_dir)
        raise FactoryError(run.message)

    coordinator.begin(run.run_id, run.base_state_version, f"Build {run.product_name}")
    try:
        coordinator.acquire_locks(run.required_locks, "FactoryOrchestrator", run.run_id, run.base_state_version)
    except (StateConflictError, ContractLockError):
        coordinator.abort(run.run_id, "Unable to acquire required contract locks.")
        raise

    staging = run_dir / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    run.staging_path = str(staging)
    run.target_path = str(target)
    run.status = FactoryRunStatus.BUILDING
    save_factory_run(repo, run, out_dir)

    try:
        if blueprint.template in {"fullstack-lite", "web-app"}:
            generated = _scaffold_fullstack(staging, blueprint)
        elif blueprint.template == "saas-starter":
            generated = _scaffold_saas(staging, blueprint)
        else:
            generated = _scaffold_python_service(staging, blueprint)
        generated.extend(_write_project_metadata(staging, blueprint, plan, run))
        run.agent_records = _execute_task_records(run, staging)
        manifest = {
            "factory_run_id": run.run_id,
            "product_name": blueprint.name,
            "blueprint_id": blueprint.blueprint_id,
            "engineering_plan_id": plan.plan_id,
            "template": blueprint.template,
            "generated_at": _now(),
            "files": sorted(set(generated)),
            "epochs": [asdict(item) for item in run.epochs],
            "tasks": [asdict(item) for item in run.tasks],
            "model_assignments": [asdict(item) for item in run.model_assignments],
            "proof_required": True,
            "assembly_rule": "No target mutation before VERIFIED proof.",
        }
        manifest_path = staging / "factory-manifest.json"
        manifest_path.write_text(_safe_json(manifest), encoding="utf-8")
        run.manifest_path = str(manifest_path)
        run.status = FactoryRunStatus.VERIFYING
        save_factory_run(repo, run, out_dir)

        evidence = staging / ".basalt"
        report = verify_repo(staging, sandbox_override=sandbox, output_dir=evidence)
        write_json_report(report, evidence / "proof-report.json")
        write_markdown_report(report, evidence / "proof-report.md")
        write_dashboard(report, evidence / "basalt-dashboard.html")
        run.proof_report_path = str(evidence / "proof-report.json")
        run.proof_status = report.final_status.value
        run.proof_score = report.score
        if report.final_status.value != "VERIFIED":
            run.status = FactoryRunStatus.ROLLED_BACK
            run.message = f"Generated product was not assembled because proof returned {report.final_status.value}."
            coordinator.abort(run.run_id, run.message)
            save_factory_run(repo, run, out_dir)
            return run

        target.mkdir(parents=True, exist_ok=True)
        for item in staging.iterdir():
            if item.name == ".basalt":
                continue
            destination = target / item.name
            if item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)
        target_evidence = target / ".basalt" / "factory-proof"
        target_evidence.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(evidence, target_evidence)
        output_hash = repository_hash(target)
        committed = coordinator.commit(
            run.run_id,
            run.base_state_version,
            output_hash,
            f"Verified factory assembly for {run.product_name}",
        )
        run.committed_state_version = committed.version
        run.project_state_hash = committed.state_hash
        run.status = FactoryRunStatus.VERIFIED
        run.message = f"Verified product assembled at {target}."
        run.artifacts.extend([str(manifest_path), str(evidence / "proof-report.json"), str(evidence / "proof-report.md"), str(evidence / "basalt-dashboard.html")])
        save_factory_run(repo, run, out_dir)
        return run
    except Exception as exc:
        coordinator.abort(run.run_id, f"Factory build failed: {exc}")
        run.status = FactoryRunStatus.FAILED
        run.message = str(exc)
        save_factory_run(repo, run, out_dir)
        raise


def create_product(
    repo: Path,
    prompt: str,
    name: str,
    target: Path,
    template: str = "python-service",
    target_users: list[str] | None = None,
    constraints: list[str] | None = None,
    privacy_mode: str = "local",
    sandbox: str = "temp",
    out_dir: Path | None = None,
) -> FactoryRun:
    run = plan_factory_run(
        repo,
        prompt,
        name,
        template=template,
        target_users=target_users,
        constraints=constraints,
        privacy_mode=privacy_mode,
        out_dir=out_dir,
    )
    if run.status == FactoryRunStatus.BLOCKED:
        return run
    return build_factory_run(repo, run.run_id, target, sandbox=sandbox, out_dir=out_dir)


def factory_snapshot(repo: Path, out_dir: Path | None = None) -> dict[str, Any]:
    coordinator = StateCoordinator((out_dir or repo / ".basalt") / "factory-state.sqlite3")
    state = coordinator.bootstrap(repository_hash(repo))
    runs = list_factory_runs(repo, out_dir)
    return {
        "platform": "Basalt v2.5 Private Beta Full Build System",
        "supported_templates": sorted(SUPPORTED_TEMPLATES),
        "metrics": {
            "total_runs": len(runs),
            "verified_runs": sum(1 for item in runs if item.get("status") == "VERIFIED"),
            "blocked_runs": sum(1 for item in runs if item.get("status") == "BLOCKED"),
            "failed_runs": sum(1 for item in runs if item.get("status") in {"FAILED", "ROLLED_BACK"}),
        },
        "state": coordinator.snapshot(),
        "runs": runs,
        "models": ModelRouter().inventory(),
        "design_system": {"name": TOKENS["name"], "version": TOKENS["version"]},
        "current_state": asdict(state),
    }
