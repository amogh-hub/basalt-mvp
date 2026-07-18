from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import sqlite3
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .beta_models import DeploymentRecord, DeploymentStatus


class DeploymentError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deployment_id(project_id: str, environment: str, source: Path) -> str:
    seed = f"{project_id}:{environment}:{source}:{_now()}"
    return f"dep_{hashlib.sha256(seed.encode()).hexdigest()[:14]}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DeploymentManager:
    """Private-beta deployment control plane.

    It packages verified products, records approval gates, promotes immutable artifacts, and preserves rollback provenance.
    It intentionally does not claim a production cloud deployment provider.
    """

    def __init__(self, database_path: Path, artifact_root: Path) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_root = artifact_root.resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextlib.contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS deployments (
                    deployment_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    status TEXT NOT NULL,
                    artifact_path TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    proof_status TEXT NOT NULL,
                    proof_score INTEGER NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_by TEXT NOT NULL DEFAULT '',
                    approval_reason TEXT NOT NULL DEFAULT '',
                    promoted_at TEXT NOT NULL DEFAULT '',
                    rollback_of TEXT NOT NULL DEFAULT '',
                    rollback_reason TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS deployment_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deployment_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_deployments_project ON deployments(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_deployment_events ON deployment_events(deployment_id, event_id);
                """
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> DeploymentRecord:
        try:
            metadata = json.loads(row["metadata_json"])
        except json.JSONDecodeError:
            metadata = {}
        return DeploymentRecord(
            deployment_id=row["deployment_id"],
            project_id=row["project_id"],
            environment=row["environment"],
            status=DeploymentStatus(row["status"]),
            artifact_path=row["artifact_path"],
            artifact_sha256=row["artifact_sha256"],
            source_path=row["source_path"],
            proof_status=row["proof_status"],
            proof_score=int(row["proof_score"]),
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approved_by=row["approved_by"],
            approval_reason=row["approval_reason"],
            promoted_at=row["promoted_at"],
            rollback_of=row["rollback_of"],
            rollback_reason=row["rollback_reason"],
            metadata=metadata,
        )

    def _event(self, connection: sqlite3.Connection, deployment_id: str, event: str, actor: str, detail: str) -> None:
        connection.execute(
            "INSERT INTO deployment_events(deployment_id, event, actor, detail, created_at) VALUES(?, ?, ?, ?, ?)",
            (deployment_id, event, actor, detail, _now()),
        )

    @staticmethod
    def _load_proof(path: Path) -> tuple[str, int, dict[str, Any]]:
        if not path.exists():
            raise DeploymentError(f"Proof report not found: {path}")
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DeploymentError("Proof report is invalid JSON.") from exc
        return str(report.get("final_status", "UNKNOWN")), int(report.get("score", 0) or 0), report

    def package_verified_product(
        self,
        project_id: str,
        source_dir: Path,
        proof_report_path: Path,
        environment: str,
        created_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> DeploymentRecord:
        source = source_dir.expanduser().resolve()
        if not source.exists() or not source.is_dir():
            raise DeploymentError(f"Product source does not exist: {source}")
        selected_environment = environment.strip().lower()
        if selected_environment not in {"preview", "staging", "production"}:
            raise DeploymentError(f"Unsupported deployment environment: {environment}")
        proof_status, proof_score, report = self._load_proof(proof_report_path)
        if proof_status != "VERIFIED" or proof_score < 80:
            raise DeploymentError(f"Deployment requires VERIFIED proof with score >= 80; got {proof_status} {proof_score}/100.")

        deployment_id = _deployment_id(project_id, selected_environment, source)
        directory = self.artifact_root / project_id / deployment_id
        directory.mkdir(parents=True, exist_ok=False)
        artifact = directory / "release.tar.gz"
        with tarfile.open(artifact, "w:gz") as archive:
            for path in sorted(source.rglob("*")):
                if ".git" in path.relative_to(source).parts:
                    continue
                archive.add(path, arcname=Path(source.name) / path.relative_to(source), recursive=False)
        artifact_hash = _sha256(artifact)
        manifest = {
            "deployment_id": deployment_id,
            "project_id": project_id,
            "environment": selected_environment,
            "source_path": str(source),
            "artifact": str(artifact),
            "artifact_sha256": artifact_hash,
            "proof": {
                "status": proof_status,
                "score": proof_score,
                "report": str(proof_report_path.resolve()),
                "sandbox": report.get("sandbox", "unknown"),
            },
            "created_at": _now(),
            "created_by": created_by,
            "metadata": metadata or {},
        }
        (directory / "deployment-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        status = DeploymentStatus.PACKAGED if selected_environment == "preview" else DeploymentStatus.AWAITING_APPROVAL
        record = DeploymentRecord(
            deployment_id=deployment_id,
            project_id=project_id,
            environment=selected_environment,
            status=status,
            artifact_path=str(artifact),
            artifact_sha256=artifact_hash,
            source_path=str(source),
            proof_status=proof_status,
            proof_score=proof_score,
            created_by=created_by,
            created_at=_now(),
            updated_at=_now(),
            metadata=metadata or {},
        )
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO deployments(deployment_id, project_id, environment, status, artifact_path, artifact_sha256,
                                        source_path, proof_status, proof_score, created_by, created_at, updated_at,
                                        metadata_json)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.deployment_id,
                    record.project_id,
                    record.environment,
                    record.status.value,
                    record.artifact_path,
                    record.artifact_sha256,
                    record.source_path,
                    record.proof_status,
                    record.proof_score,
                    record.created_by,
                    record.created_at,
                    record.updated_at,
                    json.dumps(record.metadata, sort_keys=True),
                ),
            )
            self._event(connection, deployment_id, "PACKAGED", created_by, selected_environment)
        return record

    def get(self, deployment_id: str) -> DeploymentRecord:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
        if not row:
            raise DeploymentError(f"Deployment not found: {deployment_id}")
        return self._row_to_record(row)

    def list(self, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connection() as connection:
            if project_id:
                rows = connection.execute(
                    "SELECT * FROM deployments WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                    (project_id, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute("SELECT * FROM deployments ORDER BY created_at DESC LIMIT ?", (safe_limit,)).fetchall()
        return [self._row_to_record(row).to_dict() for row in rows]

    def approve(self, deployment_id: str, actor: str, reason: str) -> DeploymentRecord:
        record = self.get(deployment_id)
        if record.status != DeploymentStatus.AWAITING_APPROVAL:
            raise DeploymentError("Only deployments awaiting approval may be approved.")
        with self._connection() as connection:
            connection.execute(
                "UPDATE deployments SET status = 'APPROVED', approved_by = ?, approval_reason = ?, updated_at = ? WHERE deployment_id = ?",
                (actor, reason[:1000], _now(), deployment_id),
            )
            self._event(connection, deployment_id, "APPROVED", actor, reason[:500])
        return self.get(deployment_id)

    def promote(self, deployment_id: str, actor: str) -> DeploymentRecord:
        record = self.get(deployment_id)
        if record.environment in {"staging", "production"} and record.status != DeploymentStatus.APPROVED:
            raise DeploymentError(f"{record.environment} promotion requires approval.")
        if record.environment == "preview" and record.status != DeploymentStatus.PACKAGED:
            raise DeploymentError("Preview deployment must be in PACKAGED state.")
        promoted = _now()
        with self._connection() as connection:
            connection.execute(
                "UPDATE deployments SET status = 'PROMOTED', promoted_at = ?, updated_at = ? WHERE deployment_id = ?",
                (promoted, promoted, deployment_id),
            )
            self._event(connection, deployment_id, "PROMOTED", actor, record.environment)
        return self.get(deployment_id)

    def rollback(self, deployment_id: str, actor: str, reason: str) -> DeploymentRecord:
        record = self.get(deployment_id)
        if record.status != DeploymentStatus.PROMOTED:
            raise DeploymentError("Only promoted deployments may be rolled back.")
        with self._connection() as connection:
            connection.execute(
                "UPDATE deployments SET status = 'ROLLED_BACK', rollback_reason = ?, updated_at = ? WHERE deployment_id = ?",
                (reason[:1000], _now(), deployment_id),
            )
            self._event(connection, deployment_id, "ROLLED_BACK", actor, reason[:500])
        return self.get(deployment_id)

    def restore_artifact(self, deployment_id: str, destination: Path) -> Path:
        record = self.get(deployment_id)
        artifact = Path(record.artifact_path)
        if not artifact.exists() or _sha256(artifact) != record.artifact_sha256:
            raise DeploymentError("Deployment artifact failed integrity verification.")
        target = destination.expanduser().resolve()
        if target.exists() and any(target.iterdir()):
            raise DeploymentError("Restore destination must be empty or absent.")
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(artifact, "r:gz") as archive:
            root = target.resolve()
            for member in archive.getmembers():
                candidate = (target / member.name).resolve()
                if root not in candidate.parents and candidate != root:
                    raise DeploymentError("Deployment archive contains path traversal.")
            archive.extractall(target, filter="data")
        return target

    def events(self, deployment_id: str) -> list[dict[str, Any]]:
        self.get(deployment_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM deployment_events WHERE deployment_id = ? ORDER BY event_id", (deployment_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def snapshot(self) -> dict[str, Any]:
        with self._connection() as connection:
            rows = connection.execute("SELECT status, COUNT(*) AS count FROM deployments GROUP BY status").fetchall()
        return {"counts": {row["status"]: int(row["count"]) for row in rows}, "deployments": self.list(limit=50)}
