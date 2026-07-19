from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .beta_models import BetaJob, WorkspaceRole
from .deployment_manager import DeploymentManager
from .job_queue import DurableJobQueue, JobQueueError
from .proof import verify_repo
from .provider_registry import ProviderRegistry
from .software_factory import create_product, plan_factory_run
from .workspace_registry import WorkspaceRegistry
from .workspace_runtime import PRIVATE_BETA_PROFILE, WorkspaceManager


class PrivateBetaError(RuntimeError):
    pass


class PrivateBetaPlatform:
    """Local private-beta control plane for persistent projects, durable jobs, providers, and deployments."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry = WorkspaceRegistry(self.root / "private-beta.sqlite3")
        self.jobs = DurableJobQueue(self.root / "jobs.sqlite3")
        self.providers = ProviderRegistry(self.root / "providers.json")
        self.workspaces = WorkspaceManager(self.root / "workspaces")
        self.deployments = DeploymentManager(self.root / "deployments.sqlite3", self.root / "deployment-artifacts")
        (self.root / "job-artifacts").mkdir(parents=True, exist_ok=True)

    def bootstrap(self, email: str, display_name: str, team_name: str) -> dict[str, Any]:
        user = self.registry.create_user(email, display_name)
        existing = next((item for item in self.registry.snapshot()["teams"] if item["created_by"] == user.user_id), None)
        team = self.registry.get_team(existing["team_id"]) if existing else self.registry.create_team(team_name, user.user_id)
        return {"user": user.__dict__, "team": team.__dict__}

    def add_project(
        self,
        team_id: str,
        name: str,
        repo_path: Path,
        created_by: str,
        template: str = "fullstack-lite",
        privacy_mode: str = "local",
    ) -> dict[str, Any]:
        project = self.registry.create_project(
            team_id,
            name,
            repo_path,
            created_by,
            template=template,
            privacy_mode=privacy_mode,
        )
        return project.__dict__

    def submit_job(
        self,
        project_id: str,
        job_type: str,
        payload: dict[str, Any],
        created_by: str,
        idempotency_key: str = "",
        max_attempts: int = 2,
    ) -> dict[str, Any]:
        self.registry.require_project_role(project_id, created_by, WorkspaceRole.DEVELOPER)
        allowed = {"VERIFY_PROJECT", "FACTORY_PLAN", "FACTORY_CREATE", "PACKAGE_PREVIEW"}
        selected = job_type.strip().upper()
        if selected not in allowed:
            raise PrivateBetaError(f"Unsupported private-beta job type: {selected}")
        job = self.jobs.submit(project_id, selected, payload, created_by, idempotency_key, max_attempts)
        project = self.registry.get_project(project_id)
        self.registry.record_activity(project.team_id, project_id, created_by, "JOB_SUBMITTED", f"Submitted {selected}.", {"job_id": job.job_id})
        return job.to_dict()

    def _job_artifact_dir(self, job_id: str) -> Path:
        path = (self.root / "job-artifacts" / job_id).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _handle_verify(self, job: BetaJob, project) -> dict[str, Any]:
        manifest = self.workspaces.prepare(job.job_id, Path(project.repo_path), PRIVATE_BETA_PROFILE)
        workspace = Path(manifest["workspace"])
        output = self._job_artifact_dir(job.job_id) / "proof"
        report = verify_repo(workspace, sandbox_override=str(job.payload.get("sandbox", "temp")), output_dir=output)
        from .report import write_json_report, write_markdown_report

        write_json_report(report, output / "proof-report.json")
        write_markdown_report(report, output / "proof-report.md")
        if not self.workspaces.verify_source_unchanged(manifest):
            raise PrivateBetaError("Registered source repository changed during isolated verification.")
        return {
            "status": report.final_status.value,
            "score": report.score,
            "sandbox": report.sandbox,
            "proof_report": str(output / "proof-report.json"),
            "workspace_manifest": manifest,
        }

    def _handle_factory_plan(self, job: BetaJob, project) -> dict[str, Any]:
        payload = job.payload
        run = plan_factory_run(
            Path(project.repo_path),
            str(payload.get("prompt", "")),
            str(payload.get("name", project.name)),
            template=str(payload.get("template", project.template)),
            privacy_mode=project.privacy_mode,
        )
        return {
            "run_id": run.run_id,
            "status": run.status.value,
            "tasks": len(run.tasks),
            "epochs": len(run.epochs),
            "artifacts": run.artifacts,
        }

    @staticmethod
    def _external_product_target(project, job_id: str) -> Path:
        repo = Path(project.repo_path).expanduser().resolve()
        base = repo.parent / f".{repo.name}-basalt-products"
        target = (base / project.project_id / job_id).resolve()
        if target == repo or repo in target.parents:
            raise PrivateBetaError("Private-beta product target must remain outside the source repository.")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _handle_factory_create(self, job: BetaJob, project) -> dict[str, Any]:
        payload = job.payload
        target = self._external_product_target(project, job.job_id)
        if target.exists():
            shutil.rmtree(target)
        run = create_product(
            Path(project.repo_path),
            str(payload.get("prompt", "")),
            str(payload.get("name", project.name)),
            target,
            template=str(payload.get("template", project.template)),
            privacy_mode=project.privacy_mode,
            sandbox=str(payload.get("sandbox", "temp")),
        )
        return {
            "run_id": run.run_id,
            "status": run.status.value,
            "proof_status": run.proof_status,
            "proof_score": run.proof_score,
            "target": str(target),
            "proof_report": str(target / ".basalt" / "factory-proof" / "proof-report.json"),
        }

    def _handle_package_preview(self, job: BetaJob, project) -> dict[str, Any]:
        source_value = str(job.payload.get("source_path", "")).strip()
        source = (
            Path(source_value).expanduser().resolve()
            if source_value
            else Path(project.repo_path).expanduser().resolve()
        )

        proof_value = str(job.payload.get("proof_report", "")).strip()
        proof_report = (
            Path(proof_value).expanduser().resolve()
            if proof_value
            else source / ".basalt" / "factory-proof" / "proof-report.json"
        )

        record = self.deployments.package_verified_product(
            project.project_id,
            source,
            proof_report,
            str(job.payload.get("environment", "preview")),
            job.created_by,
            metadata={"job_id": job.job_id},
        )
        if record.environment == "preview":
            record = self.deployments.promote(record.deployment_id, job.created_by)
        return record.to_dict()

    def run_next(self, worker_id: str = "beta-worker-1") -> dict[str, Any] | None:
        claimed = self.jobs.claim(worker_id, lease_seconds=900)
        if claimed is None:
            return None
        running = self.jobs.start(claimed.job_id, worker_id, lease_seconds=900)
        project = self.registry.get_project(running.project_id)
        handlers = {
            "VERIFY_PROJECT": self._handle_verify,
            "FACTORY_PLAN": self._handle_factory_plan,
            "FACTORY_CREATE": self._handle_factory_create,
            "PACKAGE_PREVIEW": self._handle_package_preview,
        }
        handler = handlers.get(running.job_type)
        if handler is None:
            completed = self.jobs.fail(running.job_id, worker_id, f"No handler for {running.job_type}.", retryable=False)
            return completed.to_dict()
        try:
            result = handler(running, project)
            completed = self.jobs.complete(running.job_id, worker_id, result)
            self.registry.record_activity(project.team_id, project.project_id, worker_id, "JOB_SUCCEEDED", running.job_type, {"job_id": running.job_id})
            return completed.to_dict()
        except Exception as exc:
            failed = self.jobs.fail(running.job_id, worker_id, str(exc), retryable=True)
            self.registry.record_activity(project.team_id, project.project_id, worker_id, "JOB_FAILED", str(exc), {"job_id": running.job_id})
            return failed.to_dict()

    def run_job(self, job_id: str, worker_id: str = "beta-worker-1") -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if job.status.value not in {"PENDING", "RETRY_WAIT"}:
            raise JobQueueError(f"Job is not runnable: {job.status.value}")
        # Claim ordering is deterministic. If another pending job is earlier, process until this job is reached.
        for _ in range(100):
            result = self.run_next(worker_id)
            if result is None:
                break
            if result["job_id"] == job_id:
                return result
        return self.jobs.get(job_id).to_dict()

    def snapshot(self) -> dict[str, Any]:
        workspace = self.registry.snapshot()
        jobs = self.jobs.snapshot()
        providers = self.providers.snapshot()
        deployments = self.deployments.snapshot()
        return {
            "version": "2.5.0b4",
            "root": str(self.root),
            "workspace": workspace,
            "jobs": jobs,
            "providers": providers,
            "deployments": deployments,
            "runtime": self.workspaces.snapshot(),
            "readiness": {
                "persistent_projects": True,
                "durable_jobs": True,
                "rbac": True,
                "provider_registry": True,
                "preview_deployments": True,
                "production_cloud_deployments": False,
            },
        }

    def write_snapshot(self, path: Path | None = None) -> Path:
        target = path or self.root / "private-beta-snapshot.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")
        return target
