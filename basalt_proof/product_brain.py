from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .factory_models import Assumption, ProductBlueprint, ProductFeature, ProductRequirement, UserFlow


KNOWN_FEATURES: list[tuple[str, tuple[str, ...], str]] = [
    ("Authentication", ("auth", "login", "sign in", "signup", "register", "account"), "Identity, session, and access control."),
    ("Payments", ("payment", "checkout", "billing", "subscription", "invoice"), "Payment collection and billing lifecycle."),
    ("Booking", ("booking", "reservation", "appointment", "schedule"), "Availability and reservation workflow."),
    ("Dashboard", ("dashboard", "admin panel", "analytics"), "Operational overview and management controls."),
    ("Search", ("search", "filter", "discovery"), "Find and filter relevant records."),
    ("Notifications", ("notification", "email", "alert", "reminder"), "Event-driven user communication."),
    ("Profiles", ("profile", "user settings", "preferences"), "User-owned information and preferences."),
    ("File Management", ("upload", "attachment", "document", "image"), "Safe file upload and retrieval."),
    ("API", ("api", "integration", "webhook"), "Machine-readable contracts and integrations."),
    ("Administration", ("admin", "moderation", "manage users"), "Privileged operational controls."),
]

RISK_KEYWORDS: list[tuple[str, str, str]] = [
    ("payment", "HIGH", "Payment logic and financial data require separate review and strong tests."),
    ("auth", "HIGH", "Authentication and permissions are security-critical contracts."),
    ("medical", "CRITICAL", "Medical output requires domain review and strict wording governance."),
    ("legal", "CRITICAL", "Legal output requires human review and auditability."),
    ("migration", "HIGH", "Schema migration requires expand-and-contract planning."),
    ("upload", "MEDIUM", "File handling requires validation, size limits, and content controls."),
    ("personal data", "HIGH", "Personal data requires privacy and retention controls."),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return clean or "product"


def _canonical_hash(data: dict) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contains(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _feature_risk(name: str, prompt: str) -> str:
    text = f"{name} {prompt}".lower()
    for keyword, level, _message in RISK_KEYWORDS:
        if keyword in text:
            return level
    if name in {"Notifications", "File Management", "Administration"}:
        return "MEDIUM"
    return "LOW"


def _extract_features(prompt: str) -> list[ProductFeature]:
    features: list[ProductFeature] = []
    for index, (name, keywords, description) in enumerate(KNOWN_FEATURES, start=1):
        if _contains(prompt, keywords):
            features.append(
                ProductFeature(
                    id=f"FEAT-{index:03d}",
                    name=name,
                    description=description,
                    risk_level=_feature_risk(name, prompt),
                )
            )
    if not features:
        sentence = re.split(r"[.!?\n]", prompt.strip())[0].strip()
        feature_name = sentence[:70] if sentence else "Core Product Workflow"
        features.append(
            ProductFeature(
                id="FEAT-001",
                name=feature_name,
                description="Primary user-visible capability derived from the product intent.",
                risk_level="LOW",
            )
        )
    return features


def _requirements_for_feature(feature: ProductFeature, ordinal: int) -> list[ProductRequirement]:
    slug = _slug(feature.name).upper().replace("-", "_")[:18]
    requirements = [
        ProductRequirement(
            id=f"REQ-{slug}-{ordinal:03d}",
            title=f"{feature.name} core behavior",
            statement=f"The product must provide {feature.name.lower()} behavior with explicit success and failure states.",
            risk_level=feature.risk_level,
            acceptance_criteria=[
                f"A user can complete the primary {feature.name.lower()} flow.",
                "Invalid input returns a clear, non-sensitive error.",
                "The behavior is covered by an automated test.",
            ],
            source_feature=feature.id,
        )
    ]
    if feature.risk_level in {"HIGH", "CRITICAL"}:
        requirements.append(
            ProductRequirement(
                id=f"REQ-{slug}-SEC-{ordinal:03d}",
                title=f"{feature.name} governance",
                statement=f"The {feature.name.lower()} capability must enforce least privilege, auditability, and human review for high-risk changes.",
                priority="MUST",
                risk_level=feature.risk_level,
                acceptance_criteria=[
                    "Security-sensitive actions are logged.",
                    "A negative-path test proves the control rejects an invalid action.",
                    "Contract changes require a lock and explicit review.",
                ],
                source_feature=feature.id,
            )
        )
    return requirements


def _non_functional_requirements() -> list[ProductRequirement]:
    return [
        ProductRequirement(
            id="NFR-SEC-001",
            title="Secure defaults",
            statement="The product must fail closed for unauthorized or malformed requests.",
            risk_level="HIGH",
            acceptance_criteria=["Unauthorized requests are rejected.", "Secrets are never written to logs."],
        ),
        ProductRequirement(
            id="NFR-REL-001",
            title="Deterministic verification",
            statement="Every build must include repeatable automated verification and an evidence report.",
            risk_level="MEDIUM",
            acceptance_criteria=["The full test suite is repeatable.", "A machine-readable proof result is generated."],
        ),
        ProductRequirement(
            id="NFR-UX-001",
            title="Accessible operational interface",
            statement="User-facing interfaces must remain clear, keyboard-usable, and visually consistent.",
            risk_level="LOW",
            acceptance_criteria=["Core actions are keyboard accessible.", "Design tokens govern visual styles."],
        ),
        ProductRequirement(
            id="NFR-OBS-001",
            title="Auditability",
            statement="Important product and engineering decisions must retain provenance.",
            risk_level="MEDIUM",
            acceptance_criteria=["Actions and decisions include timestamps and actors.", "Artifacts are traceable to requirements."],
        ),
    ]


def build_product_blueprint(
    prompt: str,
    name: str,
    template: str = "python-service",
    target_users: list[str] | None = None,
    constraints: list[str] | None = None,
) -> ProductBlueprint:
    prompt = " ".join(prompt.strip().split())
    if len(prompt) < 12:
        raise ValueError("Product intent must contain at least 12 meaningful characters.")
    name = name.strip() or "Basalt Generated Product"
    users = [item.strip() for item in (target_users or ["Primary user"]) if item.strip()]
    features = _extract_features(prompt)
    requirements: list[ProductRequirement] = []
    for index, feature in enumerate(features, start=1):
        feature_requirements = _requirements_for_feature(feature, index)
        feature.requirements = [item.id for item in feature_requirements]
        requirements.extend(feature_requirements)

    user_flows = [
        UserFlow(
            id=f"FLOW-{index:03d}",
            name=f"{feature.name} primary flow",
            actor=users[0],
            steps=[
                "Open the product entry point.",
                f"Start the {feature.name.lower()} action.",
                "Provide valid input.",
                "Receive a confirmed result with a clear next step.",
            ],
            success_condition=f"The {feature.name.lower()} outcome is completed and recorded without hidden failure.",
        )
        for index, feature in enumerate(features, start=1)
    ]

    risks: list[dict[str, str]] = []
    lowered = prompt.lower()
    for keyword, level, message in RISK_KEYWORDS:
        if keyword in lowered:
            risks.append({"area": keyword, "level": level, "message": message})
    if not risks:
        risks.append({"area": "scope", "level": "LOW", "message": "Scope must remain bounded to the locked alpha blueprint."})

    assumptions = [
        Assumption(
            id="ASM-001",
            text="The first alpha targets a single deployable product and a bounded feature set.",
            confidence=0.92,
            risk="LOW",
        ),
        Assumption(
            id="ASM-002",
            text="Production secrets and production data are unavailable during generation and verification.",
            confidence=0.99,
            risk="HIGH",
        ),
    ]

    architecture_hint = {
        "template": template,
        "runtime": "Python 3.11+",
        "interface": "JSON API" if template == "python-service" else "Local web application + JSON API",
        "storage": "In-memory alpha adapter with explicit repository contracts",
        "verification": "unittest + Basalt proof gate",
        "design_system": "Basalt Obsidian",
    }

    blueprint = ProductBlueprint(
        blueprint_id=f"bp_{hashlib.sha256((name + prompt).encode()).hexdigest()[:12]}",
        name=name,
        prompt=prompt,
        template=template,
        target_users=users,
        created_at=_now(),
        product_summary=f"{name} is a governed alpha product generated from a locked product intent and verified before assembly.",
        features=features,
        requirements=requirements,
        user_flows=user_flows,
        non_functional_requirements=_non_functional_requirements(),
        risks=risks,
        assumptions=assumptions,
        constraints=list(constraints or []),
        success_criteria=[
            "The generated project installs or runs without hidden manual edits.",
            "All required tests pass in an isolated Basalt sandbox.",
            "No blocking security or policy findings remain.",
            "The generated project includes traceable blueprint, plan, and proof artifacts.",
        ],
        architecture_hint=architecture_hint,
    )
    payload = blueprint_to_dict(blueprint)
    payload["content_hash"] = ""
    payload["created_at"] = ""
    blueprint.content_hash = _canonical_hash(payload)
    return blueprint


def blueprint_to_dict(blueprint: ProductBlueprint) -> dict:
    from dataclasses import asdict

    return asdict(blueprint)


def validate_blueprint(blueprint: ProductBlueprint) -> list[str]:
    errors: list[str] = []
    if not blueprint.features:
        errors.append("Blueprint has no product features.")
    requirement_ids = {item.id for item in blueprint.requirements + blueprint.non_functional_requirements}
    if len(requirement_ids) != len(blueprint.requirements) + len(blueprint.non_functional_requirements):
        errors.append("Blueprint contains duplicate requirement identifiers.")
    for feature in blueprint.features:
        missing = [item for item in feature.requirements if item not in requirement_ids]
        if missing:
            errors.append(f"Feature {feature.id} references missing requirements: {', '.join(missing)}")
    if not blueprint.success_criteria:
        errors.append("Blueprint has no success criteria.")
    return errors


def render_blueprint_markdown(blueprint: ProductBlueprint) -> str:
    lines = [
        f"# Product Blueprint — {blueprint.name}",
        "",
        f"- Blueprint: `{blueprint.blueprint_id}`",
        f"- Template: `{blueprint.template}`",
        f"- State hash: `{blueprint.content_hash}`",
        "",
        "## Product intent",
        blueprint.prompt,
        "",
        "## Features",
    ]
    for feature in blueprint.features:
        lines.append(f"- **{feature.name}** — {feature.description} (`{feature.risk_level}`)")
    lines.extend(["", "## Requirements"])
    for requirement in blueprint.requirements + blueprint.non_functional_requirements:
        lines.append(f"- `{requirement.id}` **{requirement.title}** — {requirement.statement}")
    lines.extend(["", "## Risks"])
    for risk in blueprint.risks:
        lines.append(f"- **{risk['level']} / {risk['area']}** — {risk['message']}")
    lines.extend(["", "## Success criteria"])
    lines.extend(f"- {item}" for item in blueprint.success_criteria)
    return "\n".join(lines) + "\n"


def write_blueprint_artifacts(blueprint: ProductBlueprint, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "product-blueprint.json"
    md_path = out_dir / "product-blueprint.md"
    json_path.write_text(json.dumps(blueprint_to_dict(blueprint), indent=2), encoding="utf-8")
    md_path.write_text(render_blueprint_markdown(blueprint), encoding="utf-8")
    return [json_path, md_path]
