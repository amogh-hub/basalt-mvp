from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .knowledge_graph import analyze_impact, build_project_graph, check_graph_freshness
from .models import ContextPack, KnowledgeGraph

TASK_KEYWORDS = {
    "bug_fix": {"bug", "fix", "error", "failure", "broken", "exception", "regression"},
    "feature": {"feature", "add", "implement", "create", "build", "support"},
    "security": {"security", "auth", "permission", "secret", "vulnerability", "token"},
    "testing": {"test", "coverage", "mutation", "assert", "verify", "proof"},
    "migration": {"migration", "schema", "database", "table", "column", "backfill"},
    "ui": {"ui", "frontend", "component", "page", "screen", "layout", "style"},
    "documentation": {"docs", "documentation", "readme", "guide", "comment"},
    "review": {"review", "audit", "inspect", "analyze", "quality"},
}
ROLE_HINTS = {
    "testingagent": {"test", "tests", "spec", "proof", "mutation"},
    "securityagent": {"auth", "security", "permission", "secret", "policy", "token"},
    "frontendagent": {"frontend", "component", "page", "ui", "tsx", "jsx", "react"},
    "backendagent": {"backend", "api", "service", "route", "handler", "python"},
    "databaseagent": {"database", "schema", "migration", "sql", "model", "table"},
    "devopsagent": {"deploy", "ci", "workflow", "docker", "config", "environment"},
    "documentationagent": {"docs", "readme", "guide", "documentation"},
    "codereviewagent": {"review", "quality", "complexity", "security", "test"},
}
DEFAULT_CONSTRAINTS = [
    "Do not deploy without a VERIFIED proof verdict.",
    "Do not expose secrets in prompts, generated code, or artifacts.",
    "Do not perform destructive migrations without expand-and-contract planning and human approval.",
    "Do not silently change auth, payment, permission, or API contracts.",
    "Use AST-anchored graph truth; semantic summaries must not override deterministic code structure.",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> set[str]:
    return {
        item
        for item in re.split(r"[^A-Za-z0-9_]+", text.lower())
        if len(item) >= 2
    }


def classify_task(task: str) -> str:
    words = _tokens(task)
    scored = [
        (len(words & keywords), task_type)
        for task_type, keywords in TASK_KEYWORDS.items()
    ]
    score, task_type = max(scored, default=(0, "general"))
    return task_type if score else "general"


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _read_snippet(path: Path, line_ranges: list[tuple[int, int]], max_chars: int) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    collected: list[str] = []
    seen: set[int] = set()
    for start, end in line_ranges:
        for index in range(max(1, start), min(len(lines), end) + 1):
            if index in seen:
                continue
            seen.add(index)
            collected.append(f"{index:>4}: {lines[index - 1]}")
            if sum(len(item) + 1 for item in collected) >= max_chars:
                return "\n".join(collected)[:max_chars]
    if not collected:
        return "\n".join(f"{i + 1:>4}: {line}" for i, line in enumerate(lines[:40]))[:max_chars]
    return "\n".join(collected)[:max_chars]


def _entity_text(graph: KnowledgeGraph) -> dict[str, str]:
    result: dict[str, str] = {}
    for file in graph.files:
        result[f"file:{file.path}"] = f"{file.path} {file.language}"
    for symbol in graph.symbols:
        result[symbol.id] = " ".join(
            [symbol.name, symbol.qualified_name, symbol.signature, symbol.kind, symbol.file, symbol.docstring]
        )
    for feature in graph.features:
        result[f"feature:{feature.id}"] = " ".join(
            [feature.id, feature.name, feature.description, *feature.keywords, *feature.files]
        )
    return result


def _seed_scores(
    graph: KnowledgeGraph,
    task: str,
    role: str,
    targets: list[str],
) -> tuple[dict[str, float], dict[str, set[str]]]:
    task_words = _tokens(task)
    role_words = ROLE_HINTS.get(role.lower().replace(" ", ""), set())
    entity_text = _entity_text(graph)
    scores: dict[str, float] = {}
    reasons: dict[str, set[str]] = {}

    def add(node: str, score: float, reason: str) -> None:
        scores[node] = scores.get(node, 0.0) + score
        reasons.setdefault(node, set()).add(reason)

    for target in targets:
        lowered = target.lower()
        for node, text in entity_text.items():
            if lowered == node.lower() or lowered in text.lower():
                add(node, 100.0, f"explicit target: {target}")

    for node, text in entity_text.items():
        words = _tokens(text)
        overlap = task_words & words
        if overlap:
            add(node, 8.0 * len(overlap), "task keyword match: " + ", ".join(sorted(overlap)))
        role_overlap = role_words & words
        if role_overlap:
            add(node, 3.0 * len(role_overlap), "agent-role relevance: " + ", ".join(sorted(role_overlap)))
        if node.startswith("file:") and node[5:] in graph.test_files and role.lower().replace(" ", "") == "testingagent":
            add(node, 12.0, "TestingAgent prioritizes test files")

    if not scores:
        for file in graph.files[:8]:
            add(f"file:{file.path}", 1.0, "fallback project overview")
    return scores, reasons


def _expand_scores(
    graph: KnowledgeGraph,
    scores: dict[str, float],
    reasons: dict[str, set[str]],
    depth: int = 2,
) -> None:
    adjacency: dict[str, list[tuple[str, str, float]]] = {}
    edge_weights = {
        "contains": 0.75,
        "imports": 0.72,
        "calls": 0.65,
        "verifies": 0.9,
        "verifies_feature": 0.85,
        "implemented_by": 0.85,
        "handled_by": 0.9,
        "defines_route": 0.8,
        "inherits": 0.7,
        "references_table": 0.8,
    }
    for edge in graph.edges:
        weight = edge_weights.get(edge.edge_type, 0.55) * max(0.25, edge.confidence)
        adjacency.setdefault(edge.source, []).append((edge.target, edge.edge_type, weight))
        adjacency.setdefault(edge.target, []).append((edge.source, "reverse_" + edge.edge_type, weight * 0.9))
    frontier = dict(scores)
    for _ in range(depth):
        next_frontier: dict[str, float] = {}
        for node, score in frontier.items():
            for neighbor, edge_type, weight in adjacency.get(node, []):
                propagated = score * weight * 0.45
                if propagated < 0.5:
                    continue
                if propagated > scores.get(neighbor, 0.0):
                    scores[neighbor] = scores.get(neighbor, 0.0) + propagated
                    reasons.setdefault(neighbor, set()).add(f"graph relation: {edge_type} from {node}")
                    next_frontier[neighbor] = max(next_frontier.get(neighbor, 0.0), propagated)
        frontier = next_frontier
        if not frontier:
            break


def compile_context_pack(
    repo_path: Path,
    graph: KnowledgeGraph,
    task: str,
    agent_role: str,
    targets: list[str] | None = None,
    token_budget: int = 12000,
) -> ContextPack:
    targets = targets or []
    task_type = classify_task(task)
    scores, reasons = _seed_scores(graph, task, agent_role, targets)
    _expand_scores(graph, scores, reasons)

    file_scores: dict[str, float] = {}
    symbol_scores: dict[str, float] = {}
    for node, score in scores.items():
        if node.startswith("file:"):
            file_scores[node[5:]] = max(file_scores.get(node[5:], 0.0), score)
        elif node.startswith("symbol:"):
            symbol_scores[node] = score
            symbol = next((item for item in graph.symbols if item.id == node), None)
            if symbol:
                file_scores[symbol.file] = max(file_scores.get(symbol.file, 0.0), score * 0.95)
        elif node.startswith("feature:"):
            feature = next((item for item in graph.features if item.id == node[8:]), None)
            if feature:
                for file_path in feature.files:
                    file_scores[file_path] = max(file_scores.get(file_path, 0.0), score * 0.85)
                for test_path in feature.tests:
                    file_scores[test_path] = max(file_scores.get(test_path, 0.0), score * 0.9)

    selected_files: list[dict[str, Any]] = []
    selected_symbols: list[dict[str, Any]] = []
    estimated_tokens = 0
    per_file_cap = max(600, min(6000, token_budget // 3))

    for file_path, score in sorted(file_scores.items(), key=lambda item: (-item[1], item[0])):
        if estimated_tokens >= token_budget:
            break
        symbols = [item for item in graph.symbols if item.file == file_path]
        ranges = [(max(1, item.line - 3), max(item.line + 8, item.end_line + 2)) for item in symbols[:10]]
        remaining_chars = max(0, (token_budget - estimated_tokens) * 4)
        snippet = _read_snippet(repo_path / file_path, ranges, min(per_file_cap * 4, remaining_chars))
        snippet_tokens = _estimate_tokens(snippet)
        if not snippet or estimated_tokens + snippet_tokens > token_budget:
            continue
        file_node = f"file:{file_path}"
        selected_files.append(
            {
                "path": file_path,
                "score": round(score, 3),
                "reasons": sorted(reasons.get(file_node, set())),
                "snippet": snippet,
                "estimated_tokens": snippet_tokens,
                "hash": next((item.hash for item in graph.files if item.path == file_path), ""),
            }
        )
        estimated_tokens += snippet_tokens
        for symbol in symbols:
            if symbol.id in symbol_scores or score >= 10:
                selected_symbols.append(
                    {
                        "id": symbol.id,
                        "file": symbol.file,
                        "name": symbol.name,
                        "qualified_name": symbol.qualified_name,
                        "kind": symbol.kind,
                        "line": symbol.line,
                        "signature": symbol.signature,
                    }
                )

    selected_paths = {item["path"] for item in selected_files}
    tests = sorted(
        {
            mapping.test_file
            for mapping in graph.test_mappings
            if mapping.source_file in selected_paths or mapping.test_file in selected_paths
        }
        | (selected_paths & set(graph.test_files))
    )
    features = sorted(
        feature.name
        for feature in graph.features
        if selected_paths & set(feature.files + feature.tests)
    )
    routes = sorted(
        symbol.name
        for symbol in graph.symbols
        if symbol.kind == "api_route" and symbol.file in selected_paths
    )
    schemas = sorted(
        symbol.name
        for symbol in graph.symbols
        if symbol.kind in {"database_table", "database_view"} and symbol.file in selected_paths
    )
    dependencies = [
        asdict(edge)
        for edge in graph.edges
        if (edge.source_file in selected_paths or edge.target_file in selected_paths)
        and edge.edge_type in {"imports", "calls", "verifies", "handled_by", "references_table"}
    ][:100]
    selection_reasons = [
        {"entity": entity, "score": round(scores[entity], 3), "reasons": sorted(reasons.get(entity, set()))}
        for entity in sorted(scores, key=lambda item: (-scores[item], item))[:100]
    ]
    total_candidates = max(1, len(graph.files))
    precision = round(min(1.0, len(selected_files) / total_candidates), 4)
    identity = hashlib.sha256(
        f"{graph.state_hash}|{task}|{agent_role}|{','.join(targets)}|{token_budget}".encode("utf-8")
    ).hexdigest()[:16]
    return ContextPack(
        context_pack_id=f"ctx_{identity}",
        project_state_hash=graph.state_hash,
        created_at=_now(),
        task=task,
        task_type=task_type,
        agent_role=agent_role,
        token_budget=token_budget,
        estimated_tokens=estimated_tokens,
        target_entities=targets,
        files=selected_files,
        symbols=selected_symbols,
        tests=tests,
        features=features,
        routes=routes,
        schemas=schemas,
        dependencies=dependencies,
        constraints=list(DEFAULT_CONSTRAINTS),
        freshness={
            "fresh": graph.fresh,
            "state_hash": graph.state_hash,
            "parser_version": graph.parser_version,
            "built_at": graph.built_at,
        },
        selection_reasons=selection_reasons,
        context_precision_score=precision,
    )


def ensure_fresh_graph(
    repo_path: Path,
    store_path: Path,
    excluded_paths: list[str] | None = None,
    refresh: bool = True,
) -> KnowledgeGraph:
    freshness = check_graph_freshness(repo_path, store_path, excluded_paths)
    if freshness.fresh:
        return build_project_graph(repo_path, store_path, excluded_paths)
    if not refresh:
        raise RuntimeError(
            "Project Knowledge Graph is stale. Run `basalt graph build <repo>` or allow automatic refresh."
        )
    return build_project_graph(repo_path, store_path, excluded_paths, force=True)


def write_context_pack(pack: ContextPack, output_dir: Path) -> list[Path]:
    pack_dir = output_dir / "context-packs"
    pack_dir.mkdir(parents=True, exist_ok=True)
    json_path = pack_dir / f"{pack.context_pack_id}.json"
    md_path = pack_dir / f"{pack.context_pack_id}.md"
    latest_json = output_dir / "context-pack.json"
    latest_md = output_dir / "context-pack.md"
    payload = json.dumps(asdict(pack), indent=2, sort_keys=True)
    json_path.write_text(payload, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    lines = [
        "# Basalt Context Pack",
        "",
        f"- ID: `{pack.context_pack_id}`",
        f"- Project state: `{pack.project_state_hash}`",
        f"- Task type: `{pack.task_type}`",
        f"- Agent role: `{pack.agent_role}`",
        f"- Token budget: `{pack.token_budget}`",
        f"- Estimated tokens: `{pack.estimated_tokens}`",
        f"- Context precision score: `{pack.context_precision_score:.4f}`",
        "",
        "## Task",
        "",
        pack.task,
        "",
        "## Selected Files",
        "",
    ]
    for item in pack.files:
        lines.append(f"### `{item['path']}` — score {item['score']}")
        if item.get("reasons"):
            lines.append("Reasons: " + "; ".join(item["reasons"]))
        lines.extend(["", "```text", item.get("snippet", ""), "```", ""])
    lines.extend(["## Tests", ""])
    lines.extend(f"- `{item}`" for item in pack.tests) or lines.append("- None")
    lines.extend(["", "## Features", ""])
    lines.extend(f"- {item}" for item in pack.features) or lines.append("- None")
    lines.extend(["", "## Constraints", ""])
    lines.extend(f"- {item}" for item in pack.constraints)
    markdown = "\n".join(lines) + "\n"
    md_path.write_text(markdown, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    return [json_path, md_path, latest_json, latest_md]


def compile_context_for_repo(
    repo_path: Path,
    output_dir: Path,
    task: str,
    agent_role: str,
    targets: list[str] | None = None,
    token_budget: int = 12000,
    excluded_paths: list[str] | None = None,
    refresh: bool = True,
) -> tuple[ContextPack, list[Path]]:
    store_path = output_dir / "knowledge-graph.sqlite3"
    graph = ensure_fresh_graph(repo_path, store_path, excluded_paths, refresh=refresh)
    pack = compile_context_pack(repo_path, graph, task, agent_role, targets, token_budget)
    artifacts = write_context_pack(pack, output_dir)
    return pack, artifacts
