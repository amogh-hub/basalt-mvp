from __future__ import annotations

import ast
import copy
import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

from .models import CheckStatus, CommandSpec, MutationResult
from .runner import CommandExecutor

SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}
SKIP_PARTS = {
    "tests",
    "test",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".basalt",
    ".basalt-deps",
}


@dataclass
class MutationCandidate:
    file_path: Path
    mutation_type: str
    original: str
    replacement: str
    mutated_text: str
    line: int | None = None


@dataclass(frozen=True)
class _PythonDescriptor:
    kind: str
    line: int
    col: int
    original: str
    replacement: str


COMPARE_REPLACEMENTS = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.GtE: ast.Gt,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.Lt: ast.LtE,
}
BINOP_REPLACEMENTS = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv,
}


def _matches_path(relative: str, patterns: list[str] | None) -> bool:
    relative = relative.replace("\\", "/")
    for pattern in patterns or []:
        normalized = pattern.strip().strip("/")
        if not normalized:
            continue
        if fnmatch.fnmatch(relative, normalized) or fnmatch.fnmatch(relative, normalized + "/**"):
            return True
        if relative == normalized or relative.startswith(normalized + "/"):
            return True
    return False


def _candidate_files(
    repo_path: Path,
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
) -> list[Path]:
    candidates: list[Path] = []
    for path in repo_path.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        relative = path.relative_to(repo_path).as_posix()
        lowered_parts = {part.lower() for part in path.relative_to(repo_path).parts}
        if lowered_parts & SKIP_PARTS:
            continue
        if include_paths and not _matches_path(relative, include_paths):
            continue
        if _matches_path(relative, exclude_paths):
            continue
        candidates.append(path)
    return sorted(candidates, key=lambda item: item.relative_to(repo_path).as_posix())


def _python_descriptors(tree: ast.AST) -> list[_PythonDescriptor]:
    descriptors: list[_PythonDescriptor] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            descriptors.append(
                _PythonDescriptor(
                    "bool",
                    getattr(node, "lineno", 0),
                    getattr(node, "col_offset", 0),
                    str(node.value),
                    str(not node.value),
                )
            )
        elif isinstance(node, ast.Compare) and node.ops:
            op = node.ops[0]
            for old, new in COMPARE_REPLACEMENTS.items():
                if isinstance(op, old):
                    descriptors.append(
                        _PythonDescriptor(
                            "compare",
                            getattr(node, "lineno", 0),
                            getattr(node, "col_offset", 0),
                            old.__name__,
                            new.__name__,
                        )
                    )
                    break
        elif isinstance(node, ast.BinOp):
            for old, new in BINOP_REPLACEMENTS.items():
                if isinstance(node.op, old):
                    descriptors.append(
                        _PythonDescriptor(
                            "binop",
                            getattr(node, "lineno", 0),
                            getattr(node, "col_offset", 0),
                            old.__name__,
                            new.__name__,
                        )
                    )
                    break
    return descriptors


class _ApplyPythonMutation(ast.NodeTransformer):
    def __init__(self, descriptor: _PythonDescriptor):
        self.descriptor = descriptor
        self.done = False

    def _match(self, node: ast.AST, kind: str) -> bool:
        return (
            not self.done
            and self.descriptor.kind == kind
            and getattr(node, "lineno", 0) == self.descriptor.line
            and getattr(node, "col_offset", 0) == self.descriptor.col
        )

    def visit_Constant(self, node: ast.Constant):
        if self._match(node, "bool") and isinstance(node.value, bool):
            self.done = True
            return ast.copy_location(ast.Constant(not node.value), node)
        return self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare):
        if self._match(node, "compare") and node.ops:
            op = node.ops[0]
            for old, new in COMPARE_REPLACEMENTS.items():
                if isinstance(op, old):
                    node.ops[0] = new()
                    self.done = True
                    break
        return self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp):
        if self._match(node, "binop"):
            for old, new in BINOP_REPLACEMENTS.items():
                if isinstance(node.op, old):
                    node.op = new()
                    self.done = True
                    break
        return self.generic_visit(node)


