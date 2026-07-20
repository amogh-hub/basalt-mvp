from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class WorkspaceRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxProfile:
    name: str
    network: str = "deny"
    env_allowlist: tuple[str, ...] = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL")
    exclude: tuple[str, ...] = (".git", ".basalt", ".venv", "venv", "node_modules", "__pycache__")
    max_files: int = 50_000
    max_bytes: int = 512 * 1024 * 1024
    read_only_source: bool = True


PRIVATE_BETA_PROFILE = SandboxProfile(name="private-beta")


def _hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()


class WorkspaceManager:
    """Creates bounded per-job workspaces without mutating the registered source repository."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _job_root(self, job_id: str) -> Path:
        if not job_id or any(token in job_id for token in ("/", "\\", "..")):
            raise WorkspaceRuntimeError("Unsafe job id.")
        candidate = (self.root / job_id).resolve()
        if self.root not in candidate.parents:
            raise WorkspaceRuntimeError("Workspace escaped the configured root.")
        return candidate

    @staticmethod
    def safe_environment(profile: SandboxProfile = PRIVATE_BETA_PROFILE, source: dict[str, str] | None = None) -> dict[str, str]:
        environ = source if source is not None else os.environ
        safe = {key: environ[key] for key in profile.env_allowlist if key in environ}
        safe["BASALT_SANDBOX_PROFILE"] = profile.name
        safe["BASALT_NETWORK_POLICY"] = profile.network
        return safe

    def prepare(self, job_id: str, source_repo: Path, profile: SandboxProfile = PRIVATE_BETA_PROFILE) -> dict[str, Any]:
        source = source_repo.expanduser().resolve()
        if not source.exists() or not source.is_dir():
            raise WorkspaceRuntimeError(f"Source repository does not exist: {source}")
        destination = self._job_root(job_id)
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        workspace = destination / "workspace"
        excluded = set(profile.exclude)
        file_count = 0
        total_bytes = 0
        source_hash = hashlib.sha256()

        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if any(part in excluded for part in relative.parts):
                continue
            if path.is_symlink():
                raise WorkspaceRuntimeError(f"Symlinks are not allowed in private-beta workspaces: {relative}")
            target = workspace / relative
            if path.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not path.is_file():
                continue
            file_count += 1
            total_bytes += path.stat().st_size
            if file_count > profile.max_files:
                raise WorkspaceRuntimeError(f"Workspace exceeds file limit: {profile.max_files}")
            if total_bytes > profile.max_bytes:
                raise WorkspaceRuntimeError(f"Workspace exceeds byte limit: {profile.max_bytes}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            source_hash.update(relative.as_posix().encode("utf-8"))
            source_hash.update(path.read_bytes())

        manifest = {
            "job_id": job_id,
            "profile": asdict(profile),
            "source_repo": str(source),
            "workspace": str(workspace),
            "source_hash": source_hash.hexdigest(),
            "workspace_hash": _hash_tree(workspace),
            "file_count": file_count,
            "total_bytes": total_bytes,
            "environment_keys": sorted(self.safe_environment(profile)),
        }
        import json

        (destination / "workspace-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def verify_source_unchanged(self, manifest: dict[str, Any]) -> bool:
        source = Path(manifest["source_repo"])
        if not source.exists():
            return False
        excluded = set(manifest["profile"].get("exclude", []))
        digest = hashlib.sha256()
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if any(part in excluded for part in relative.parts) or not path.is_file() or path.is_symlink():
                continue
            digest.update(relative.as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
        return digest.hexdigest() == manifest["source_hash"]

    def cleanup(self, job_id: str) -> None:
        destination = self._job_root(job_id)
        if destination.exists():
            shutil.rmtree(destination)

    def snapshot(self) -> dict[str, Any]:
        workspaces = []
        for path in sorted(self.root.iterdir()) if self.root.exists() else []:
            manifest = path / "workspace-manifest.json"
            if manifest.exists():
                import json

                try:
                    workspaces.append(json.loads(manifest.read_text(encoding="utf-8")))
                except json.JSONDecodeError:
                    continue
        return {"root": str(self.root), "active": len(workspaces), "workspaces": workspaces}
