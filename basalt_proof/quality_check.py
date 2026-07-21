from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

EXCLUDED = {'.git', '.basalt', '.basalt-deps', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache', 'dist', 'build', '.next'}
TEXT_SUFFIXES = {'.py', '.json', '.toml', '.yaml', '.yml', '.js', '.jsx', '.ts', '.tsx', '.css', '.html', '.md'}


@dataclass(frozen=True)
class Finding:
    level: str
    path: str
    line: int
    code: str
    message: str


def _iter_files(roots: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for root in roots:
        if root.is_file():
            files.add(root)
            continue
        if not root.exists():
            continue
        for path in root.rglob('*'):
            if not path.is_file() or path.is_symlink():
                continue
            if any(part in EXCLUDED or part.endswith('.egg-info') for part in path.parts):
                continue
            if path.suffix.lower() in TEXT_SUFFIXES:
                files.add(path)
    return sorted(files, key=lambda item: item.as_posix())


def inspect_file(path: Path, max_line_length: int = 140) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        return [Finding('ERROR', path.as_posix(), 1, 'READ_ERROR', str(exc))]

    if path.suffix == '.py':
        try:
            ast.parse(text, filename=path.as_posix())
        except SyntaxError as exc:
            findings.append(Finding('ERROR', path.as_posix(), exc.lineno or 1, 'PY_SYNTAX', exc.msg))
    elif path.suffix == '.json':
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            findings.append(Finding('ERROR', path.as_posix(), exc.lineno, 'JSON_PARSE', exc.msg))
    elif path.suffix == '.toml':
        try:
            import tomllib
            tomllib.loads(text)
        except Exception as exc:  # TOMLDecodeError is runtime-specific
            findings.append(Finding('ERROR', path.as_posix(), 1, 'TOML_PARSE', str(exc)))

    for number, line in enumerate(text.splitlines(), 1):
        if line.rstrip(' \t') != line:
            findings.append(Finding('WARNING', path.as_posix(), number, 'TRAILING_WS', 'Trailing whitespace.'))
        if '\t' in line[: len(line) - len(line.lstrip())]:
            findings.append(Finding('WARNING', path.as_posix(), number, 'TAB_INDENT', 'Tab indentation detected.'))
        if len(line) > max_line_length:
            findings.append(Finding('INFO', path.as_posix(), number, 'LONG_LINE', f'Line is {len(line)} characters; recommended maximum is {max_line_length}.'))
    return findings


def run(paths: list[str], max_line_length: int = 140) -> int:
    roots = [Path(item).expanduser().resolve() for item in paths]
    files = _iter_files(roots)
    findings = [finding for path in files for finding in inspect_file(path, max_line_length)]
    errors = [item for item in findings if item.level == 'ERROR']
    warnings = [item for item in findings if item.level == 'WARNING']
    infos = [item for item in findings if item.level == 'INFO']
    for item in findings[:250]:
        print(f'{item.level} {item.path}:{item.line} {item.code} {item.message}')
    if len(findings) > 250:
        print(f'INFO quality-check TRUNCATED {len(findings) - 250} additional findings omitted from console output.')
    print(f'QUALITY_CHECK files={len(files)} errors={len(errors)} warnings={len(warnings)} info={len(infos)}')
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Basalt dependency-free static quality check.')
    parser.add_argument('paths', nargs='*', default=['.'])
    parser.add_argument('--max-line-length', type=int, default=140)
    args = parser.parse_args(argv)
    return run(args.paths, max(40, args.max_line_length))


if __name__ == '__main__':
    raise SystemExit(main())
