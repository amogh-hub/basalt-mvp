from __future__ import annotations

import json
import mimetypes
import re
import threading
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_runtime import (
    AgentRunError,
    apply_agent_run,
    approve_agent_run,
    list_agent_runs,
    load_agent_run,
    reject_agent_run,
    rollback_agent_run,
)
from .config import load_config
from .context_compiler import compile_context_for_repo
from .knowledge_graph import analyze_impact, build_project_graph, render_impact_markdown, write_graph_artifacts
from .proof import verify_repo
from .report import write_json_report, write_markdown_report
from .dashboard import write_dashboard
from .private_beta import PrivateBetaPlatform
from .software_factory import (
    build_factory_run,
    factory_snapshot,
    list_factory_runs,
    load_factory_run,
    plan_factory_run,
)
from .state_coordinator import StateCoordinator


COMMAND_CENTER_API_VERSION = "v1"
MAX_ARTIFACT_BYTES = 2_000_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _risk_level(report: dict[str, Any], runs: list[dict[str, Any]]) -> str:
    status = str(report.get("final_status", "UNKNOWN"))
    if status in {"BLOCKED_BY_POLICY", "NOT_VERIFIED"}:
        return "HIGH"
    if status in {"WEAK_PROOF", "NEEDS_HUMAN_REVIEW"}:
        return "MEDIUM"
    if any(str(item.get("risk", "")).upper() == "HIGH" for item in runs):
        return "MEDIUM"
    return "LOW"


def _proof_metrics(report: dict[str, Any]) -> dict[str, Any]:
    checks = list(report.get("checks") or [])
    findings = list(report.get("security_findings") or [])
    mutations = list(report.get("mutations") or [])
    statuses = Counter(str(item.get("status", "UNKNOWN")) for item in checks)
    levels = Counter(str(item.get("level", "UNKNOWN")).upper() for item in findings)
    killed = sum(1 for item in mutations if item.get("survived") is False)
    survived = sum(1 for item in mutations if item.get("survived") is True)
    return {
        "status": str(report.get("final_status", "UNKNOWN")),
        "score": int(report.get("score", 0) or 0),
        "started_at": str(report.get("started_at", "")),
        "finished_at": str(report.get("finished_at", "")),
        "sandbox": str(report.get("sandbox", "unknown")),
        "sandbox_requested": str(report.get("sandbox_requested", "unknown")),
        "checks": {
            "total": len(checks),
            "passed": statuses.get("PASS", 0),
            "failed": statuses.get("FAIL", 0),
            "warnings": statuses.get("WARNING", 0),
            "weak": statuses.get("WEAK_PROOF", 0),
            "skipped": statuses.get("SKIPPED", 0),
        },
        "findings": {
            "total": len(findings),
            "high": levels.get("HIGH", 0),
            "medium": levels.get("MEDIUM", 0),
            "low": levels.get("LOW", 0),
        },
        "mutations": {"total": len(mutations), "killed": killed, "survived": survived},
    }


def _graph_metrics(graph: Any) -> dict[str, Any]:
    return {
        "state_hash": graph.state_hash,
        "fresh": bool(graph.fresh),
        "built_at": graph.built_at,
        "files": int(graph.files_scanned),
        "symbols": len(graph.symbols),
        "edges": len(graph.edges),
        "features": len(graph.features),
        "test_mappings": len(graph.test_mappings),
        "routes": len(graph.routes),
        "schemas": len(graph.schemas),
        "languages": dict(graph.languages),
        "changed_files": list(graph.changed_files),
        "removed_files": list(graph.removed_files),
    }


