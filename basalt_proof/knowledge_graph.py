from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import re
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import (
    FeatureNode,
    GraphEdge,
    GraphFile,
    GraphFreshness,
    GraphSymbol,
    ImpactAnalysis,
    KnowledgeGraph,
    TestMapping,
)

GRAPH_VERSION = "2.1"
PARSER_VERSION = "phase2-stdlib-1"
SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".sql"}
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
    "coverage",
}
TEST_MARKERS = ("test_", "_test", ".test.", ".spec.")
LANGUAGE_NAMES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript JSX",
    ".ts": "TypeScript",
    ".tsx": "TypeScript TSX",
    ".sql": "SQL",
}
GENERIC_FEATURE_TOKENS = {
    "src",
    "lib",
    "app",
    "apps",
    "core",
    "utils",
    "util",
    "common",
    "shared",
    "index",
    "main",
    "test",
    "tests",
    "spec",
    "components",
    "component",
    "pages",
    "page",
    "routes",
    "route",
    "models",
    "model",
}
CRITICAL_TOKENS = {
    "auth",
    "permission",
    "security",
    "payment",
    "billing",
    "migration",
    "database",
    "secret",
    "deploy",
    "production",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_hash(path: Path) -> str:
    try:
        return _hash_bytes(path.read_bytes())
    except OSError:
        return ""


def _state_hash(file_hashes: dict[str, str]) -> str:
    payload = "\n".join(f"{path}:{digest}" for path, digest in sorted(file_hashes.items()))
    return _hash_bytes(payload.encode("utf-8"))


def _matches(relative: str, patterns: list[str] | None) -> bool:
    for pattern in patterns or []:
        normalized = pattern.strip().strip("/")
        if not normalized:
            continue
        if relative == normalized or relative.startswith(normalized + "/"):
            return True
        if fnmatch.fnmatch(relative, normalized) or fnmatch.fnmatch(relative, normalized + "/**"):
            return True
    return False


def _is_test_file(relative: str) -> bool:
    path = Path(relative)
    lower = path.name.lower()
    parts = {part.lower() for part in path.parts}
    return "tests" in parts or "test" in parts or any(marker in lower for marker in TEST_MARKERS)


def discover_graph_files(repo_path: Path, excluded_paths: list[str] | None = None) -> list[Path]:
    discovered: list[Path] = []
    for path in repo_path.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        relative = path.relative_to(repo_path)
        if set(relative.parts) & SKIP_PARTS:
            continue
        if _matches(relative.as_posix(), excluded_paths):
            continue
        discovered.append(path)
    return sorted(discovered, key=lambda item: item.relative_to(repo_path).as_posix())


def current_file_hashes(repo_path: Path, excluded_paths: list[str] | None = None) -> dict[str, str]:
    return {
        path.relative_to(repo_path).as_posix(): _file_hash(path)
        for path in discover_graph_files(repo_path, excluded_paths)
    }


def _safe_unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _python_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args: list[str] = []
    positional = list(node.args.posonlyargs) + list(node.args.args)
    defaults_offset = len(positional) - len(node.args.defaults)
    for index, arg in enumerate(positional):
        item = arg.arg
        annotation = _safe_unparse(arg.annotation)
        if annotation:
            item += f": {annotation}"
        if index >= defaults_offset and node.args.defaults:
            default = node.args.defaults[index - defaults_offset]
            item += f" = {_safe_unparse(default)}"
        args.append(item)
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    for kwarg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        item = kwarg.arg
        annotation = _safe_unparse(kwarg.annotation)
        if annotation:
            item += f": {annotation}"
        if default is not None:
            item += f" = {_safe_unparse(default)}"
        args.append(item)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    result = f"{node.name}({', '.join(args)})"
    returns = _safe_unparse(node.returns)
    return result + (f" -> {returns}" if returns else "")


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    return ""


def _symbol_id(file_path: str, qualified_name: str) -> str:
    return f"symbol:{file_path}::{qualified_name}"


def _file_id(file_path: str) -> str:
    return f"file:{file_path}"


def _feature_id(feature_id: str) -> str:
    return f"feature:{feature_id}"


class _PythonGraphVisitor(ast.NodeVisitor):
    def __init__(self, relative: str):
        self.relative = relative
        self.symbols: list[GraphSymbol] = []
        self.edges: list[GraphEdge] = []
        self.routes: list[str] = []
        self.scope: list[str] = []
        self.current_symbol_ids: list[str] = []

    def _qualified(self, name: str) -> str:
        return ".".join([*self.scope, name]) if self.scope else name

    def _current_source(self) -> str:
        return self.current_symbol_ids[-1] if self.current_symbol_ids else _file_id(self.relative)

    def _add_symbol(
        self,
        name: str,
        kind: str,
        line: int,
        end_line: int,
        signature: str = "",
        docstring: str = "",
        return_type: str = "",
        decorators: list[str] | None = None,
    ) -> GraphSymbol:
        qualified = self._qualified(name)
        symbol = GraphSymbol(
            file=self.relative,
            name=name,
            kind=kind,
            line=line,
            signature=signature,
            id=_symbol_id(self.relative, qualified),
            qualified_name=qualified,
            end_line=end_line,
            parent=".".join(self.scope),
            docstring=docstring,
            return_type=return_type,
            decorators=decorators or [],
        )
        self.symbols.append(symbol)
        self.edges.append(
            GraphEdge(
                source=_file_id(self.relative),
                target=symbol.id,
                edge_type="contains",
                source_file=self.relative,
                target_file=self.relative,
                line=line,
                confidence=1.0,
            )
        )
        return symbol

    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            self.edges.append(
                GraphEdge(
                    source=self._current_source(),
                    target=f"raw:pyimport:0:{alias.name}",
                    edge_type="imports",
                    source_file=self.relative,
                    line=node.lineno,
                    confidence=1.0,
                    metadata={"raw_target": alias.name, "level": 0},
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        module = node.module or ""
        self.edges.append(
            GraphEdge(
                source=self._current_source(),
                target=f"raw:pyimport:{node.level}:{module}",
                edge_type="imports",
                source_file=self.relative,
                line=node.lineno,
                confidence=1.0,
                metadata={"raw_target": module, "level": node.level},
            )
        )

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> None:
        decorators = [_dotted_name(item) for item in node.decorator_list if _dotted_name(item)]
        symbol = self._add_symbol(
            node.name,
            kind,
            node.lineno,
            getattr(node, "end_lineno", node.lineno),
            signature=_python_signature(node),
            docstring=ast.get_docstring(node) or "",
            return_type=_safe_unparse(node.returns),
            decorators=decorators,
        )
        for decorator in node.decorator_list:
            name = _dotted_name(decorator)
            if name:
                self.edges.append(
                    GraphEdge(
                        source=symbol.id,
                        target=f"raw:decorator:{name}",
                        edge_type="decorated_by",
                        source_file=self.relative,
                        line=node.lineno,
                        confidence=1.0,
                        metadata={"raw_target": name},
                    )
                )
            if isinstance(decorator, ast.Call):
                route_name = _dotted_name(decorator.func)
                method = route_name.rsplit(".", 1)[-1].upper() if route_name else ""
                if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
                    route_path = ""
                    if decorator.args and isinstance(decorator.args[0], ast.Constant):
                        route_path = str(decorator.args[0].value)
                    route_label = f"{method} {route_path or '/'}"
                    route = self._add_symbol(
                        route_label,
                        "api_route",
                        node.lineno,
                        getattr(node, "end_lineno", node.lineno),
                        signature=route_label,
                    )
                    self.routes.append(route_label)
                    self.edges.append(
                        GraphEdge(
                            source=route.id,
                            target=symbol.id,
                            edge_type="handled_by",
                            source_file=self.relative,
                            target_file=self.relative,
                            line=node.lineno,
                            confidence=1.0,
                        )
                    )
        self.scope.append(node.name)
        self.current_symbol_ids.append(symbol.id)
        self.generic_visit(node)
        self.current_symbol_ids.pop()
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_function(node, "async_function")

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        decorators = [_dotted_name(item) for item in node.decorator_list if _dotted_name(item)]
        symbol = self._add_symbol(
            node.name,
            "class",
            node.lineno,
            getattr(node, "end_lineno", node.lineno),
            signature=node.name,
            docstring=ast.get_docstring(node) or "",
            decorators=decorators,
        )
        for base in node.bases:
            base_name = _dotted_name(base) or _safe_unparse(base)
            if base_name:
                self.edges.append(
                    GraphEdge(
                        source=symbol.id,
                        target=f"raw:symbol:{base_name}",
                        edge_type="inherits",
                        source_file=self.relative,
                        line=node.lineno,
                        confidence=0.9,
                        metadata={"raw_target": base_name},
                    )
                )
        self.scope.append(node.name)
        self.current_symbol_ids.append(symbol.id)
        self.generic_visit(node)
        self.current_symbol_ids.pop()
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> Any:
        name = _dotted_name(node.func)
        if name:
            self.edges.append(
                GraphEdge(
                    source=self._current_source(),
                    target=f"raw:symbol:{name}",
                    edge_type="calls",
                    source_file=self.relative,
                    line=getattr(node, "lineno", 0),
                    confidence=0.75,
                    metadata={"raw_target": name},
                )
            )
        self.generic_visit(node)


def _parse_python(path: Path, repo_path: Path) -> tuple[list[GraphSymbol], list[GraphEdge], list[str], list[str]]:
    relative = path.relative_to(repo_path).as_posix()
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text)
    except (OSError, SyntaxError):
        return [], [], [], []
    visitor = _PythonGraphVisitor(relative)
    visitor.visit(tree)
    return visitor.symbols, visitor.edges, visitor.routes, []


JS_FUNCTION = re.compile(
    r"(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)",
)
JS_ARROW = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\(([^)]*)\)|([A-Za-z_$][\w$]*))\s*=>",
)
JS_CLASS = re.compile(r"(?:export\s+(?:default\s+)?)?class\s+([A-Za-z_$][\w$]*)(?:\s+extends\s+([A-Za-z_$][\w$\.]*))?")
JS_INTERFACE = re.compile(r"(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)")
JS_TYPE = re.compile(r"(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*=")
JS_IMPORT = re.compile(r"import\s+(?:type\s+)?(?:[\s\S]*?)\s+from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]")
JS_REQUIRE = re.compile(r"require\(['\"]([^'\"]+)['\"]\)")
JS_ROUTE = re.compile(
    r"\b(?:app|router|server)\.(get|post|put|patch|delete|options|head)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
JS_CALL = re.compile(r"\b([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(")
JS_CALL_EXCLUDE = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "function",
    "return",
    "typeof",
    "new",
    "console.log",
}


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _parse_js(path: Path, repo_path: Path) -> tuple[list[GraphSymbol], list[GraphEdge], list[str], list[str]]:
    relative = path.relative_to(repo_path).as_posix()
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], [], [], []
    symbols: list[GraphSymbol] = []
    edges: list[GraphEdge] = []
    routes: list[str] = []

    def add_symbol(name: str, kind: str, line: int, signature: str = "") -> GraphSymbol:
        symbol = GraphSymbol(
            file=relative,
            name=name,
            kind=kind,
            line=line,
            signature=signature or name,
            id=_symbol_id(relative, name),
            qualified_name=name,
            end_line=line,
        )
        symbols.append(symbol)
        edges.append(
            GraphEdge(
                source=_file_id(relative),
                target=symbol.id,
                edge_type="contains",
                source_file=relative,
                target_file=relative,
                line=line,
                confidence=1.0,
            )
        )
        return symbol

    for match in JS_FUNCTION.finditer(text):
        name = match.group(1)
        args = match.group(2).strip()
        kind = "component" if name[:1].isupper() and path.suffix.lower() in {".jsx", ".tsx"} else "function"
        add_symbol(name, kind, _line_number(text, match.start()), f"{name}({args})")
    for match in JS_ARROW.finditer(text):
        name = match.group(1)
        args = (match.group(2) or match.group(3) or "").strip()
        kind = "component" if name[:1].isupper() and path.suffix.lower() in {".jsx", ".tsx"} else "function"
        add_symbol(name, kind, _line_number(text, match.start()), f"{name}({args})")
    for match in JS_CLASS.finditer(text):
        symbol = add_symbol(match.group(1), "class", _line_number(text, match.start()))
        if match.group(2):
            edges.append(
                GraphEdge(
                    source=symbol.id,
                    target=f"raw:symbol:{match.group(2)}",
                    edge_type="inherits",
                    source_file=relative,
                    line=symbol.line,
                    confidence=0.9,
                    metadata={"raw_target": match.group(2)},
                )
            )
    for pattern, kind in ((JS_INTERFACE, "interface"), (JS_TYPE, "type")):
        for match in pattern.finditer(text):
            add_symbol(match.group(1), kind, _line_number(text, match.start()))
    for match in JS_IMPORT.finditer(text):
        target = match.group(1) or match.group(2)
        edges.append(
            GraphEdge(
                source=_file_id(relative),
                target=f"raw:jsimport:{target}",
                edge_type="imports",
                source_file=relative,
                line=_line_number(text, match.start()),
                confidence=1.0,
                metadata={"raw_target": target},
            )
        )
    for match in JS_REQUIRE.finditer(text):
        target = match.group(1)
        edges.append(
            GraphEdge(
                source=_file_id(relative),
                target=f"raw:jsimport:{target}",
                edge_type="imports",
                source_file=relative,
                line=_line_number(text, match.start()),
                confidence=1.0,
                metadata={"raw_target": target},
            )
        )
    for match in JS_ROUTE.finditer(text):
        route_label = f"{match.group(1).upper()} {match.group(2)}"
        route = add_symbol(route_label, "api_route", _line_number(text, match.start()), route_label)
        routes.append(route_label)
        edges.append(
            GraphEdge(
                source=_file_id(relative),
                target=route.id,
                edge_type="defines_route",
                source_file=relative,
                target_file=relative,
                line=route.line,
                confidence=1.0,
            )
        )
    exported_methods = re.findall(r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b", text)
    if exported_methods and any(part.lower() in {"api", "routes"} for part in path.parts):
        for method in exported_methods:
            route_label = f"{method} {relative}"
            add_symbol(route_label, "api_route", 1, route_label)
            routes.append(route_label)
    for match in JS_CALL.finditer(text):
        name = match.group(1)
        if name in JS_CALL_EXCLUDE:
            continue
        edges.append(
            GraphEdge(
                source=_file_id(relative),
                target=f"raw:symbol:{name}",
                edge_type="calls",
                source_file=relative,
                line=_line_number(text, match.start()),
                confidence=0.55,
                metadata={"raw_target": name},
            )
        )
    return symbols, edges, routes, []


SQL_TABLE = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`\[]?([A-Za-z_][\w.]*)", re.IGNORECASE)
SQL_VIEW = re.compile(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+[\"`\[]?([A-Za-z_][\w.]*)", re.IGNORECASE)
SQL_REFERENCE = re.compile(r"\bREFERENCES\s+[\"`\[]?([A-Za-z_][\w.]*)", re.IGNORECASE)


def _parse_sql(path: Path, repo_path: Path) -> tuple[list[GraphSymbol], list[GraphEdge], list[str], list[str]]:
    relative = path.relative_to(repo_path).as_posix()
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], [], [], []
    symbols: list[GraphSymbol] = []
    edges: list[GraphEdge] = []
    schemas: list[str] = []
    for pattern, kind in ((SQL_TABLE, "database_table"), (SQL_VIEW, "database_view")):
        for match in pattern.finditer(text):
            name = match.group(1)
            symbol = GraphSymbol(
                file=relative,
                name=name,
                kind=kind,
                line=_line_number(text, match.start()),
                signature=name,
                id=_symbol_id(relative, name),
                qualified_name=name,
                end_line=_line_number(text, match.end()),
            )
            symbols.append(symbol)
            schemas.append(name)
            edges.append(
                GraphEdge(
                    source=_file_id(relative),
                    target=symbol.id,
                    edge_type="contains",
                    source_file=relative,
                    target_file=relative,
                    line=symbol.line,
                    confidence=1.0,
                )
            )
    for match in SQL_REFERENCE.finditer(text):
        target = match.group(1)
        edges.append(
            GraphEdge(
                source=_file_id(relative),
                target=f"raw:schema:{target}",
                edge_type="references_table",
                source_file=relative,
                line=_line_number(text, match.start()),
                confidence=0.9,
                metadata={"raw_target": target},
            )
        )
    return symbols, edges, [], schemas


