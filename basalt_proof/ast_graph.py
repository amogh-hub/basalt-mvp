from __future__ import annotations

import ast
import fnmatch
import re
from pathlib import Path

from .models import GraphEdge, GraphSymbol, KnowledgeGraph

SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}
TEST_PATTERNS = ("test_", "_test", ".test.", ".spec.")
SKIP_PARTS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".basalt",
    ".basalt-deps",
}
LANGUAGE_NAMES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript JSX",
    ".ts": "TypeScript",
    ".tsx": "TypeScript TSX",
}


def _matches(relative: str, patterns: list[str] | None) -> bool:
    for pattern in patterns or []:
        normalized = pattern.strip().strip("/")
        if not normalized:
            continue
        if fnmatch.fnmatch(relative, normalized) or fnmatch.fnmatch(relative, normalized + "/**"):
            return True
        if relative == normalized or relative.startswith(normalized + "/"):
            return True
    return False


def _skip(path: Path, repo_path: Path, excluded_paths: list[str] | None = None) -> bool:
    relative_path = path.relative_to(repo_path)
    if set(relative_path.parts) & SKIP_PARTS:
        return True
    return _matches(relative_path.as_posix(), excluded_paths)


def _signature_from_args(args: ast.arguments) -> str:
    names = [arg.arg for arg in args.args]
    return "(" + ", ".join(names) + ")"


def _parse_python(path: Path, repo_path: Path) -> tuple[list[GraphSymbol], list[GraphEdge]]:
    rel = path.relative_to(repo_path).as_posix()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return [], []
    symbols: list[GraphSymbol] = []
    edges: list[GraphEdge] = []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            symbols.append(
                GraphSymbol(rel, node.name, "function", node.lineno, node.name + _signature_from_args(node.args))
            )
        elif isinstance(node, ast.AsyncFunctionDef):
            symbols.append(
                GraphSymbol(rel, node.name, "async_function", node.lineno, node.name + _signature_from_args(node.args))
            )
        elif isinstance(node, ast.ClassDef):
            symbols.append(GraphSymbol(rel, node.name, "class", node.lineno, node.name))
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    edges.extend(GraphEdge(rel, target, "imports") for target in imports)
    return symbols, edges


JS_FUNC = re.compile(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)")
JS_CONST_FN = re.compile(r"(?:export\s+)?(?:const|let)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>")
JS_IMPORT = re.compile(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]")
JS_REQUIRE = re.compile(r"require\(['\"]([^'\"]+)['\"]\)")


def _parse_js(path: Path, repo_path: Path) -> tuple[list[GraphSymbol], list[GraphEdge]]:
    rel = path.relative_to(repo_path).as_posix()
    text = path.read_text(encoding="utf-8", errors="ignore")
    symbols: list[GraphSymbol] = []
    edges: list[GraphEdge] = []
    for pattern, kind in ((JS_FUNC, "function"), (JS_CONST_FN, "function")):
        for match in pattern.finditer(text):
            line = text[: match.start()].count("\n") + 1
            name = match.group(1)
            args = match.group(2).strip()
            symbols.append(GraphSymbol(rel, name, kind, line, f"{name}({args})"))
    for pattern in (JS_IMPORT, JS_REQUIRE):
        edges.extend(GraphEdge(rel, match.group(1), "imports") for match in pattern.finditer(text))
    return symbols, edges


def build_knowledge_graph(
    repo_path: Path,
    excluded_paths: list[str] | None = None,
) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    for path in repo_path.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        if _skip(path, repo_path, excluded_paths):
            continue
        graph.files_scanned += 1
        rel = path.relative_to(repo_path).as_posix()
        graph.source_files.append(rel)
        language = LANGUAGE_NAMES.get(path.suffix.lower(), path.suffix.lower())
        graph.languages[language] = graph.languages.get(language, 0) + 1
        lower = path.name.lower()
        if any(pattern in lower for pattern in TEST_PATTERNS) or "tests" in {part.lower() for part in path.parts}:
            graph.test_files.append(rel)
        if path.suffix.lower() == ".py":
            symbols, edges = _parse_python(path, repo_path)
        else:
            symbols, edges = _parse_js(path, repo_path)
        graph.symbols.extend(symbols)
        graph.edges.extend(edges)
    return graph