class CommandCenterService:
    """Repository truth adapter used by the local Command Center HTTP API."""

    def __init__(self, repo: Path, out_dir: Path | None = None) -> None:
        self.repo = repo.resolve()
        if not self.repo.exists() or not self.repo.is_dir():
            raise ValueError(f"Repository does not exist: {self.repo}")
        self.out_dir = (out_dir or self.repo / ".basalt").resolve()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @property
    def proof_report_path(self) -> Path:
        return self.out_dir / "proof-report.json"

    @property
    def graph_store_path(self) -> Path:
        return self.out_dir / "knowledge-graph.sqlite3"

    @property
    def factory_state_path(self) -> Path:
        return self.out_dir / "factory-state.sqlite3"

    @property
    def private_beta_root(self) -> Path:
        return self.out_dir / "private-beta"

    def private_beta(self) -> PrivateBetaPlatform:
        return PrivateBetaPlatform(self.private_beta_root)

    def _config_and_excludes(self):
        config = load_config(self.repo)
        excludes = sorted(set(config.scan_exclude + config.graph_exclude))
        return config, excludes

    def ensure_graph(self, force: bool = False):
        config, excludes = self._config_and_excludes()
        graph = build_project_graph(self.repo, self.graph_store_path, excludes, force=force)
        write_graph_artifacts(graph, self.out_dir)
        return graph

    def proof_report(self) -> dict[str, Any]:
        return _read_json(self.proof_report_path, {})

    def recent_runs(self) -> list[dict[str, Any]]:
        return list_agent_runs(self.repo, self.out_dir)

    def recent_factory_runs(self) -> list[dict[str, Any]]:
        return list_factory_runs(self.repo, self.out_dir)

    def factory_transactions(self) -> list[dict[str, Any]]:
        snapshot = StateCoordinator(self.factory_state_path).snapshot()
        factory_runs = {item.get("run_id"): item for item in self.recent_factory_runs()}
        rows: list[dict[str, Any]] = []
        for transaction in snapshot.get("transactions", []):
            run_id = str(transaction.get("run_id", ""))
            run = factory_runs.get(run_id, {})
            rows.append(
                {
                    "kind": "factory",
                    "transaction_type": "FACTORY_STATE",
                    "run_id": run_id,
                    "task": str(transaction.get("summary") or run.get("product_name") or "Factory state transaction"),
                    "status": str(transaction.get("status", "UNKNOWN")),
                    "risk": "GOVERNED",
                    "updated_at": str(transaction.get("finished_at") or transaction.get("created_at") or ""),
                    "created_at": str(transaction.get("created_at") or ""),
                    "base_version": int(transaction.get("base_version", 0) or 0),
                    "result_version": transaction.get("result_version"),
                    "product_name": str(run.get("product_name") or ""),
                    "target_path": str(run.get("target_path") or ""),
                    "proof_status": str(run.get("proof_status") or ""),
                    "proof_score": int(run.get("proof_score", 0) or 0),
                    "rollback_available": False,
                }
            )
        return rows

    def governed_transactions(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for run in self.recent_runs():
            item = dict(run)
            item.setdefault("kind", "agent")
            item.setdefault("transaction_type", "AGENT_PATCH")
            item.setdefault("rollback_available", str(item.get("status")) == "VERIFIED")
            rows.append(item)
        rows.extend(self.factory_transactions())
        rows.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        return rows

    def artifacts(self) -> list[dict[str, Any]]:
        allowed_names = {
            "proof-report.json",
            "proof-report.md",
            "basalt-patch-plan.md",
            "basalt-dashboard.html",
            "knowledge-graph.json",
            "knowledge-graph.md",
            "impact-analysis.json",
            "impact-analysis.md",
            "context-pack.json",
            "context-pack.md",
            "context-manifest.json",
            "command-center-snapshot.json",
            "basalt-design-tokens.json",
            "basalt-design-system.md",
            "design-system-audit.json",
        }
        results: list[dict[str, Any]] = []
        for name in sorted(allowed_names):
            path = self.out_dir / name
            if not path.exists() or not path.is_file():
                continue
            results.append(
                {
                    "id": name,
                    "name": name,
                    "path": _safe_relative(path, self.repo),
                    "size_bytes": path.stat().st_size,
                    "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                    "mime_type": mimetypes.guess_type(path.name)[0] or "text/plain",
                }
            )
        run_root = self.out_dir / "agent-runs"
        if run_root.exists():
            for run_file in sorted(run_root.glob("*/run.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:20]:
                run_id = run_file.parent.name
                results.append(
                    {
                        "id": f"run:{run_id}",
                        "name": f"Agent run {run_id}",
                        "path": _safe_relative(run_file, self.repo),
                        "size_bytes": run_file.stat().st_size,
                        "modified_at": datetime.fromtimestamp(run_file.stat().st_mtime, timezone.utc).isoformat(),
                        "mime_type": "application/json",
                    }
                )
        factory_root = self.out_dir / "factory-runs"
        if factory_root.exists():
            for run_file in sorted(factory_root.glob("*/run.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:20]:
                run_id = run_file.parent.name
                results.append(
                    {
                        "id": f"factory:{run_id}",
                        "name": f"Factory run {run_id}",
                        "path": _safe_relative(run_file, self.repo),
                        "size_bytes": run_file.stat().st_size,
                        "modified_at": datetime.fromtimestamp(run_file.stat().st_mtime, timezone.utc).isoformat(),
                        "mime_type": "application/json",
                    }
                )
        return results

    def read_artifact(self, artifact_id: str) -> dict[str, Any]:
        candidates: dict[str, Path] = {item["id"]: self.repo / item["path"] for item in self.artifacts()}
        path = candidates.get(artifact_id)
        if path is None or not path.exists():
            raise FileNotFoundError("Artifact not found.")
        resolved = path.resolve()
        if self.out_dir not in resolved.parents and resolved != self.out_dir:
            raise PermissionError("Artifact is outside the Basalt evidence directory.")
        size = resolved.stat().st_size
        if size > MAX_ARTIFACT_BYTES:
            raise ValueError("Artifact is too large for inline viewing.")
        text = resolved.read_text(encoding="utf-8", errors="replace")
        payload: Any = text
        if resolved.suffix == ".json":
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = text
        return {
            "id": artifact_id,
            "name": resolved.name,
            "path": _safe_relative(resolved, self.repo),
            "size_bytes": size,
            "content": payload,
        }

    def overview(self) -> dict[str, Any]:
        with self._lock:
            config, _ = self._config_and_excludes()
            graph = self.ensure_graph()
            report = self.proof_report()
            runs = self.recent_runs()
            transactions = self.governed_transactions()
            factory_runs = self.recent_factory_runs()
            status_counts = Counter(str(item.get("status", "UNKNOWN")) for item in transactions)
            factory_status_counts = Counter(str(item.get("status", "UNKNOWN")) for item in factory_runs)
            beta_snapshot = self.private_beta().snapshot()
            agent_pending = [
                {**item, "kind": "agent", "action": "approve"}
                for item in runs
                if str(item.get("status")) == "AWAITING_APPROVAL"
            ]

            deployment_pending = []
            for item in beta_snapshot.get("deployments", {}).get("deployments", []):
                deployment_status = str(item.get("status", "UNKNOWN"))
                if deployment_status not in {"AWAITING_APPROVAL", "APPROVED"}:
                    continue

                environment = str(item.get("environment", "deployment")).lower()
                deployment_pending.append({
                    **item,
                    "kind": "deployment",
                    "run_id": str(item.get("deployment_id", "")),
                    "task": (
                        f"Approve {environment} deployment"
                        if deployment_status == "AWAITING_APPROVAL"
                        else f"Promote {environment} deployment"
                    ),
                    "risk": "HIGH" if environment == "production" else "MEDIUM",
                    "role": "Release control",
                    "action": (
                        "approve"
                        if deployment_status == "AWAITING_APPROVAL"
                        else "promote"
                    ),
                })

            pending = agent_pending + deployment_pending
            verified = [item for item in transactions if str(item.get("status")) in {"VERIFIED", "COMMITTED"}]
            rolled_back = [item for item in transactions if str(item.get("status")) == "ROLLED_BACK"]
            project_name = str(report.get("project_name") or config.project_name or self.repo.name)
            return {
                "api_version": COMMAND_CENTER_API_VERSION,
                "generated_at": _now(),
                "platform": "Basalt v2.5 Private Beta Full Build System",
                "project": {
                    "name": project_name,
                    "path": str(self.repo),
                    "type": str(report.get("project_type") or config.project_type),
                    "state_hash": graph.state_hash,
                },
                "truth": {
                    "status": str(report.get("final_status", "NOT_RUN")),
                    "score": int(report.get("score", 0) or 0),
                    "risk": _risk_level(report, runs),
                    "graph_fresh": bool(graph.fresh),
                    "last_verified_at": str(report.get("finished_at", "")),
                    "intent": "Plan, build, prove, and safely evolve software through governed factory transactions.",
                    "current_phase": "Private Beta Full Build System",
                },
                "proof": _proof_metrics(report),
                "graph": _graph_metrics(graph),
                "approvals": {"pending": len(pending), "items": pending[:10]},
                "transactions": {
                    "total": len(transactions),
                    "verified": len(verified),
                    "rolled_back": len(rolled_back),
                    "status_counts": dict(status_counts),
                    "recent": transactions[:20],
                },
                "factory": {
                    "total": len(factory_runs),
                    "verified": factory_status_counts.get("VERIFIED", 0),
                    "blocked": factory_status_counts.get("BLOCKED", 0),
                    "rolled_back": factory_status_counts.get("ROLLED_BACK", 0),
                    "status_counts": dict(factory_status_counts),
                    "recent": factory_runs[:12],
                    "supported_templates": ["python-service", "api-service", "fullstack-lite", "web-app", "saas-starter"],
                },
                "private_beta": beta_snapshot,
                "artifacts": {"count": len(self.artifacts()), "items": self.artifacts()},
                "roadmap": [
                    {"phase": 0, "name": "Vision + Grant/Demo MVP", "status": "COMPLETE"},
                    {"phase": 1, "name": "Alpha Proof Platform", "status": "COMPLETE"},
                    {"phase": 2, "name": "Knowledge Graph + Context Compiler", "status": "COMPLETE"},
                    {"phase": 3, "name": "Agent-Assisted Safe Fixes", "status": "COMPLETE"},
                    {"phase": 4, "name": "Command Center Web App", "status": "COMPLETE"},
                    {"phase": 5, "name": "Alpha AI Software Factory", "status": "COMPLETE"},
                    {"phase": 6, "name": "Private Beta Full Build System", "status": "ACTIVE"},
                    {"phase": 7, "name": "Production Basalt v1", "status": "UPCOMING"},
                    {"phase": 8, "name": "Full Basalt Final Vision", "status": "UPCOMING"},
                ],
            }

    def run_detail(self, run_id: str) -> dict[str, Any]:
        run, run_dir = load_agent_run(self.repo, run_id, self.out_dir)
        data = run.to_dict()
        data["artifact_files"] = [
            _safe_relative(path, self.repo)
            for path in sorted(run_dir.iterdir())
            if path.is_file()
        ]
        return data

    def impact(self, target: str, depth: int = 3) -> dict[str, Any]:
        if not target.strip():
            raise ValueError("Impact target is required.")
        if depth < 0 or depth > 8:
            raise ValueError("Impact depth must be between 0 and 8.")
        with self._lock:
            graph = self.ensure_graph()
            result = analyze_impact(graph, target.strip(), depth=depth)
            data = asdict(result)
            (self.out_dir / "impact-analysis.json").write_text(
                json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
            )
            (self.out_dir / "impact-analysis.md").write_text(render_impact_markdown(result), encoding="utf-8")
            return data

    def context(
        self,
        task: str,
        role: str,
        targets: list[str],
        budget: int | None = None,
    ) -> dict[str, Any]:
        if not task.strip():
            raise ValueError("Context task is required.")
        config, excludes = self._config_and_excludes()
        selected_budget = budget if budget is not None else config.context_token_budget
        if selected_budget < 500 or selected_budget > 100_000:
            raise ValueError("Context budget must be between 500 and 100000 tokens.")
        with self._lock:
            pack, artifacts = compile_context_for_repo(
                self.repo,
                self.out_dir,
                task=task.strip(),
                agent_role=role.strip() or "CodeReviewAgent",
                targets=[str(item).strip() for item in targets if str(item).strip()],
                token_budget=selected_budget,
                excluded_paths=excludes,
                refresh=config.graph_auto_refresh,
            )
            data = asdict(pack)
            data["artifacts"] = [str(item) for item in artifacts]
            return data

    def factory_runs(self) -> list[dict[str, Any]]:
        return self.recent_factory_runs()

    def factory_run_detail(self, run_id: str) -> dict[str, Any]:
        return load_factory_run(self.repo, run_id, self.out_dir).to_dict()

    def factory_state(self) -> dict[str, Any]:
        return factory_snapshot(self.repo, self.out_dir)

    def factory_plan(
        self,
        prompt: str,
        name: str,
        template: str = "python-service",
        users: list[str] | None = None,
        constraints: list[str] | None = None,
        privacy: str = "local",
    ) -> dict[str, Any]:
        if not prompt.strip() or not name.strip():
            raise ValueError("Product name and product intent are required.")
        with self._lock:
            run = plan_factory_run(
                self.repo,
                prompt.strip(),
                name.strip(),
                template=template,
                target_users=users or [],
                constraints=constraints or [],
                privacy_mode=privacy,
                out_dir=self.out_dir,
            )
            return run.to_dict()

    def factory_build(self, run_id: str, sandbox: str = "temp") -> dict[str, Any]:
        run = load_factory_run(self.repo, run_id, self.out_dir)
        safe_name = re.sub(r"[^a-z0-9]+", "-", run.product_name.lower()).strip("-") or run.run_id
        target = self.repo.parent / "basalt-products" / f"{safe_name}-{run.run_id[-8:]}"
        with self._lock:
            return build_factory_run(
                self.repo,
                run_id,
                target,
                sandbox=sandbox,
                out_dir=self.out_dir,
            ).to_dict()

    def beta_state(self) -> dict[str, Any]:
        return self.private_beta().snapshot()

    def beta_bootstrap(self, email: str, display_name: str, team_name: str) -> dict[str, Any]:
        if not email.strip() or not display_name.strip() or not team_name.strip():
            raise ValueError("Email, display name, and team name are required.")
        return self.private_beta().bootstrap(email.strip(), display_name.strip(), team_name.strip())

    def beta_add_project(
        self,
        team_id: str,
        name: str,
        repo_path: str,
        created_by: str,
        template: str = "fullstack-lite",
        privacy_mode: str = "local",
    ) -> dict[str, Any]:
        return self.private_beta().add_project(
            team_id.strip(), name.strip(), Path(repo_path), created_by.strip(), template, privacy_mode
        )

    def beta_submit_job(
        self,
        project_id: str,
        job_type: str,
        payload: dict[str, Any],
        created_by: str,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        return self.private_beta().submit_job(
            project_id.strip(), job_type.strip(), payload, created_by.strip(), idempotency_key.strip()
        )

    def beta_run_job(self, job_id: str, worker_id: str = "command-center-worker") -> dict[str, Any]:
        return self.private_beta().run_job(job_id.strip(), worker_id.strip())

    def beta_cancel_job(self, job_id: str, actor: str, reason: str) -> dict[str, Any]:
        return self.private_beta().jobs.cancel(job_id.strip(), actor.strip(), reason.strip()).to_dict()

    def beta_retry_job(self, job_id: str, actor: str) -> dict[str, Any]:
        return self.private_beta().jobs.retry(job_id.strip(), actor.strip()).to_dict()

    def beta_approve_deployment(self, deployment_id: str, actor: str, reason: str) -> dict[str, Any]:
        return self.private_beta().deployments.approve(deployment_id.strip(), actor.strip(), reason.strip()).to_dict()

    def beta_promote_deployment(self, deployment_id: str, actor: str) -> dict[str, Any]:
        return self.private_beta().deployments.promote(deployment_id.strip(), actor.strip()).to_dict()

    def beta_rollback_deployment(self, deployment_id: str, actor: str, reason: str) -> dict[str, Any]:
        return self.private_beta().deployments.rollback(deployment_id.strip(), actor.strip(), reason.strip()).to_dict()

    def verify(self, sandbox: str | None = None) -> dict[str, Any]:
        if sandbox not in {None, "auto", "temp", "docker"}:
            raise ValueError("Sandbox must be auto, temp, or docker.")
        with self._lock:
            report = verify_repo(self.repo, sandbox_override=sandbox, output_dir=self.out_dir)
            write_json_report(report, self.proof_report_path)
            write_markdown_report(report, self.out_dir / "proof-report.md")
            write_dashboard(report, self.out_dir / "basalt-dashboard.html")
            return report.to_dict()

    def approve(self, run_id: str, actor: str, reason: str) -> dict[str, Any]:
        if not actor.strip() or not reason.strip():
            raise ValueError("Approver and reason are required.")
        with self._lock:
            run, token = approve_agent_run(self.repo, run_id, actor.strip(), reason.strip(), self.out_dir)
            data = run.to_dict()
            data["approval_token"] = token
            return data

    def reject(self, run_id: str, actor: str, reason: str) -> dict[str, Any]:
        if not actor.strip() or not reason.strip():
            raise ValueError("Actor and reason are required.")
        with self._lock:
            return reject_agent_run(self.repo, run_id, actor.strip(), reason.strip(), self.out_dir).to_dict()

    def apply(self, run_id: str, approval_token: str, sandbox: str | None = None) -> dict[str, Any]:
        if not approval_token.strip():
            raise ValueError("One-time approval token is required.")
        with self._lock:
            return apply_agent_run(
                self.repo,
                run_id,
                approval_token=approval_token.strip(),
                out_dir=self.out_dir,
                sandbox=sandbox,
            ).to_dict()

    def rollback(self, run_id: str, actor: str, reason: str) -> dict[str, Any]:
        if not actor.strip() or not reason.strip():
            raise ValueError("Actor and reason are required.")
        with self._lock:
            return rollback_agent_run(self.repo, run_id, actor.strip(), reason.strip(), self.out_dir).to_dict()


__all__ = ["CommandCenterService", "COMMAND_CENTER_API_VERSION", "AgentRunError"]
