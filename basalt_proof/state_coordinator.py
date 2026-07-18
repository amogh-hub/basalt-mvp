from __future__ import annotations

import contextlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class StateConflictError(RuntimeError):
    pass


class ContractLockError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectState:
    version: int
    state_hash: str
    committed_at: str
    run_id: str = ""
    summary: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateCoordinator:
    """Monotonic project state and contract-lock coordinator for the alpha factory."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextlib.contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
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
                CREATE TABLE IF NOT EXISTS state_versions (
                    version INTEGER PRIMARY KEY,
                    state_hash TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    run_id TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS contract_locks (
                    name TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    base_version INTEGER NOT NULL,
                    acquired_at TEXT NOT NULL,
                    run_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS state_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    base_version INTEGER NOT NULL,
                    result_version INTEGER,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL DEFAULT ''
                );
                """
            )

    def bootstrap(self, initial_hash: str) -> ProjectState:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM state_versions ORDER BY version DESC LIMIT 1").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO state_versions(version, state_hash, committed_at, summary) VALUES(0, ?, ?, ?)",
                    (initial_hash, _now(), "Factory state initialized"),
                )
                return ProjectState(0, initial_hash, _now(), summary="Factory state initialized")
            return ProjectState(row["version"], row["state_hash"], row["committed_at"], row["run_id"], row["summary"])

    def current(self) -> ProjectState:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM state_versions ORDER BY version DESC LIMIT 1").fetchone()
            if row is None:
                return ProjectState(0, "", "")
            return ProjectState(row["version"], row["state_hash"], row["committed_at"], row["run_id"], row["summary"])

    def begin(self, run_id: str, base_version: int, summary: str) -> None:
        current = self.current()
        if current.version != base_version:
            raise StateConflictError(f"Stale factory state: expected {base_version}, current is {current.version}.")
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO state_transactions(run_id, base_version, status, summary, created_at) VALUES(?, ?, 'OPEN', ?, ?)",
                (run_id, base_version, summary, _now()),
            )

    def acquire_locks(self, names: list[str], owner: str, run_id: str, base_version: int) -> None:
        current = self.current()
        if current.version != base_version:
            raise StateConflictError(f"Cannot acquire locks for stale state {base_version}; current is {current.version}.")
        normalized = sorted({name.strip() for name in names if name.strip()})
        with self._connection() as connection:
            for name in normalized:
                row = connection.execute("SELECT * FROM contract_locks WHERE name = ?", (name,)).fetchone()
                if row and row["run_id"] != run_id:
                    raise ContractLockError(f"Contract lock {name} is held by {row['owner']} for {row['run_id']}.")
            for name in normalized:
                connection.execute(
                    "INSERT OR REPLACE INTO contract_locks(name, owner, base_version, acquired_at, run_id) VALUES(?, ?, ?, ?, ?)",
                    (name, owner, base_version, _now(), run_id),
                )

    def release_locks(self, run_id: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM contract_locks WHERE run_id = ?", (run_id,))

    def commit(self, run_id: str, base_version: int, new_hash: str, summary: str) -> ProjectState:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM state_versions ORDER BY version DESC LIMIT 1").fetchone()
            current_version = int(row["version"]) if row else 0
            if current_version != base_version:
                raise StateConflictError(f"Compare-and-swap rejected: expected state {base_version}, current is {current_version}.")
            new_version = current_version + 1
            timestamp = _now()
            connection.execute(
                "INSERT INTO state_versions(version, state_hash, committed_at, run_id, summary) VALUES(?, ?, ?, ?, ?)",
                (new_version, new_hash, timestamp, run_id, summary),
            )
            connection.execute(
                "UPDATE state_transactions SET result_version = ?, status = 'COMMITTED', finished_at = ? WHERE run_id = ? AND status = 'OPEN'",
                (new_version, timestamp, run_id),
            )
            connection.execute("DELETE FROM contract_locks WHERE run_id = ?", (run_id,))
            return ProjectState(new_version, new_hash, timestamp, run_id, summary)

    def abort(self, run_id: str, summary: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE state_transactions SET status = 'ABORTED', summary = ?, finished_at = ? WHERE run_id = ? AND status = 'OPEN'",
                (summary, _now(), run_id),
            )
            connection.execute("DELETE FROM contract_locks WHERE run_id = ?", (run_id,))

    def snapshot(self) -> dict:
        current = self.current()
        with self._connection() as connection:
            locks = [dict(row) for row in connection.execute("SELECT * FROM contract_locks ORDER BY name")]
            transactions = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM state_transactions ORDER BY id DESC LIMIT 50"
                )
            ]
        return {"current": current.__dict__, "locks": locks, "transactions": transactions}
