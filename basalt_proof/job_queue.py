from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .beta_models import BetaJob, JobStatus


class JobQueueError(RuntimeError):
    pass


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return _now_dt().isoformat()


def _job_id(project_id: str, job_type: str, key: str) -> str:
    seed = f"{project_id}:{job_type}:{key}:{_now()}"
    return f"job_{hashlib.sha256(seed.encode()).hexdigest()[:14]}"


def _loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


class DurableJobQueue:
    """SQLite-backed private-beta job queue with leases, retries, cancellation, and idempotency."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextlib.contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=15)
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
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 2,
                    worker_id TEXT NOT NULL DEFAULT '',
                    lease_expires_at TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    cancellation_reason TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS job_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idempotency
                    ON jobs(project_id, idempotency_key) WHERE idempotency_key != '';
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id, event_id);
                """
            )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> BetaJob:
        return BetaJob(
            job_id=row["job_id"],
            project_id=row["project_id"],
            job_type=row["job_type"],
            status=JobStatus(row["status"]),
            payload=_loads(row["payload_json"], {}),
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            idempotency_key=row["idempotency_key"],
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            worker_id=row["worker_id"],
            lease_expires_at=row["lease_expires_at"],
            result=_loads(row["result_json"], {}),
            error=row["error"],
            cancellation_reason=row["cancellation_reason"],
        )

    def _event(self, connection: sqlite3.Connection, job_id: str, event: str, actor: str, detail: str) -> None:
        connection.execute(
            "INSERT INTO job_events(job_id, event, actor, detail, created_at) VALUES(?, ?, ?, ?, ?)",
            (job_id, event, actor, detail, _now()),
        )

    def submit(
        self,
        project_id: str,
        job_type: str,
        payload: dict[str, Any],
        created_by: str,
        idempotency_key: str = "",
        max_attempts: int = 2,
    ) -> BetaJob:
        selected_type = job_type.strip().upper()
        if not selected_type:
            raise JobQueueError("A job type is required.")
        attempts = max(1, min(int(max_attempts), 10))
        key = idempotency_key.strip()
        if key:
            with self._connection() as connection:
                existing = connection.execute(
                    "SELECT * FROM jobs WHERE project_id = ? AND idempotency_key = ?", (project_id, key)
                ).fetchone()
                if existing:
                    return self._row_to_job(existing)
        job = BetaJob(
            job_id=_job_id(project_id, selected_type, key or hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:8]),
            project_id=project_id,
            job_type=selected_type,
            status=JobStatus.PENDING,
            payload=dict(payload),
            created_by=created_by,
            created_at=_now(),
            updated_at=_now(),
            idempotency_key=key,
            max_attempts=attempts,
        )
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO jobs(job_id, project_id, job_type, status, payload_json, created_by, created_at, updated_at,
                                 idempotency_key, attempts, max_attempts, worker_id, lease_expires_at, result_json, error,
                                 cancellation_reason)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '{}', '', '')
                """,
                (
                    job.job_id,
                    job.project_id,
                    job.job_type,
                    job.status.value,
                    json.dumps(job.payload, sort_keys=True),
                    job.created_by,
                    job.created_at,
                    job.updated_at,
                    job.idempotency_key,
                    job.attempts,
                    job.max_attempts,
                ),
            )
            self._event(connection, job.job_id, "SUBMITTED", created_by, selected_type)
        return job

    def get(self, job_id: str) -> BetaJob:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            raise JobQueueError(f"Job not found: {job_id}")
        return self._row_to_job(row)

    def list(self, project_id: str | None = None, status: JobStatus | str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if project_id:
            clauses.append("project_id = ?")
            values.append(project_id)
        if status:
            clauses.append("status = ?")
            values.append(JobStatus(status).value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, min(int(limit), 500)))
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT ?", values
            ).fetchall()
        return [self._row_to_job(row).to_dict() for row in rows]

    def _requeue_expired(self, connection: sqlite3.Connection) -> None:
        now = _now()
        rows = connection.execute(
            "SELECT job_id, attempts, max_attempts FROM jobs WHERE status IN ('CLAIMED','RUNNING') AND lease_expires_at != '' AND lease_expires_at < ?",
            (now,),
        ).fetchall()
        for row in rows:
            next_status = JobStatus.RETRY_WAIT.value if int(row["attempts"]) < int(row["max_attempts"]) else JobStatus.FAILED.value
            connection.execute(
                "UPDATE jobs SET status = ?, worker_id = '', lease_expires_at = '', error = ?, updated_at = ? WHERE job_id = ?",
                (next_status, "Worker lease expired.", now, row["job_id"]),
            )
            self._event(connection, row["job_id"], "LEASE_EXPIRED", "system", next_status)

    def claim(self, worker_id: str, lease_seconds: int = 120) -> BetaJob | None:
        if not worker_id.strip():
            raise JobQueueError("A worker id is required.")
        lease = max(10, min(int(lease_seconds), 3600))
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._requeue_expired(connection)
            row = connection.execute(
                "SELECT * FROM jobs WHERE status IN ('PENDING','RETRY_WAIT') ORDER BY created_at, job_id LIMIT 1"
            ).fetchone()
            if row is None:
                connection.execute("COMMIT")
                return None
            lease_expires = (_now_dt() + timedelta(seconds=lease)).isoformat()
            now = _now()
            connection.execute(
                "UPDATE jobs SET status = 'CLAIMED', worker_id = ?, lease_expires_at = ?, updated_at = ? WHERE job_id = ?",
                (worker_id, lease_expires, now, row["job_id"]),
            )
            self._event(connection, row["job_id"], "CLAIMED", worker_id, f"Lease until {lease_expires}")
            connection.execute("COMMIT")
            return self.get(row["job_id"])
        except Exception:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def start(self, job_id: str, worker_id: str, lease_seconds: int = 120) -> BetaJob:
        job = self.get(job_id)
        if job.status != JobStatus.CLAIMED or job.worker_id != worker_id:
            raise JobQueueError("Job must be claimed by this worker before it can start.")
        lease_expires = (_now_dt() + timedelta(seconds=max(10, int(lease_seconds)))).isoformat()
        with self._connection() as connection:
            connection.execute(
                "UPDATE jobs SET status = 'RUNNING', attempts = attempts + 1, lease_expires_at = ?, updated_at = ? WHERE job_id = ?",
                (lease_expires, _now(), job_id),
            )
            self._event(connection, job_id, "STARTED", worker_id, "Job execution started.")
        return self.get(job_id)

    def heartbeat(self, job_id: str, worker_id: str, lease_seconds: int = 120) -> BetaJob:
        job = self.get(job_id)
        if job.worker_id != worker_id or job.status not in {JobStatus.CLAIMED, JobStatus.RUNNING}:
            raise JobQueueError("Only the active worker may heartbeat this job.")
        lease_expires = (_now_dt() + timedelta(seconds=max(10, int(lease_seconds)))).isoformat()
        with self._connection() as connection:
            connection.execute(
                "UPDATE jobs SET lease_expires_at = ?, updated_at = ? WHERE job_id = ?",
                (lease_expires, _now(), job_id),
            )
        return self.get(job_id)

    def complete(self, job_id: str, worker_id: str, result: dict[str, Any]) -> BetaJob:
        job = self.get(job_id)
        if job.worker_id != worker_id or job.status != JobStatus.RUNNING:
            raise JobQueueError("Only the running worker may complete this job.")
        with self._connection() as connection:
            connection.execute(
                "UPDATE jobs SET status = 'SUCCEEDED', result_json = ?, error = '', worker_id = '', lease_expires_at = '', updated_at = ? WHERE job_id = ?",
                (json.dumps(result, sort_keys=True), _now(), job_id),
            )
            self._event(connection, job_id, "SUCCEEDED", worker_id, "Job completed successfully.")
        return self.get(job_id)

    def fail(self, job_id: str, worker_id: str, error: str, retryable: bool = True) -> BetaJob:
        job = self.get(job_id)
        if job.worker_id != worker_id or job.status != JobStatus.RUNNING:
            raise JobQueueError("Only the running worker may fail this job.")
        next_status = JobStatus.RETRY_WAIT if retryable and job.attempts < job.max_attempts else JobStatus.FAILED
        with self._connection() as connection:
            connection.execute(
                "UPDATE jobs SET status = ?, error = ?, worker_id = '', lease_expires_at = '', updated_at = ? WHERE job_id = ?",
                (next_status.value, error[:4000], _now(), job_id),
            )
            self._event(connection, job_id, next_status.value, worker_id, error[:500])
        return self.get(job_id)

    def cancel(self, job_id: str, actor: str, reason: str) -> BetaJob:
        job = self.get(job_id)
        if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
            raise JobQueueError(f"Cannot cancel a terminal job: {job.status.value}")
        with self._connection() as connection:
            connection.execute(
                "UPDATE jobs SET status = 'CANCELLED', cancellation_reason = ?, worker_id = '', lease_expires_at = '', updated_at = ? WHERE job_id = ?",
                (reason[:1000], _now(), job_id),
            )
            self._event(connection, job_id, "CANCELLED", actor, reason[:500])
        return self.get(job_id)

    def retry(self, job_id: str, actor: str) -> BetaJob:
        job = self.get(job_id)
        if job.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
            raise JobQueueError("Only failed or cancelled jobs may be retried manually.")
        with self._connection() as connection:
            connection.execute(
                "UPDATE jobs SET status = 'PENDING', error = '', cancellation_reason = '', worker_id = '', lease_expires_at = '', updated_at = ? WHERE job_id = ?",
                (_now(), job_id),
            )
            self._event(connection, job_id, "RETRIED", actor, "Manual retry requested.")
        return self.get(job_id)

    def events(self, job_id: str) -> list[dict[str, Any]]:
        self.get(job_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM job_events WHERE job_id = ? ORDER BY event_id", (job_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def run_next(
        self,
        worker_id: str,
        handlers: dict[str, Callable[[BetaJob], dict[str, Any]]],
        lease_seconds: int = 300,
    ) -> BetaJob | None:
        claimed = self.claim(worker_id, lease_seconds=lease_seconds)
        if claimed is None:
            return None
        running = self.start(claimed.job_id, worker_id, lease_seconds=lease_seconds)
        handler = handlers.get(running.job_type)
        if handler is None:
            return self.fail(running.job_id, worker_id, f"No handler registered for {running.job_type}.", retryable=False)
        try:
            result = handler(running)
        except Exception as exc:
            return self.fail(running.job_id, worker_id, str(exc), retryable=True)
        return self.complete(running.job_id, worker_id, result)

    def snapshot(self) -> dict[str, Any]:
        with self._connection() as connection:
            rows = connection.execute("SELECT status, COUNT(*) AS count FROM jobs GROUP BY status").fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        return {"counts": counts, "jobs": self.list(limit=50)}