def _python_candidates(file_path: Path, per_file: int) -> list[MutationCandidate]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text)
    except (OSError, SyntaxError):
        return []

    candidates: list[MutationCandidate] = []
    for descriptor in _python_descriptors(tree)[:per_file]:
        cloned = copy.deepcopy(tree)
        mutator = _ApplyPythonMutation(descriptor)
        mutated_tree = mutator.visit(cloned)
        if not mutator.done:
            continue
        ast.fix_missing_locations(mutated_tree)
        mutated_text = ast.unparse(mutated_tree) + "\n"
        if mutated_text == text:
            continue
        candidates.append(
            MutationCandidate(
                file_path=file_path,
                mutation_type=f"python_ast_{descriptor.kind}_flip",
                original=descriptor.original,
                replacement=descriptor.replacement,
                mutated_text=mutated_text,
                line=descriptor.line,
            )
        )
    return candidates


JS_RULES = [
    ("js_true_to_false", re.compile(r"\btrue\b"), "false"),
    ("js_false_to_true", re.compile(r"\bfalse\b"), "true"),
    ("js_strict_eq_flip", re.compile(r"===|=="), "!=="),
    ("js_strict_neq_flip", re.compile(r"!==|!="), "==="),
    ("boundary_ge_to_gt", re.compile(r">="), ">"),
    ("boundary_le_to_lt", re.compile(r"<="), "<"),
    ("boundary_gt_to_ge", re.compile(r"(?<![=>])>(?!=)"), ">="),
    ("boundary_lt_to_le", re.compile(r"(?<![=<])<(?!=)"), "<="),
    ("arithmetic_plus_to_minus", re.compile(r"\s\+\s"), " - "),
]


def _text_candidates(file_path: Path, per_file: int) -> list[MutationCandidate]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    candidates: list[MutationCandidate] = []
    for name, pattern, replacement in JS_RULES:
        for match in pattern.finditer(text):
            original = match.group(0)
            mutated = text[: match.start()] + replacement + text[match.end() :]
            line = text[: match.start()].count("\n") + 1
            candidates.append(
                MutationCandidate(file_path, name, original, replacement, mutated, line)
            )
            if len(candidates) >= per_file:
                return candidates
    return candidates


def _find_mutations(file_path: Path, per_file: int) -> list[MutationCandidate]:
    if file_path.suffix.lower() == ".py":
        return _python_candidates(file_path, per_file)
    return _text_candidates(file_path, per_file)


def run_mutation_sample(
    repo_path: Path,
    test_command: CommandSpec | None,
    executor: CommandExecutor,
    max_mutations: int = 8,
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
    per_file: int = 2,
) -> list[MutationResult]:
    if test_command is None or not test_command.command or max_mutations <= 0:
        return []

    results: list[MutationResult] = []
    for file_path in _candidate_files(repo_path, include_paths, exclude_paths):
        original_text = file_path.read_text(encoding="utf-8", errors="ignore")
        for candidate in _find_mutations(file_path, per_file):
            if len(results) >= max_mutations:
                return results
            file_path.write_text(candidate.mutated_text, encoding="utf-8")
            try:
                if isinstance(executor, CommandExecutor):
                    mutation_executor = CommandExecutor(
                        sandbox=executor.requested_sandbox,
                        docker_image=executor.docker_image,
                        docker_network=executor.docker_network,
                        fallback_to_temp=executor.fallback_to_temp,
                    )
                else:
                    mutation_executor = executor
                test_result = mutation_executor.run(test_command, repo_path)
                survived = test_result.status == CheckStatus.PASS
                results.append(
                    MutationResult(
                        file=str(file_path.relative_to(repo_path)),
                        mutation_type=candidate.mutation_type,
                        original=candidate.original,
                        replacement=candidate.replacement,
                        survived=survived,
                        test_status=test_result.status,
                        message=(
                            "Mutation survived: tests did not catch the injected bug."
                            if survived
                            else "Mutation killed: tests caught the injected bug."
                        ),
                        line=candidate.line,
                    )
                )
            finally:
                file_path.write_text(original_text, encoding="utf-8")
    return results
