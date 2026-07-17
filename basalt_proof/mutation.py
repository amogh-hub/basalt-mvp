from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .models import CheckStatus, CommandSpec, MutationResult
from .runner import CommandExecutor

SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}
SKIP_PARTS = {"tests", "test", "node_modules", ".git", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".basalt"}


@dataclass
class MutationCandidate:
    file_path: Path
    mutation_type: str
    original: str
    replacement: str
    mutated_text: str


@dataclass
class TextMutationRule:
    name: str
    original: str
    replacement: str


TEXT_RULES = [
    TextMutationRule("boolean_flip_true", "True", "False"),
    TextMutationRule("boolean_flip_false", "False", "True"),
    TextMutationRule("strict_equality_flip", " == ", " != "),
    TextMutationRule("strict_inequality_flip", " != ", " == "),
    TextMutationRule("boundary_ge_to_gt", " >= ", " > "),
    TextMutationRule("boundary_le_to_lt", " <= ", " < "),
    TextMutationRule("boundary_gt_to_ge", " > ", " >= "),
    TextMutationRule("boundary_lt_to_le", " < ", " <= "),
    TextMutationRule("arithmetic_plus_to_minus", " + ", " - "),
    TextMutationRule("js_true_to_false", "true", "false"),
    TextMutationRule("js_false_to_true", "false", "true"),
    TextMutationRule("js_strict_eq_flip", " === ", " !== "),
    TextMutationRule("js_strict_neq_flip", " !== ", " === "),
]


class _PythonMutator(ast.NodeTransformer):
    def __init__(self):
        self.done = False
        self.original = ""
        self.replacement = ""

    def visit_Constant(self, node: ast.Constant):
        if self.done:
            return node
        if isinstance(node.value, bool):
            self.done = True
            self.original = str(node.value)
            self.replacement = str(not node.value)
            return ast.copy_location(ast.Constant(not node.value), node)
        return node

    def visit_Compare(self, node: ast.Compare):
        self.generic_visit(node)
        if self.done or not node.ops:
            return node
        op = node.ops[0]
        replacements = {
            ast.Eq: ast.NotEq,
            ast.NotEq: ast.Eq,
            ast.GtE: ast.Gt,
            ast.LtE: ast.Lt,
            ast.Gt: ast.GtE,
            ast.Lt: ast.LtE,
        }
        for old, new in replacements.items():
            if isinstance(op, old):
                self.done = True
                self.original = old.__name__
                self.replacement = new.__name__
                node.ops[0] = new()
                return node
        return node

    def visit_BinOp(self, node: ast.BinOp):
        self.generic_visit(node)
        if self.done:
            return node
        replacements = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv}
        for old, new in replacements.items():
            if isinstance(node.op, old):
                self.done = True
                self.original = old.__name__
                self.replacement = new.__name__
                node.op = new()
                return node
        return node


def _matches_path(relative: str, patterns: list[str] | None) -> bool:
    for pattern in patterns or []:
        normalized = pattern.strip().strip("/")
        if normalized and (relative == normalized or relative.startswith(normalized + "/")):
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


def _python_ast_candidate(file_path: Path) -> MutationCandidate | None:
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text)
        mutator = _PythonMutator()
        mutated_tree = mutator.visit(tree)
        if not mutator.done:
            return None
        ast.fix_missing_locations(mutated_tree)
        mutated_text = ast.unparse(mutated_tree) + "\n"
        if mutated_text == text:
            return None
        return MutationCandidate(file_path, "python_ast_logic_flip", mutator.original, mutator.replacement, mutated_text)
    except Exception:
        return None


def _text_candidate(file_path: Path) -> MutationCandidate | None:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    for rule in TEXT_RULES:
        if rule.original in text:
            return MutationCandidate(file_path, rule.name, rule.original, rule.replacement, text.replace(rule.original, rule.replacement, 1))
    return None


def _find_mutation(file_path: Path) -> MutationCandidate | None:
    if file_path.suffix.lower() == ".py":
        return _python_ast_candidate(file_path) or _text_candidate(file_path)
    return _text_candidate(file_path)


def run_mutation_sample(
    repo_path: Path,
    test_command: CommandSpec | None,
    executor: CommandExecutor,
    max_mutations: int = 8,
    include_paths: list[str] | None = None,
    exclude_paths: list[str] | None = None,
) -> list[MutationResult]:
    if test_command is None or not test_command.command:
        return []

    results: list[MutationResult] = []
    for file_path in _candidate_files(repo_path, include_paths, exclude_paths):
        if len(results) >= max_mutations:
            break
        original_text = file_path.read_text(encoding="utf-8", errors="ignore")
        candidate = _find_mutation(file_path)
        if candidate is None:
            continue
        file_path.write_text(candidate.mutated_text, encoding="utf-8")
        try:
            test_result = executor.run(test_command, repo_path)
            survived = test_result.status == CheckStatus.PASS
            results.append(
                MutationResult(
                    file=str(file_path.relative_to(repo_path)),
                    mutation_type=candidate.mutation_type,
                    original=candidate.original,
                    replacement=candidate.replacement,
                    survived=survived,
                    test_status=test_result.status,
                    message="Mutation survived: tests did not catch the injected bug." if survived else "Mutation killed: tests caught the injected bug.",
                )
            )
        finally:
            file_path.write_text(original_text, encoding="utf-8")
    return results
