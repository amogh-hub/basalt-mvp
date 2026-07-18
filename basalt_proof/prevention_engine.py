from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .factory_models import ContractLock, EngineeringPlan, ProductBlueprint, TestPlanItem


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def detect_contradictions(blueprint: ProductBlueprint) -> list[str]:
    text = " ".join([blueprint.prompt, *blueprint.constraints]).lower()
    contradictions: list[str] = []
    pairs = [
        (("no authentication", "without authentication"), ("login", "authentication", "account"), "Authentication is both prohibited and required."),
        (("no database", "without database"), ("persistent", "history", "booking", "payment"), "Persistent behavior is requested while database use is prohibited."),
        (("public data",), ("private data", "confidential"), "Data is described as both public and private."),
        (("no human approval",), ("payment", "medical", "legal", "production deploy"), "Human approval is prohibited for a high-risk capability."),
    ]
    for negative, positive, message in pairs:
        if any(item in text for item in negative) and any(item in text for item in positive):
            contradictions.append(message)
    return contradictions


def _locks_for_blueprint(blueprint: ProductBlueprint) -> list[ContractLock]:
    locks = [
        ContractLock(
            name="PRODUCT_REQUIREMENTS",
            scope="requirements + user flows + success criteria",
            reason="Agents must not silently change product intent during implementation.",
            risk_level="HIGH",
        ),
        ContractLock(
            name="BASALT_DESIGN_SYSTEM",
            scope="design tokens + components + accessibility rules",
            reason="Prevents visual drift and toy-like generated UI.",
            risk_level="MEDIUM",
            owner="UIDesignAgent",
        ),
    ]
    feature_names = {item.name for item in blueprint.features}
    if "Authentication" in feature_names:
        locks.append(ContractLock("AUTH_CONTRACT", "identity + session + permissions", "Authentication is a shared security contract.", "HIGH", "SecurityAgent"))
    if "Payments" in feature_names:
        locks.append(ContractLock("PAYMENT_CONTRACT", "billing + checkout + webhook semantics", "Payment behavior requires separate review.", "CRITICAL", "ArchitectureAgent"))
    if "API" in feature_names or blueprint.template in {"python-service", "fullstack-lite"}:
        locks.append(ContractLock("API_CONTRACT", "request + response + error shapes", "Frontend, backend, tests, and integrations share this contract.", "HIGH", "ArchitectureAgent"))
    if any(item.name in {"Booking", "Profiles", "Payments"} for item in blueprint.features):
        locks.append(ContractLock("DATA_SCHEMA", "entities + relationships + migration policy", "Data shape changes can invalidate multiple agents.", "HIGH", "DatabaseAgent"))
    return locks


def build_engineering_plan(blueprint: ProductBlueprint) -> EngineeringPlan:
    contradictions = detect_contradictions(blueprint)
    locks = _locks_for_blueprint(blueprint)
    tests: list[TestPlanItem] = []
    all_requirements = blueprint.requirements + blueprint.non_functional_requirements
    for index, requirement in enumerate(all_requirements, start=1):
        test_type = "security" if requirement.risk_level in {"HIGH", "CRITICAL"} else "behavior"
        tests.append(
            TestPlanItem(
                id=f"TEST-{index:03d}",
                requirement_id=requirement.id,
                test_type=test_type,
                description=f"Prove requirement {requirement.id}: {requirement.title}",
                required=True,
                owner_role="SecurityAgent" if test_type == "security" else "TestingAgent",
            )
        )

    architecture = {
        **blueprint.architecture_hint,
        "layers": ["interface", "application", "domain", "verification"],
        "dependency_rule": "Higher layers may depend inward; domain logic remains independently testable.",
        "state_rule": "Agents propose against a known state version and never commit directly.",
        "proof_rule": "Assembly is accepted only after deterministic verification.",
    }
    risk_controls = [
        {
            "risk": risk["area"],
            "level": risk["level"],
            "control": "Separate specialist review, negative-path tests, and human approval when high risk.",
        }
        for risk in blueprint.risks
    ]
    decisions = [
        {"id": "DEC-001", "decision": f"Use the {blueprint.template} alpha template.", "status": "LOCKED"},
        {"id": "DEC-002", "decision": "Use dependency-free runtime components for deterministic offline verification.", "status": "LOCKED"},
        {"id": "DEC-003", "decision": "Apply the Basalt Obsidian design system to every generated interface.", "status": "LOCKED"},
    ]
    plan = EngineeringPlan(
        plan_id=f"plan_{blueprint.content_hash[:12]}",
        blueprint_id=blueprint.blueprint_id,
        created_at=_now(),
        status="BLOCKED" if contradictions else "LOCKED",
        architecture=architecture,
        contract_locks=locks,
        test_plan=tests,
        risk_controls=risk_controls,
        contradictions=contradictions,
        decisions=decisions,
    )
    payload = asdict(plan)
    payload["state_hash"] = ""
    plan.state_hash = _state_hash(payload)
    return plan


def render_engineering_plan_markdown(plan: EngineeringPlan) -> str:
    lines = [
        "# Prevention-First Engineering Plan",
        "",
        f"- Plan: `{plan.plan_id}`",
        f"- Blueprint: `{plan.blueprint_id}`",
        f"- Status: `{plan.status}`",
        f"- State hash: `{plan.state_hash}`",
        "",
        "## Contract locks",
    ]
    lines.extend(f"- `{item.name}` — {item.reason}" for item in plan.contract_locks)
    lines.extend(["", "## Test plan"])
    lines.extend(f"- `{item.id}` → `{item.requirement_id}` — {item.description}" for item in plan.test_plan)
    lines.extend(["", "## Decisions"])
    lines.extend(f"- `{item['id']}` {item['decision']}" for item in plan.decisions)
    if plan.contradictions:
        lines.extend(["", "## Blocking contradictions"])
        lines.extend(f"- {item}" for item in plan.contradictions)
    return "\n".join(lines) + "\n"


def write_engineering_plan_artifacts(plan: EngineeringPlan, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "engineering-plan.json"
    md_path = out_dir / "engineering-plan.md"
    json_path.write_text(json.dumps(asdict(plan), indent=2), encoding="utf-8")
    md_path.write_text(render_engineering_plan_markdown(plan), encoding="utf-8")
    return [json_path, md_path]
