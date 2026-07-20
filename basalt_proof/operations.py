from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def operations_snapshot(
    proof: dict[str, Any],
    graph: dict[str, Any],
    transactions: list[dict[str, Any]],
    beta: dict[str, Any],
    preview: dict[str, Any],
) -> dict[str, Any]:
    incidents: list[dict[str, Any]] = []
    proof_status = str(proof.get("final_status") or "NOT_RUN")
    proof_score = int(proof.get("score", 0) or 0)
    if proof_status not in {"VERIFIED", "NOT_RUN"}:
        incidents.append({"severity": "HIGH", "code": "PROOF_NOT_VERIFIED", "summary": f"Repository proof is {proof_status} ({proof_score}/100).", "source": "proof"})
    elif proof_status == "NOT_RUN":
        incidents.append({"severity": "MEDIUM", "code": "PROOF_NOT_RUN", "summary": "Repository proof has not been executed for the current workspace.", "source": "proof"})
    if graph and not bool(graph.get("fresh", False)):
        incidents.append({"severity": "MEDIUM", "code": "GRAPH_STALE", "summary": "Knowledge graph is stale relative to repository state.", "source": "knowledge-graph"})

    job_counts = ((beta.get("jobs") or {}).get("counts") or {}) if isinstance(beta, dict) else {}
    failed_jobs = int(job_counts.get("FAILED", 0) or 0)
    if failed_jobs:
        incidents.append({"severity": "HIGH", "code": "FAILED_JOBS", "summary": f"{failed_jobs} durable job(s) are in FAILED state.", "source": "job-queue"})

    deployment_counts = ((beta.get("deployments") or {}).get("counts") or {}) if isinstance(beta, dict) else {}
    blocked_deployments = int(deployment_counts.get("BLOCKED", 0) or 0)
    if blocked_deployments:
        incidents.append({"severity": "HIGH", "code": "BLOCKED_DEPLOYMENTS", "summary": f"{blocked_deployments} deployment(s) are blocked.", "source": "deployment-ledger"})

    pending_approvals = sum(1 for item in transactions if str(item.get("status")) == "AWAITING_APPROVAL")
    rollback_ready = sum(1 for item in transactions if bool(item.get("rollback_available")))
    high = sum(1 for item in incidents if item["severity"] == "HIGH")
    status = "DEGRADED" if high else ("ATTENTION" if incidents else "HEALTHY")
    return {
        "generated_at": _now(),
        "status": status,
        "scope": "LOCAL_CONTROL_PLANE",
        "metrics": {
            "incidents": len(incidents),
            "high_incidents": high,
            "pending_approvals": pending_approvals,
            "rollback_ready": rollback_ready,
            "failed_jobs": failed_jobs,
            "preview_status": preview.get("status", "STOPPED"),
        },
        "incidents": incidents,
        "recovery": {
            "transaction_rollback": rollback_ready > 0,
            "deployment_rollback_records": int(deployment_counts.get("ROLLED_BACK", 0) or 0),
            "preview_stop_control": True,
            "evidence_hashing": True,
            "claim": "Local recovery readiness is reported from ledgers and available controls. No external uptime or cloud-provider monitoring is claimed.",
        },
    }
