from __future__ import annotations

import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_PREVIEW_BYTES = 10_000_000
ALLOWED_SUFFIXES = {
    ".html", ".htm", ".css", ".js", ".mjs", ".json", ".svg", ".png", ".jpg", ".jpeg",
    ".gif", ".webp", ".ico", ".txt", ".woff", ".woff2", ".ttf", ".map",
}
PROTECTED_PARTS = {".git", ".basalt", ".venv", "venv", "node_modules", "__pycache__"}


class PreviewError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StaticPreviewManager:
    """Same-origin static preview with no arbitrary command execution."""

    def __init__(self, repo: Path, state_root: Path) -> None:
        self.repo = repo.resolve()
        self.state_root = state_root.resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_root / "preview-state.json"

    def _candidate_root(self) -> Path | None:
        candidates = (
            self.repo,
            self.repo / "dist",
            self.repo / "build",
            self.repo / "public",
            self.repo / "frontend",
            self.repo / "web",
            self.repo / "app",
        )
        for candidate in candidates:
            if candidate.is_dir() and (candidate / "index.html").is_file():
                return candidate.resolve()
        return None

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def snapshot(self) -> dict[str, Any]:
        root = self._candidate_root()
        state = self._load()
        enabled = bool(state.get("enabled")) and root is not None
        return {
            "available": root is not None,
            "status": "RUNNING" if enabled else "STOPPED",
            "mode": "STATIC_SAME_ORIGIN",
            "root": root.relative_to(self.repo).as_posix() if root and root != self.repo else ("" if root else ""),
            "url": "/preview/" if enabled else "",
            "started_at": str(state.get("started_at", "")) if enabled else "",
            "started_by": str(state.get("started_by", "")) if enabled else "",
            "reason": "Static index.html detected." if root else "No supported static index.html was detected.",
            "security": {
                "arbitrary_shell": False,
                "server_side_execution": False,
                "same_origin": True,
                "protected_paths": True,
            },
        }

    def start(self, actor: str) -> dict[str, Any]:
        root = self._candidate_root()
        if root is None:
            raise PreviewError("No supported static index.html was detected.")
        state = {
            "enabled": True,
            "root": root.relative_to(self.repo).as_posix() if root != self.repo else "",
            "started_at": _now(),
            "started_by": actor.strip()[:200] or "local-user",
        }
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return self.snapshot()

    def stop(self, actor: str) -> dict[str, Any]:
        prior = self._load()
        state = {
            "enabled": False,
            "root": prior.get("root", ""),
            "stopped_at": _now(),
            "stopped_by": actor.strip()[:200] or "local-user",
        }
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return self.snapshot()

    def resolve(self, requested: str) -> tuple[Path, str]:
        snapshot = self.snapshot()
        if snapshot["status"] != "RUNNING":
            raise PreviewError("Preview is stopped.")
        root_value = str(snapshot.get("root", ""))
        root = (self.repo / root_value).resolve() if root_value else self.repo
        cleaned = requested.strip().lstrip("/") or "index.html"
        candidate = (root / cleaned).resolve()
        if candidate != root and root not in candidate.parents:
            raise PreviewError("Preview path escapes the preview root.")
        relative = candidate.relative_to(root)
        if any(part in PROTECTED_PARTS or part.startswith(".") for part in relative.parts):
            raise PreviewError("Preview path is protected.")
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.is_file() or candidate.is_symlink():
            raise FileNotFoundError(str(candidate))
        if candidate.suffix.lower() not in ALLOWED_SUFFIXES:
            raise PreviewError("Preview file type is not allowed.")
        if candidate.stat().st_size > MAX_PREVIEW_BYTES:
            raise PreviewError("Preview asset is too large.")
        return candidate, mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
