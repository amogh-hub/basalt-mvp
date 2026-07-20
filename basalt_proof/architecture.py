from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import KnowledgeGraph


_LAYER_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Interface", ("webui", "frontend", "templates", "static", "ui", "views")),
    ("Application", ("service", "command", "cli", "runtime", "factory", "controller", "handler")),
    ("Domain", ("model", "policy", "proof", "planner", "context", "knowledge", "mutation", "security")),
    ("Infrastructure", ("registry", "queue", "deployment", "provider", "state", "runner", "sandbox", "storage")),
    ("Tests", ("test", "tests", "spec")),
)

_DB_PATTERNS = (
    re.compile(r"sqlite3\.connect\((?P<value>[^\n]+)"),
    re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<value>[A-Za-z_][A-Za-z0-9_]*)", re.I),
)

_API_PATH = re.compile(r"(?:path\s*==|path\.startswith\()\s*[\"'](?P<path>/[^\"']+)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _layer_for(path: str) -> str:
    lowered = path.lower()
    parts = {part.lower() for part in Path(path).parts}
    for layer, tokens in _LAYER_RULES:
        if any(token in parts or token in lowered for token in tokens):
            return layer
    return "Core"


def _module_name(path: str) -> str:
    item = Path(path)
    if len(item.parts) <= 1:
        return item.stem
    return "/".join(item.parts[:2])


def _discover_api_paths(repo: Path) -> list[dict[str, str]]:
    routes: set[tuple[str, str]] = set()
    for path in sorted(repo.rglob("*.py")):
        if any(part in {".git", ".basalt", ".venv", "venv", "__pycache__"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(repo).as_posix()
        for match in _API_PATH.finditer(text):
            route = match.group("path")
            before = text[:match.start()]
            get_position = before.rfind("def do_GET")
            post_position = before.rfind("def do_POST")
            method = "GET" if get_position > post_position else ("POST" if post_position > get_position else "HTTP")
            routes.add((method, route))
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not decorator.args:
                    continue
                func = decorator.func
                attr = func.attr.lower() if isinstance(func, ast.Attribute) else ""
                if attr not in {"get", "post", "put", "patch", "delete", "route", "websocket"}:
                    continue
                value = decorator.args[0]
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value.startswith("/"):
                    routes.add((attr.upper(), value.value))
    return [{"method": method, "path": route} for method, route in sorted(routes)]


def _discover_databases(repo: Path, graph: KnowledgeGraph) -> dict[str, Any]:
    tables: set[str] = set()
    sqlite_references: set[str] = set()
    files: set[str] = set()
    for path in sorted(repo.rglob("*.py")):
        if any(part in {".git", ".basalt", ".venv", "venv", "__pycache__"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(repo).as_posix()
        for match in _DB_PATTERNS[0].finditer(text):
            sqlite_references.add(match.group("value").strip()[:180])
            files.add(rel)
        for match in _DB_PATTERNS[1].finditer(text):
            tables.add(match.group("value"))
            files.add(rel)
    return {
        "engine": "SQLite/local" if sqlite_references or tables else "Not detected",
        "tables": sorted(tables),
        "schema_signals": sorted(set(graph.schemas)),
        "files": sorted(files),
        "connection_references": sorted(sqlite_references),
    }


def architecture_snapshot(repo: Path, graph: KnowledgeGraph) -> dict[str, Any]:
    layers: dict[str, list[str]] = defaultdict(list)
    modules: Counter[str] = Counter()
    for source in sorted(graph.source_files):
        layers[_layer_for(source)].append(source)
        modules[_module_name(source)] += 1

    dependency_edges: Counter[tuple[str, str]] = Counter()
    for edge in graph.edges:
        if not edge.source_file or not edge.target_file or edge.source_file == edge.target_file:
            continue
        source = _module_name(edge.source_file)
        target = _module_name(edge.target_file)
        if source != target:
            dependency_edges[(source, target)] += 1

    discovered_api = _discover_api_paths(repo)
    database = _discover_databases(repo, graph)

    return {
        "generated_at": _now(),
        "repository": str(repo.resolve()),
        "state_hash": graph.state_hash,
        "fresh": bool(graph.fresh),
        "summary": {
            "source_files": len(graph.source_files),
            "modules": len(modules),
            "routes": len({item["method"] + " " + item["path"] for item in discovered_api}) + len(graph.routes),
            "schemas": len(set(database.get("tables", []))) + len(set(database.get("schema_signals", []))),
            "dependency_edges": len(dependency_edges),
        },
        "layers": [
            {"name": name, "count": len(files), "files": files[:80]}
            for name, files in sorted(layers.items(), key=lambda item: (-len(item[1]), item[0]))
        ],
        "modules": [
            {"name": name, "files": count}
            for name, count in modules.most_common(80)
        ],
        "dependencies": [
            {"source": source, "target": target, "signals": count}
            for (source, target), count in dependency_edges.most_common(120)
        ],
        "api": {
            "discovered": discovered_api,
            "graph_routes": list(graph.routes),
        },
        "database": database,
        "truth": {
            "mode": "STATIC_REPOSITORY_ANALYSIS",
            "claim": "Architecture is derived from repository source and the AST-backed knowledge graph; it is not a manually drawn or model-invented diagram.",
        },
    }