def _module_index(source_files: Iterable[str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for relative in source_files:
        path = Path(relative)
        if path.suffix.lower() != ".py":
            continue
        parts = list(path.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        module = ".".join(parts)
        index[module] = relative
        index[parts[-1]] = relative
    return index


def _resolve_python_import(source_file: str, raw_target: str, level: int, module_index: dict[str, str]) -> str | None:
    if level <= 0:
        if raw_target in module_index:
            return module_index[raw_target]
        pieces = raw_target.split(".")
        for size in range(len(pieces), 0, -1):
            candidate = ".".join(pieces[:size])
            if candidate in module_index:
                return module_index[candidate]
        return None
    source_parts = list(Path(source_file).with_suffix("").parts[:-1])
    keep = max(0, len(source_parts) - level + 1)
    prefix = source_parts[:keep]
    if raw_target:
        prefix.extend(raw_target.split("."))
    candidate = ".".join(prefix)
    return module_index.get(candidate) or module_index.get(raw_target)


def _resolve_js_import(source_file: str, raw_target: str, source_files: set[str]) -> str | None:
    if not raw_target.startswith("."):
        return None
    base = Path(source_file).parent / raw_target
    candidates = [
        base,
        base.with_suffix(".js"),
        base.with_suffix(".jsx"),
        base.with_suffix(".ts"),
        base.with_suffix(".tsx"),
        base / "index.js",
        base / "index.jsx",
        base / "index.ts",
        base / "index.tsx",
    ]
    for candidate in candidates:
        normalized = candidate.as_posix()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized in source_files:
            return normalized
    return None


def _resolve_edges(graph: KnowledgeGraph) -> None:
    source_files = set(graph.source_files)
    module_index = _module_index(graph.source_files)
    symbols_by_name: dict[str, list[GraphSymbol]] = {}
    symbols_by_file_name: dict[tuple[str, str], GraphSymbol] = {}
    schemas: dict[str, GraphSymbol] = {}
    for symbol in graph.symbols:
        symbols_by_name.setdefault(symbol.name, []).append(symbol)
        symbols_by_name.setdefault(symbol.qualified_name, []).append(symbol)
        symbols_by_file_name[(symbol.file, symbol.name)] = symbol
        if symbol.kind in {"database_table", "database_view"}:
            schemas[symbol.name] = symbol

    for edge in graph.edges:
        raw_target = str(edge.metadata.get("raw_target", "")) if edge.metadata else ""
        if edge.target.startswith("raw:pyimport:"):
            level = int(edge.metadata.get("level", 0)) if edge.metadata else 0
            resolved = _resolve_python_import(edge.source_file, raw_target, level, module_index)
            if resolved:
                edge.target = _file_id(resolved)
                edge.target_file = resolved
            else:
                edge.target = f"external:{raw_target or 'unknown'}"
                edge.confidence = 0.6
        elif edge.target.startswith("raw:jsimport:"):
            resolved = _resolve_js_import(edge.source_file, raw_target, source_files)
            if resolved:
                edge.target = _file_id(resolved)
                edge.target_file = resolved
            else:
                edge.target = f"external:{raw_target or 'unknown'}"
                edge.confidence = 0.6
        elif edge.target.startswith("raw:symbol:"):
            short_name = raw_target.rsplit(".", 1)[-1]
            local = symbols_by_file_name.get((edge.source_file, short_name))
            candidates = symbols_by_name.get(raw_target) or symbols_by_name.get(short_name) or []
            resolved_symbol = local or (candidates[0] if len(candidates) == 1 else None)
            if resolved_symbol:
                edge.target = resolved_symbol.id
                edge.target_file = resolved_symbol.file
                edge.confidence = max(edge.confidence, 0.8 if local else 0.65)
            else:
                edge.target = f"external_symbol:{raw_target or 'unknown'}"
                edge.confidence = min(edge.confidence, 0.5)
        elif edge.target.startswith("raw:schema:"):
            resolved_schema = schemas.get(raw_target)
            if resolved_schema:
                edge.target = resolved_schema.id
                edge.target_file = resolved_schema.file
            else:
                edge.target = f"external_schema:{raw_target or 'unknown'}"
        elif edge.target.startswith("raw:decorator:"):
            edge.target = f"decorator:{raw_target or 'unknown'}"


def _mapping_reason(test_file: str, source_file: str, graph: KnowledgeGraph) -> tuple[str, float]:
    for edge in graph.edges:
        if edge.edge_type == "imports" and edge.source_file == test_file and edge.target_file == source_file:
            return "test imports source file", 1.0
    test_stem = Path(test_file).stem.lower()
    source_stem = Path(source_file).stem.lower()
    normalized_test = test_stem.replace("test_", "").replace("_test", "").replace(".test", "").replace(".spec", "")
    if normalized_test == source_stem or source_stem in normalized_test or normalized_test in source_stem:
        return "test and source filenames match", 0.85
    return "shared symbol reference", 0.55


def _build_test_mappings(graph: KnowledgeGraph) -> list[TestMapping]:
    mappings: dict[tuple[str, str], TestMapping] = {}
    source_files = [item for item in graph.source_files if item not in graph.test_files]
    for test_file in graph.test_files:
        imported_targets = {
            edge.target_file
            for edge in graph.edges
            if edge.edge_type == "imports" and edge.source_file == test_file and edge.target_file
        }
        for source_file in imported_targets:
            reason, confidence = _mapping_reason(test_file, source_file, graph)
            mappings[(test_file, source_file)] = TestMapping(test_file, source_file, reason=reason, confidence=confidence)
        if not imported_targets:
            for source_file in source_files:
                reason, confidence = _mapping_reason(test_file, source_file, graph)
                if confidence >= 0.8:
                    mappings[(test_file, source_file)] = TestMapping(test_file, source_file, reason=reason, confidence=confidence)
    return sorted(mappings.values(), key=lambda item: (item.test_file, item.source_file))


def _tokenize_feature(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    tokens = re.split(r"[^A-Za-z0-9]+", value.lower())
    return [token for token in tokens if len(token) >= 3 and token not in GENERIC_FEATURE_TOKENS]


def _load_explicit_features(repo_path: Path) -> list[FeatureNode]:
    path = repo_path / "basalt.features.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_features = payload.get("features", []) if isinstance(payload, dict) else []
    features: list[FeatureNode] = []
    for raw in raw_features:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or raw.get("id") or "").strip()
        if not name:
            continue
        feature_id = str(raw.get("id") or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))
        features.append(
            FeatureNode(
                id=feature_id,
                name=name,
                description=str(raw.get("description") or ""),
                files=[str(item) for item in raw.get("files", []) if str(item)],
                tests=[str(item) for item in raw.get("tests", []) if str(item)],
                keywords=[str(item).lower() for item in raw.get("keywords", []) if str(item)],
                source="explicit",
                confidence=1.0,
            )
        )
    return features


def _build_features(repo_path: Path, graph: KnowledgeGraph) -> list[FeatureNode]:
    explicit = _load_explicit_features(repo_path)
    explicit_files = {file for feature in explicit for file in feature.files}
    buckets: dict[str, set[str]] = {}
    for relative in graph.source_files:
        if relative in graph.test_files or relative in explicit_files:
            continue
        tokens: list[str] = []
        path = Path(relative)
        for part in [*path.parts[:-1], path.stem]:
            tokens.extend(_tokenize_feature(part))
        for symbol in graph.symbols:
            if symbol.file == relative:
                tokens.extend(_tokenize_feature(symbol.name))
        unique = []
        for token in tokens:
            if token not in unique:
                unique.append(token)
        for token in unique[:3]:
            buckets.setdefault(token, set()).add(relative)
    inferred: list[FeatureNode] = []
    for token, files in sorted(buckets.items()):
        if not files:
            continue
        tests = sorted(
            {
                mapping.test_file
                for mapping in graph.test_mappings
                if mapping.source_file in files
            }
        )
        inferred.append(
            FeatureNode(
                id=token,
                name=token.replace("_", " ").replace("-", " ").title(),
                description=f"Deterministically inferred from file and symbol names containing '{token}'.",
                files=sorted(files),
                tests=tests,
                keywords=[token],
                source="inferred",
                confidence=0.65,
            )
        )
    features_by_id = {feature.id: feature for feature in inferred}
    for feature in explicit:
        features_by_id[feature.id] = feature
    return sorted(features_by_id.values(), key=lambda item: (item.source != "explicit", item.name.lower()))


def _add_mapping_edges(graph: KnowledgeGraph) -> None:
    existing = {(edge.source, edge.target, edge.edge_type) for edge in graph.edges}
    for mapping in graph.test_mappings:
        edge = GraphEdge(
            source=_file_id(mapping.test_file),
            target=_file_id(mapping.source_file),
            edge_type="verifies",
            source_file=mapping.test_file,
            target_file=mapping.source_file,
            confidence=mapping.confidence,
            metadata={"reason": mapping.reason},
        )
        key = (edge.source, edge.target, edge.edge_type)
        if key not in existing:
            graph.edges.append(edge)
            existing.add(key)
    for feature in graph.features:
        feature_node = _feature_id(feature.id)
        for file_path in feature.files:
            edge = GraphEdge(
                source=feature_node,
                target=_file_id(file_path),
                edge_type="implemented_by",
                target_file=file_path,
                confidence=feature.confidence,
                metadata={"source": feature.source},
            )
            key = (edge.source, edge.target, edge.edge_type)
            if key not in existing:
                graph.edges.append(edge)
                existing.add(key)
        for test_path in feature.tests:
            edge = GraphEdge(
                source=_file_id(test_path),
                target=feature_node,
                edge_type="verifies_feature",
                source_file=test_path,
                confidence=feature.confidence,
            )
            key = (edge.source, edge.target, edge.edge_type)
            if key not in existing:
                graph.edges.append(edge)
                existing.add(key)


def _graph_to_json(graph: KnowledgeGraph) -> str:
    return json.dumps(asdict(graph), indent=2, sort_keys=True)


def _graph_from_dict(data: dict[str, Any]) -> KnowledgeGraph:
    graph = KnowledgeGraph(
        graph_version=str(data.get("graph_version", GRAPH_VERSION)),
        parser_version=str(data.get("parser_version", "")),
        state_hash=str(data.get("state_hash", "")),
        built_at=str(data.get("built_at", "")),
        fresh=bool(data.get("fresh", False)),
        files_scanned=int(data.get("files_scanned", 0)),
        test_files=list(data.get("test_files", [])),
        source_files=list(data.get("source_files", [])),
        languages=dict(data.get("languages", {})),
        routes=list(data.get("routes", [])),
        schemas=list(data.get("schemas", [])),
        changed_files=list(data.get("changed_files", [])),
        reused_files=list(data.get("reused_files", [])),
        removed_files=list(data.get("removed_files", [])),
        store_path=data.get("store_path"),
    )
    graph.files = [GraphFile(**item) for item in data.get("files", [])]
    graph.symbols = [GraphSymbol(**item) for item in data.get("symbols", [])]
    graph.edges = [GraphEdge(**item) for item in data.get("edges", [])]
    graph.features = [FeatureNode(**item) for item in data.get("features", [])]
    graph.test_mappings = [TestMapping(**item) for item in data.get("test_mappings", [])]
    return graph


class GraphStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    language TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    modified_ns INTEGER NOT NULL,
                    is_test INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS symbols (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    qualified_name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    signature TEXT NOT NULL,
                    docstring TEXT NOT NULL,
                    return_type TEXT NOT NULL,
                    parent TEXT NOT NULL,
                    decorators_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    target_file TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS features (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    keywords_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feature_files (
                    feature_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    PRIMARY KEY (feature_id, file_path, relation)
                );
                CREATE TABLE IF NOT EXISTS test_mappings (
                    test_file TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    PRIMARY KEY (test_file, source_file, symbol)
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    graph_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
                CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
                CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
                """
            )
            connection.commit()
        finally:
            connection.close()

    def save(self, graph: KnowledgeGraph) -> None:
        self.initialize()
        connection = self._connect()
        try:
            for table in ("metadata", "files", "symbols", "edges", "features", "feature_files", "test_mappings"):
                connection.execute(f"DELETE FROM {table}")
            metadata = {
                "graph_version": graph.graph_version,
                "parser_version": graph.parser_version,
                "state_hash": graph.state_hash,
                "built_at": graph.built_at,
            }
            connection.executemany("INSERT INTO metadata(key, value) VALUES(?, ?)", metadata.items())
            connection.executemany(
                "INSERT INTO files(path, language, hash, size_bytes, modified_ns, is_test) VALUES(?, ?, ?, ?, ?, ?)",
                [
                    (item.path, item.language, item.hash, item.size_bytes, item.modified_ns, int(item.is_test))
                    for item in graph.files
                ],
            )
            connection.executemany(
                """
                INSERT INTO symbols(
                    id, file_path, name, qualified_name, kind, line, end_line,
                    signature, docstring, return_type, parent, decorators_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.id,
                        item.file,
                        item.name,
                        item.qualified_name,
                        item.kind,
                        item.line,
                        item.end_line,
                        item.signature,
                        item.docstring,
                        item.return_type,
                        item.parent,
                        json.dumps(item.decorators),
                    )
                    for item in graph.symbols
                ],
            )
            connection.executemany(
                """
                INSERT INTO edges(source, target, edge_type, source_file, target_file, line, confidence, metadata_json)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.source,
                        item.target,
                        item.edge_type,
                        item.source_file,
                        item.target_file,
                        item.line,
                        item.confidence,
                        json.dumps(item.metadata, sort_keys=True),
                    )
                    for item in graph.edges
                ],
            )
            connection.executemany(
                "INSERT INTO features(id, name, description, source, confidence, keywords_json) VALUES(?, ?, ?, ?, ?, ?)",
                [
                    (item.id, item.name, item.description, item.source, item.confidence, json.dumps(item.keywords))
                    for item in graph.features
                ],
            )
            feature_rows: list[tuple[str, str, str]] = []
            for feature in graph.features:
                feature_rows.extend((feature.id, path, "file") for path in feature.files)
                feature_rows.extend((feature.id, path, "test") for path in feature.tests)
            connection.executemany(
                "INSERT OR REPLACE INTO feature_files(feature_id, file_path, relation) VALUES(?, ?, ?)",
                feature_rows,
            )
            connection.executemany(
                "INSERT INTO test_mappings(test_file, source_file, symbol, reason, confidence) VALUES(?, ?, ?, ?, ?)",
                [
                    (item.test_file, item.source_file, item.symbol, item.reason, item.confidence)
                    for item in graph.test_mappings
                ],
            )
            connection.execute(
                "INSERT OR REPLACE INTO snapshots(id, graph_json) VALUES(1, ?)",
                (_graph_to_json(graph),),
            )
            connection.commit()
        finally:
            connection.close()

    def load(self) -> KnowledgeGraph | None:
        if not self.path.exists():
            return None
        connection = self._connect()
        try:
            row = connection.execute("SELECT graph_json FROM snapshots WHERE id = 1").fetchone()
        except sqlite3.DatabaseError:
            return None
        finally:
            connection.close()
        if not row:
            return None
        try:
            return _graph_from_dict(json.loads(row["graph_json"]))
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def query_symbols(self, term: str, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        query = "SELECT * FROM symbols WHERE (name LIKE ? OR qualified_name LIKE ? OR signature LIKE ?)"
        params: list[Any] = [f"%{term}%", f"%{term}%", f"%{term}%"]
        if kind:
            query += " AND kind = ?"
            params.append(kind)
        query += " ORDER BY name LIMIT ?"
        params.append(limit)
        connection = self._connect()
        try:
            return [dict(row) for row in connection.execute(query, params).fetchall()]
        finally:
            connection.close()


def check_graph_freshness(
    repo_path: Path,
    store_path: Path,
    excluded_paths: list[str] | None = None,
) -> GraphFreshness:
    previous = GraphStore(store_path).load()
    current = current_file_hashes(repo_path, excluded_paths)
    if previous is None:
        return GraphFreshness(
            fresh=False,
            reason="Knowledge graph has not been built.",
            current_state_hash=_state_hash(current),
            stored_state_hash="",
            new_files=sorted(current),
        )
    stored = {item.path: item.hash for item in previous.files}
    changed = sorted(path for path in current.keys() & stored.keys() if current[path] != stored[path])
    new_files = sorted(current.keys() - stored.keys())
    removed = sorted(stored.keys() - current.keys())
    fresh = not changed and not new_files and not removed and previous.parser_version == PARSER_VERSION
    reason = "Graph matches current repository state." if fresh else "Repository changed since the graph was built."
    if previous.parser_version != PARSER_VERSION:
        reason = "Graph parser version changed; rebuild required."
    return GraphFreshness(
        fresh=fresh,
        reason=reason,
        current_state_hash=_state_hash(current),
        stored_state_hash=previous.state_hash,
        changed_files=changed,
        new_files=new_files,
        removed_files=removed,
    )


def build_project_graph(
    repo_path: Path,
    store_path: Path | None = None,
    excluded_paths: list[str] | None = None,
    force: bool = False,
) -> KnowledgeGraph:
    repo_path = repo_path.resolve()
    files = discover_graph_files(repo_path, excluded_paths)
    hashes = {path.relative_to(repo_path).as_posix(): _file_hash(path) for path in files}
    previous = GraphStore(store_path).load() if store_path else None
    previous_hashes = {item.path: item.hash for item in previous.files} if previous else {}
    state_hash = _state_hash(hashes)
    if previous and not force and previous.state_hash == state_hash and previous.parser_version == PARSER_VERSION:
        previous.fresh = True
        previous.changed_files = []
        previous.removed_files = []
        previous.reused_files = sorted(hashes)
        previous.store_path = str(store_path) if store_path else previous.store_path
        return previous

    graph = KnowledgeGraph(
        graph_version=GRAPH_VERSION,
        parser_version=PARSER_VERSION,
        state_hash=state_hash,
        built_at=_now(),
        fresh=True,
        files_scanned=len(files),
        store_path=str(store_path) if store_path else None,
    )
    graph.changed_files = sorted(
        path for path, digest in hashes.items() if previous_hashes.get(path) != digest
    )
    graph.reused_files = sorted(
        path for path, digest in hashes.items() if previous_hashes.get(path) == digest
    )
    graph.removed_files = sorted(set(previous_hashes) - set(hashes))

    for path in files:
        relative = path.relative_to(repo_path).as_posix()
        stat = path.stat()
        language = LANGUAGE_NAMES.get(path.suffix.lower(), path.suffix.lower())
        is_test = _is_test_file(relative)
        graph.files.append(
            GraphFile(
                path=relative,
                language=language,
                hash=hashes[relative],
                size_bytes=stat.st_size,
                modified_ns=stat.st_mtime_ns,
                is_test=is_test,
            )
        )
        graph.source_files.append(relative)
        graph.languages[language] = graph.languages.get(language, 0) + 1
        if is_test:
            graph.test_files.append(relative)
        if path.suffix.lower() == ".py":
            symbols, edges, routes, schemas = _parse_python(path, repo_path)
        elif path.suffix.lower() == ".sql":
            symbols, edges, routes, schemas = _parse_sql(path, repo_path)
        else:
            symbols, edges, routes, schemas = _parse_js(path, repo_path)
        graph.symbols.extend(symbols)
        graph.edges.extend(edges)
        graph.routes.extend(routes)
        graph.schemas.extend(schemas)

    _resolve_edges(graph)
    graph.test_mappings = _build_test_mappings(graph)
    graph.features = _build_features(repo_path, graph)
    _add_mapping_edges(graph)
    graph.routes = sorted(set(graph.routes))
    graph.schemas = sorted(set(graph.schemas))
    graph.source_files = sorted(set(graph.source_files))
    graph.test_files = sorted(set(graph.test_files))
    graph.edges = sorted(
        graph.edges,
        key=lambda item: (item.source, item.edge_type, item.target, item.line),
    )
    graph.symbols = sorted(
        graph.symbols,
        key=lambda item: (item.file, item.line, item.qualified_name),
    )
    if store_path:
        GraphStore(store_path).save(graph)
    return graph


def write_graph_artifacts(graph: KnowledgeGraph, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "project-graph.json"
    md_path = output_dir / "project-graph.md"
    manifest_path = output_dir / "graph-manifest.json"
    json_path.write_text(_graph_to_json(graph), encoding="utf-8")
    manifest = {
        "graph_version": graph.graph_version,
        "parser_version": graph.parser_version,
        "state_hash": graph.state_hash,
        "built_at": graph.built_at,
        "fresh": graph.fresh,
        "files": {item.path: item.hash for item in graph.files},
        "changed_files": graph.changed_files,
        "reused_files": graph.reused_files,
        "removed_files": graph.removed_files,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# Basalt Project Knowledge Graph",
        "",
        f"- Graph version: `{graph.graph_version}`",
        f"- Parser version: `{graph.parser_version}`",
        f"- Project state hash: `{graph.state_hash}`",
        f"- Built at: `{graph.built_at}`",
        f"- Files: `{graph.files_scanned}`",
        f"- Symbols: `{len(graph.symbols)}`",
        f"- Edges: `{len(graph.edges)}`",
        f"- Tests: `{len(graph.test_files)}`",
        f"- Test mappings: `{len(graph.test_mappings)}`",
        f"- Features: `{len(graph.features)}`",
        f"- Routes: `{len(graph.routes)}`",
        f"- Schemas: `{len(graph.schemas)}`",
        "",
        "## Freshness",
        "",
        f"- Changed/new files parsed: `{len(graph.changed_files)}`",
        f"- Unchanged files reused by state comparison: `{len(graph.reused_files)}`",
        f"- Removed files: `{len(graph.removed_files)}`",
        "",
        "## Top Symbols",
        "",
    ]
    for symbol in graph.symbols[:30]:
        lines.append(f"- `{symbol.kind}` **{symbol.qualified_name or symbol.name}** — `{symbol.file}:{symbol.line}`")
    lines.extend(["", "## Features", ""])
    for feature in graph.features[:30]:
        lines.append(
            f"- **{feature.name}** (`{feature.source}`, confidence {feature.confidence:.2f}) — "
            f"{len(feature.files)} files, {len(feature.tests)} tests"
        )
    lines.extend(["", "## Test Mappings", ""])
    for mapping in graph.test_mappings[:30]:
        lines.append(
            f"- `{mapping.test_file}` verifies `{mapping.source_file}` — {mapping.reason} "
            f"({mapping.confidence:.2f})"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [json_path, md_path, manifest_path]


def query_graph(graph: KnowledgeGraph, term: str, kind: str | None = None, limit: int = 50) -> dict[str, Any]:
    lowered = term.lower()
    symbols = [
        item
        for item in graph.symbols
        if (not kind or item.kind == kind)
        and lowered in " ".join([item.name, item.qualified_name, item.signature, item.file]).lower()
    ][:limit]
    files = [item for item in graph.files if lowered in item.path.lower()][:limit]
    features = [
        item
        for item in graph.features
        if lowered in " ".join([item.id, item.name, item.description, *item.keywords]).lower()
    ][:limit]
    return {
        "term": term,
        "kind": kind,
        "symbols": [asdict(item) for item in symbols],
        "files": [asdict(item) for item in files],
        "features": [asdict(item) for item in features],
    }


def _target_nodes(graph: KnowledgeGraph, target: str) -> set[str]:
    normalized = target.strip()
    nodes: set[str] = set()
    for file in graph.files:
        if file.path == normalized or normalized.lower() in file.path.lower():
            nodes.add(_file_id(file.path))
    for symbol in graph.symbols:
        if normalized in {symbol.id, symbol.name, symbol.qualified_name} or normalized.lower() in symbol.qualified_name.lower():
            nodes.add(symbol.id)
    for feature in graph.features:
        if normalized in {feature.id, feature.name} or normalized.lower() in feature.name.lower():
            nodes.add(_feature_id(feature.id))
    return nodes


def analyze_impact(graph: KnowledgeGraph, target: str, depth: int = 3) -> ImpactAnalysis:
    seeds = _target_nodes(graph, target)
    if not seeds:
        return ImpactAnalysis(target=target, found=False, risk_level="UNKNOWN")
    reverse: dict[str, list[GraphEdge]] = {}
    forward: dict[str, list[GraphEdge]] = {}
    for edge in graph.edges:
        reverse.setdefault(edge.target, []).append(edge)
        forward.setdefault(edge.source, []).append(edge)
    visited = set(seeds)
    frontier = set(seeds)
    reasons: dict[str, set[str]] = {seed: {"direct target"} for seed in seeds}
    for _ in range(max(0, depth)):
        next_frontier: set[str] = set()
        for node in frontier:
            for edge in reverse.get(node, []):
                if edge.source not in visited:
                    next_frontier.add(edge.source)
                reasons.setdefault(edge.source, set()).add(f"{edge.edge_type} -> {node}")
            for edge in forward.get(node, []):
                if edge.edge_type in {"contains", "handled_by", "implemented_by"} and edge.target not in visited:
                    next_frontier.add(edge.target)
                    reasons.setdefault(edge.target, set()).add(f"{node} -> {edge.edge_type}")
        visited.update(next_frontier)
        frontier = next_frontier
        if not frontier:
            break

    files: set[str] = set()
    symbols: set[str] = set()
    features: set[str] = set()
    tests: set[str] = set()
    routes: set[str] = set()
    for node in visited:
        if node.startswith("file:"):
            path = node[5:]
            files.add(path)
            if path in graph.test_files:
                tests.add(path)
        elif node.startswith("symbol:"):
            symbols.add(node)
            symbol = next((item for item in graph.symbols if item.id == node), None)
            if symbol:
                files.add(symbol.file)
                if symbol.kind == "api_route":
                    routes.add(symbol.name)
        elif node.startswith("feature:"):
            features.add(node[8:])
    for mapping in graph.test_mappings:
        if mapping.source_file in files:
            tests.add(mapping.test_file)
    for feature in graph.features:
        if any(path in files for path in feature.files):
            features.add(feature.id)
    critical = any(token in " ".join(files | symbols | features).lower() for token in CRITICAL_TOKENS)
    impact_count = len(files) + len(symbols) + len(features) + len(tests)
    if critical or impact_count >= 20:
        risk = "HIGH"
    elif impact_count >= 8:
        risk = "MEDIUM"
    else:
        risk = "LOW"
    reason_rows = [
        {"node": node, "reasons": sorted(values)}
        for node, values in sorted(reasons.items())
        if node in visited
    ]
    return ImpactAnalysis(
        target=target,
        found=True,
        risk_level=risk,
        impacted_files=sorted(files),
        impacted_symbols=sorted(symbols),
        impacted_tests=sorted(tests),
        impacted_features=sorted(features),
        impacted_routes=sorted(routes),
        reasons=reason_rows,
    )


def render_impact_markdown(result: ImpactAnalysis) -> str:
    lines = [
        "# Basalt Change Impact Analysis",
        "",
        f"- Target: `{result.target}`",
        f"- Found: `{result.found}`",
        f"- Risk: `{result.risk_level}`",
        "",
        "## Impacted Files",
        "",
    ]
    lines.extend(f"- `{item}`" for item in result.impacted_files) or lines.append("- None")
    lines.extend(["", "## Impacted Tests", ""])
    lines.extend(f"- `{item}`" for item in result.impacted_tests) or lines.append("- None")
    lines.extend(["", "## Impacted Features", ""])
    lines.extend(f"- `{item}`" for item in result.impacted_features) or lines.append("- None")
    lines.extend(["", "## Impacted Routes", ""])
    lines.extend(f"- `{item}`" for item in result.impacted_routes) or lines.append("- None")
    return "\n".join(lines) + "\n"
