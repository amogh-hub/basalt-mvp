from __future__ import annotations

import contextlib
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .beta_models import MembershipRecord, ProjectRecord, TeamRecord, UserRecord, WorkspaceRole


class WorkspaceError(RuntimeError):
    pass


_ROLE_RANK = {
    WorkspaceRole.VIEWER.value: 1,
    WorkspaceRole.REVIEWER.value: 2,
    WorkspaceRole.DEVELOPER.value: 3,
    WorkspaceRole.ADMIN.value: 4,
    WorkspaceRole.OWNER.value: 5,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise WorkspaceError("A non-empty name is required.")
    return slug[:64]


def _id(prefix: str, seed: str) -> str:
    digest = hashlib.sha256(f"{prefix}:{seed}:{_now()}".encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


class WorkspaceRegistry:
    """Persistent local control plane for private-beta users, teams, projects, and audit events."""

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
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE'
                );
                CREATE TABLE IF NOT EXISTS teams (
                    team_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    FOREIGN KEY(created_by) REFERENCES users(user_id)
                );
                CREATE TABLE IF NOT EXISTS memberships (
                    team_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    invited_by TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(team_id, user_id),
                    FOREIGN KEY(team_id) REFERENCES teams(team_id),
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    repo_path TEXT NOT NULL,
                    template TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    default_branch TEXT NOT NULL DEFAULT 'main',
                    privacy_mode TEXT NOT NULL DEFAULT 'local',
                    UNIQUE(team_id, slug),
                    FOREIGN KEY(team_id) REFERENCES teams(team_id),
                    FOREIGN KEY(created_by) REFERENCES users(user_id)
                );
                CREATE TABLE IF NOT EXISTS invitations (
                    invitation_id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    invited_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING'
                );
                CREATE TABLE IF NOT EXISTS activity (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id TEXT NOT NULL DEFAULT '',
                    project_id TEXT NOT NULL DEFAULT '',
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_projects_team ON projects(team_id);
                CREATE INDEX IF NOT EXISTS idx_activity_project ON activity(project_id, event_id DESC);
                """
            )

    def create_user(self, email: str, display_name: str) -> UserRecord:
        normalized = email.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise WorkspaceError("A valid email address is required.")
        name = " ".join(display_name.strip().split())
        if len(name) < 2:
            raise WorkspaceError("A display name is required.")
        with self._connection() as connection:
            existing = connection.execute("SELECT * FROM users WHERE email = ?", (normalized,)).fetchone()
            if existing:
                return UserRecord(**dict(existing))
            record = UserRecord(_id("usr", normalized), normalized, name, _now())
            connection.execute(
                "INSERT INTO users(user_id, email, display_name, created_at, status) VALUES(?, ?, ?, ?, ?)",
                (record.user_id, record.email, record.display_name, record.created_at, record.status),
            )
            return record

    def get_user(self, user_id: str) -> UserRecord:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            raise WorkspaceError(f"User not found: {user_id}")
        return UserRecord(**dict(row))

    def create_team(self, name: str, owner_user_id: str, slug: str | None = None) -> TeamRecord:
        self.get_user(owner_user_id)
        normalized_slug = _slug(slug or name)
        record = TeamRecord(_id("team", normalized_slug), " ".join(name.strip().split()), normalized_slug, _now(), owner_user_id)
        with self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO teams(team_id, name, slug, created_at, created_by, status) VALUES(?, ?, ?, ?, ?, ?)",
                    (record.team_id, record.name, record.slug, record.created_at, record.created_by, record.status),
                )
            except sqlite3.IntegrityError as exc:
                raise WorkspaceError(f"Team slug already exists: {normalized_slug}") from exc
            connection.execute(
                "INSERT INTO memberships(team_id, user_id, role, created_at, invited_by) VALUES(?, ?, ?, ?, ?)",
                (record.team_id, owner_user_id, WorkspaceRole.OWNER.value, _now(), owner_user_id),
            )
        self.record_activity(record.team_id, "", owner_user_id, "TEAM_CREATED", f"Created team {record.name}.")
        return record

    def get_team(self, team_id: str) -> TeamRecord:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM teams WHERE team_id = ?", (team_id,)).fetchone()
        if not row:
            raise WorkspaceError(f"Team not found: {team_id}")
        return TeamRecord(**dict(row))

    def member_role(self, team_id: str, user_id: str) -> WorkspaceRole | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT role FROM memberships WHERE team_id = ? AND user_id = ?", (team_id, user_id)
            ).fetchone()
        return WorkspaceRole(row["role"]) if row else None

    def require_team_role(self, team_id: str, user_id: str, minimum: WorkspaceRole) -> WorkspaceRole:
        role = self.member_role(team_id, user_id)
        if role is None or _ROLE_RANK[role.value] < _ROLE_RANK[minimum.value]:
            raise WorkspaceError(f"{minimum.value} access is required for team {team_id}.")
        return role

    def add_member(self, team_id: str, user_id: str, role: WorkspaceRole | str, actor_user_id: str) -> MembershipRecord:
        self.get_team(team_id)
        self.get_user(user_id)
        self.require_team_role(team_id, actor_user_id, WorkspaceRole.ADMIN)
        selected = WorkspaceRole(role)
        if selected == WorkspaceRole.OWNER and self.member_role(team_id, actor_user_id) != WorkspaceRole.OWNER:
            raise WorkspaceError("Only an owner may add another owner.")
        record = MembershipRecord(team_id, user_id, selected, _now(), actor_user_id)
        with self._connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO memberships(team_id, user_id, role, created_at, invited_by) VALUES(?, ?, ?, ?, ?)",
                (team_id, user_id, selected.value, record.created_at, actor_user_id),
            )
        self.record_activity(team_id, "", actor_user_id, "MEMBER_ADDED", f"Added {user_id} as {selected.value}.")
        return record

    def list_members(self, team_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT memberships.team_id, memberships.user_id, memberships.role, memberships.created_at,
                       memberships.invited_by, users.email, users.display_name
                FROM memberships JOIN users ON users.user_id = memberships.user_id
                WHERE memberships.team_id = ? ORDER BY memberships.role DESC, users.display_name
                """,
                (team_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_project(
        self,
        team_id: str,
        name: str,
        repo_path: Path,
        created_by: str,
        template: str = "fullstack-lite",
        slug: str | None = None,
        privacy_mode: str = "local",
    ) -> ProjectRecord:
        self.require_team_role(team_id, created_by, WorkspaceRole.DEVELOPER)
        resolved = repo_path.expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise WorkspaceError(f"Project repository does not exist: {resolved}")
        if privacy_mode not in {"local", "private", "standard"}:
            raise WorkspaceError(f"Unsupported privacy mode: {privacy_mode}")
        normalized_slug = _slug(slug or name)
        record = ProjectRecord(
            _id("proj", f"{team_id}:{normalized_slug}"),
            team_id,
            " ".join(name.strip().split()),
            normalized_slug,
            str(resolved),
            template,
            _now(),
            created_by,
            privacy_mode=privacy_mode,
        )
        with self._connection() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO projects(project_id, team_id, name, slug, repo_path, template, created_at, created_by,
                                         status, default_branch, privacy_mode)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.project_id,
                        record.team_id,
                        record.name,
                        record.slug,
                        record.repo_path,
                        record.template,
                        record.created_at,
                        record.created_by,
                        record.status,
                        record.default_branch,
                        record.privacy_mode,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise WorkspaceError(f"Project slug already exists for this team: {normalized_slug}") from exc
        self.record_activity(team_id, record.project_id, created_by, "PROJECT_CREATED", f"Created project {record.name}.")
        return record

    def get_project(self, project_id: str) -> ProjectRecord:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        if not row:
            raise WorkspaceError(f"Project not found: {project_id}")
        return ProjectRecord(**dict(row))

    def require_project_role(self, project_id: str, user_id: str, minimum: WorkspaceRole) -> ProjectRecord:
        project = self.get_project(project_id)
        self.require_team_role(project.team_id, user_id, minimum)
        return project

    def list_projects(self, team_id: str | None = None) -> list[dict[str, Any]]:
        with self._connection() as connection:
            if team_id:
                rows = connection.execute(
                    "SELECT * FROM projects WHERE team_id = ? ORDER BY created_at DESC", (team_id,)
                ).fetchall()
            else:
                rows = connection.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def set_project_status(self, project_id: str, status: str, actor_user_id: str) -> ProjectRecord:
        project = self.require_project_role(project_id, actor_user_id, WorkspaceRole.ADMIN)
        selected = status.strip().upper()
        if selected not in {"ACTIVE", "PAUSED", "ARCHIVED"}:
            raise WorkspaceError(f"Unsupported project status: {status}")
        with self._connection() as connection:
            connection.execute("UPDATE projects SET status = ? WHERE project_id = ?", (selected, project_id))
        self.record_activity(project.team_id, project_id, actor_user_id, "PROJECT_STATUS", f"Project set to {selected}.")
        return self.get_project(project_id)

    def record_activity(
        self,
        team_id: str,
        project_id: str,
        actor: str,
        action: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO activity(team_id, project_id, actor, action, summary, metadata_json, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (team_id, project_id, actor, action, summary, json.dumps(metadata or {}, sort_keys=True), _now()),
            )

    def activity(self, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connection() as connection:
            if project_id:
                rows = connection.execute(
                    "SELECT * FROM activity WHERE project_id = ? ORDER BY event_id DESC LIMIT ?",
                    (project_id, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute("SELECT * FROM activity ORDER BY event_id DESC LIMIT ?", (safe_limit,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json"))
            except json.JSONDecodeError:
                item["metadata"] = {}
            result.append(item)
        return result

    def snapshot(self) -> dict[str, Any]:
        with self._connection() as connection:
            counts = {
                "users": connection.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "teams": connection.execute("SELECT COUNT(*) FROM teams").fetchone()[0],
                "memberships": connection.execute("SELECT COUNT(*) FROM memberships").fetchone()[0],
                "projects": connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
            }
            teams = [dict(row) for row in connection.execute("SELECT * FROM teams ORDER BY created_at DESC LIMIT 50")]
        return {
            "counts": counts,
            "teams": teams,
            "projects": self.list_projects(),
            "activity": self.activity(limit=50),
        }
