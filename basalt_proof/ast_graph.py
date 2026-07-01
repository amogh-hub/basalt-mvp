from __future__ import annotations

import ast
import re
from pathlib import Path

from .models import GraphEdge, GraphSymbol, KnowledgeGraph

SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}
TEST_PATTERNS = ("test_", "_test", ".test.", ".spec.")
SKIP_PARTS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".basalt"}


def _skip(path: Path, repo_path: Path) -> bool:
    parts = set(path.relative_to(repo_path).parts)
    return bool(parts & SKIP_PARTS)


def _signature_from_args(args: ast.arguments) -> str:
    names = [arg.arg for arg in args.args]
    return "(" + ", ".join(names) + ")"


def _parse_python(path: Path, repo_path: Path) -> tuple[list[GraphSymbol], list[GraphEdge]]:
    rel = str(path.relative_to(repo_path))
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return [], []
    symbols: list[GraphSymbol] = []
    edges: list[GraphEdge] = []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            symbols.append(GraphSymbol(rel, node.name, "function", node.lineno, node.name + _signature_from_args(node.args)))
        elif isinstance(node, ast.AsyncFunctionDef):
            symbols.append(GraphSymbol(rel, node.name, "async_function", node.lineno, node.name + _signature_from_args(node.args)))
        elif isinstance(node, ast.ClassDef):
            symbols.append(GraphSymbol(rel, node.name, "class", node.lineno, node.name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    for target in imports:
        edges.append(GraphEdge(rel, target, "imports"))
    return symbols, edges


JS_FUNC = re.compile(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)")
JS_CONST_FN = re.compile(r"(?:export\s+)?(?:const|let)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>")
JS_IMPORT = re.compile(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]")


def _parse_js(path: Path, repo_path: Path) -> tuple[list[GraphSymbol], list[GraphEdge]]:
    rel = str(path.relative_to(repo_path))
    text = path.read_text(encoding="utf-8", errors="ignore")
    symbols: list[GraphSymbol] = []
    edges: list[GraphEdge] = []
    for pattern, kind in ((JS_FUNC, "function"), (JS_CONST_FN, "function")):
        for m in pattern.finditer(text):
            line = text[:m.start()].count("\n") + 1
            name = m.group(1)
            args = m.group(2).strip()
            symbols.append(GraphSymbol(rel, name, kind, line, f"{name}({args})"))
    for m in JS_IMPORT.finditer(text):
        edges.append(GraphEdge(rel, m.group(1), "imports"))
    return symbols, edges


def build_knowledge_graph(repo_path: Path) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    for path in repo_path.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTENSIONS or _skip(path, repo_path):
            continue
        graph.files_scanned += 1
        rel = str(path.relative_to(repo_path))
        graph.source_files.append(rel)
        lower = path.name.lower()
        if any(pat in lower for pat in TEST_PATTERNS) or "tests" in {p.lower() for p in path.parts}:
            graph.test_files.append(rel)
        if path.suffix.lower() == ".py":
            symbols, edges = _parse_python(path, repo_path)
        else:
            symbols, edges = _parse_js(path, repo_path)
        graph.symbols.extend(symbols)
        graph.edges.extend(edges)
    return graph
