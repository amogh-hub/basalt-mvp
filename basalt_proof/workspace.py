from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

EXCLUDE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", "dist", "build", ".next", ".basalt", ".basalt-deps"}
EXCLUDE_FILES = {"proof-report.json", "proof-report.md", "basalt-dashboard.html", "basalt-patch-plan.md", "knowledge-graph.json"}


def _ignore(directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        path = Path(directory) / name
        if name in EXCLUDE_FILES:
            ignored.add(name)
        elif path.is_dir() and name in EXCLUDE_DIRS:
            ignored.add(name)
    return ignored


class Workspace:
    def __init__(self, source_repo: Path, keep: bool = False):
        self.source_repo = source_repo.resolve()
        self.keep = keep
        self.temp_dir = Path(tempfile.mkdtemp(prefix="basalt-mvp-"))
        self.path = self.temp_dir / self.source_repo.name

    def __enter__(self) -> "Workspace":
        shutil.copytree(self.source_repo, self.path, ignore=_ignore)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.keep:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
