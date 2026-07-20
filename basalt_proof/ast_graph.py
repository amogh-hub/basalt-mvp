from __future__ import annotations

from pathlib import Path

from .knowledge_graph import build_project_graph
from .models import KnowledgeGraph


def build_knowledge_graph(
    repo_path: Path,
    excluded_paths: list[str] | None = None,
) -> KnowledgeGraph:
    """Compatibility wrapper for the Phase 1 API.

    Phase 2 moves graph construction into the persistent Project Knowledge Graph
    service while keeping this function available for existing integrations.
    """
    return build_project_graph(repo_path, store_path=None, excluded_paths=excluded_paths)
