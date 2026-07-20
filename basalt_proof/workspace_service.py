from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .config import infer_commands, infer_project_type, load_config

MAX_TEXT_BYTES = 1_000_000
MAX_TREE_ITEMS = 5000
EXCLUDED_PARTS = {'.git', '.basalt', '.venv', 'venv', 'node_modules', '__pycache__'}
TEXT_SUFFIXES = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.json', '.md', '.txt', '.toml', '.yaml', '.yml',
    '.html', '.css', '.scss', '.sql', '.sh', '.env.example', '.gitignore', '.dockerignore'
}


def _is_excluded_part(part: str) -> bool:
    return part in EXCLUDED_PARTS or part.endswith('.egg-info')


class WorkspaceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {'Dockerfile', 'Makefile', 'LICENSE'}


def _language(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        '.py': 'python', '.js': 'javascript', '.jsx': 'javascript', '.ts': 'typescript', '.tsx': 'typescript',
        '.json': 'json', '.md': 'markdown', '.toml': 'toml', '.yaml': 'yaml', '.yml': 'yaml',
        '.html': 'html', '.css': 'css', '.scss': 'scss', '.sql': 'sql', '.sh': 'shell',
    }.get(suffix, 'plaintext')


@dataclass(frozen=True)
class WorkspaceEvent:
    event: str
    path: str
    actor: str
    detail: str
    created_at: str


class BuildWorkspaceService:
    """Safe local Build Workspace over a single registered repository.

    The service deliberately avoids arbitrary shell execution. It exposes only
    repository-scoped file operations and configured/inferred proof commands.
    """

    def __init__(self, repo: Path, state_root: Path | None = None) -> None:
        self.repo = repo.expanduser().resolve()
        if not self.repo.exists() or not self.repo.is_dir():
            raise WorkspaceError(f'Repository does not exist: {self.repo}')
        self.state_root = (state_root or self.repo / '.basalt' / 'workspace').resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.events_path = self.state_root / 'events.jsonl'

    def _resolve(self, relative: str, *, must_exist: bool = True) -> Path:
        cleaned = str(relative or '').strip().replace('\\', '/')
        if cleaned in {'', '.'}:
            candidate = self.repo
        else:
            if cleaned.startswith('/') or re.match(r'^[A-Za-z]:', cleaned):
                raise WorkspaceError('Absolute paths are not allowed.')
            candidate = (self.repo / cleaned).resolve()
        if candidate != self.repo and self.repo not in candidate.parents:
            raise WorkspaceError('Path escapes the repository boundary.')
        relative_parts = candidate.relative_to(self.repo).parts if candidate != self.repo else ()
        if any(_is_excluded_part(part) for part in relative_parts):
            raise WorkspaceError('Path is inside a protected workspace directory.')
        if must_exist and not candidate.exists():
            raise FileNotFoundError(str(candidate))
        return candidate

    def _record(self, event: str, path: str, actor: str = '', detail: str = '') -> None:
        item = WorkspaceEvent(event, path, actor[:200], detail[:1000], _now())
        with self.events_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(asdict(item), sort_keys=True) + '\n')

    def snapshot(self) -> dict[str, Any]:
        project_type = infer_project_type(self.repo)
        config = load_config(self.repo)
        inferred = infer_commands(self.repo, project_type)
        commands: dict[str, str | None] = {}
        for name in ('install', 'build', 'lint', 'typecheck', 'test'):
            spec = getattr(config, name, None)
            commands[name] = getattr(spec, 'command', None) or inferred.get(name)
        return {
            'product': 'Basalt v3 Production Workspace',
            'version': __version__,
            'phase': 7,
            'repo': str(self.repo),
            'name': config.project_name or self.repo.name,
            'project_type': project_type,
            'commands': commands,
            'capabilities': {
                'file_explorer': True,
                'multi_file_tabs': True,
                'editor': True,
                'line_numbers': True,
                'syntax_highlighting': True,
                'optimistic_saves': True,
                'diff_before_save': True,
                'diagnostics': True,
                'configured_terminal': True,
                'proof_console': True,
                'activity_timeline': True,
                'git_visibility': True,
                'command_palette': True,
                'resizable_layout': True,
                'live_preview': False,
                'arbitrary_shell': False,
            },
        }

    def tree(self, path: str = '', depth: int = 4) -> dict[str, Any]:
        if depth < 0 or depth > 8:
            raise WorkspaceError('Tree depth must be between 0 and 8.')
        root = self._resolve(path)
        if not root.is_dir():
            raise WorkspaceError('Tree target must be a directory.')
        count = 0

        def walk(directory: Path, remaining: int) -> list[dict[str, Any]]:
            nonlocal count
            items: list[dict[str, Any]] = []
            if remaining < 0:
                return items
            for child in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if _is_excluded_part(child.name) or child.is_symlink():
                    continue
                count += 1
                if count > MAX_TREE_ITEMS:
                    break
                rel = child.relative_to(self.repo).as_posix()
                item: dict[str, Any] = {
                    'name': child.name,
                    'path': rel,
                    'kind': 'directory' if child.is_dir() else 'file',
                }
                if child.is_file():
                    item['size_bytes'] = child.stat().st_size
                    item['language'] = _language(child)
                elif remaining > 0:
                    item['children'] = walk(child, remaining - 1)
                items.append(item)
            return items

        return {'path': root.relative_to(self.repo).as_posix() if root != self.repo else '', 'items': walk(root, depth)}

    def read_file(self, path: str) -> dict[str, Any]:
        target = self._resolve(path)
        if not target.is_file():
            raise WorkspaceError('Target is not a file.')
        size = target.stat().st_size
        if size > MAX_TEXT_BYTES:
            raise WorkspaceError('File is too large for inline editing.')
        if not _is_text_file(target):
            raise WorkspaceError('Binary or unsupported file type.')
        raw = target.read_bytes()
        try:
            content = raw.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise WorkspaceError('File is not valid UTF-8 text.') from exc
        return {
            'path': target.relative_to(self.repo).as_posix(),
            'content': content,
            'sha256': _sha256_bytes(raw),
            'size_bytes': len(raw),
            'modified_ns': target.stat().st_mtime_ns,
            'language': _language(target),
            'line_count': max(1, len(content.splitlines()) or 1),
        }

    def diff_file(self, path: str, content: str, expected_sha256: str = '') -> dict[str, Any]:
        target = self._resolve(path)
        if not target.is_file():
            raise WorkspaceError('Target is not a file.')
        current_raw = target.read_bytes()
        try:
            current = current_raw.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise WorkspaceError('File is not valid UTF-8 text.') from exc
        proposed_raw = content.encode('utf-8')
        if len(proposed_raw) > MAX_TEXT_BYTES:
            raise WorkspaceError('File is too large for inline editing.')
        current_hash = _sha256_bytes(current_raw)
        proposed_hash = _sha256_bytes(proposed_raw)
        conflict = bool(expected_sha256 and expected_sha256 != current_hash)
        rel = target.relative_to(self.repo).as_posix()
        lines = list(difflib.unified_diff(
            current.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f'a/{rel}',
            tofile=f'b/{rel}',
            n=3,
        ))
        additions = sum(1 for line in lines if line.startswith('+') and not line.startswith('+++'))
        deletions = sum(1 for line in lines if line.startswith('-') and not line.startswith('---'))
        return {
            'path': rel,
            'changed': current_hash != proposed_hash,
            'conflict': conflict,
            'expected_sha256': expected_sha256,
            'current_sha256': current_hash,
            'proposed_sha256': proposed_hash,
            'additions': additions,
            'deletions': deletions,
            'unified_diff': ''.join(lines) or 'No changes.\n',
        }

    def diagnostics(self, path: str, content: str) -> dict[str, Any]:
        target = self._resolve(path)
        language = _language(target)
        items: list[dict[str, Any]] = []

        def add(severity: str, message: str, line: int = 1, column: int = 1, code: str = '') -> None:
            items.append({
                'severity': severity,
                'message': message[:500],
                'line': max(1, int(line or 1)),
                'column': max(1, int(column or 1)),
                'code': code,
            })

        if language == 'python':
            try:
                ast.parse(content, filename=target.name)
            except SyntaxError as exc:
                add('ERROR', exc.msg, exc.lineno or 1, exc.offset or 1, 'PY_SYNTAX')
        elif language == 'json':
            try:
                json.loads(content)
            except json.JSONDecodeError as exc:
                add('ERROR', exc.msg, exc.lineno, exc.colno, 'JSON_PARSE')
        elif language == 'toml':
            try:
                import tomllib
            except ModuleNotFoundError:
                tomllib = None  # type: ignore[assignment]
            if tomllib is not None:
                try:
                    tomllib.loads(content)
                except Exception as exc:  # TOMLDecodeError is runtime-specific
                    add('ERROR', str(exc), 1, 1, 'TOML_PARSE')

        for number, line in enumerate(content.splitlines(), 1):
            if len(items) >= 100:
                break
            if line.rstrip(' \t') != line:
                add('WARNING', 'Trailing whitespace.', number, len(line.rstrip(' \t')) + 1, 'TRAILING_WS')
            if len(line) > 140:
                add('WARNING', f'Line is {len(line)} characters; recommended maximum is 140.', number, 141, 'LONG_LINE')

        error_count = sum(1 for item in items if item['severity'] == 'ERROR')
        warning_count = sum(1 for item in items if item['severity'] == 'WARNING')
        return {
            'path': target.relative_to(self.repo).as_posix(),
            'language': language,
            'status': 'ERROR' if error_count else ('WARNING' if warning_count else 'CLEAN'),
            'errors': error_count,
            'warnings': warning_count,
            'items': items,
        }

    def save_file(self, path: str, content: str, expected_sha256: str, actor: str = '') -> dict[str, Any]:
        target = self._resolve(path)
        if not target.is_file():
            raise WorkspaceError('Target is not a file.')
        current = target.read_bytes()
        current_hash = _sha256_bytes(current)
        if not expected_sha256 or current_hash != expected_sha256:
            raise WorkspaceError('File changed since it was opened. Reload before saving.')
        encoded = content.encode('utf-8')
        if len(encoded) > MAX_TEXT_BYTES:
            raise WorkspaceError('File is too large for inline editing.')
        temp = target.with_name(f'.{target.name}.basalt-tmp')
        temp.write_bytes(encoded)
        os.replace(temp, target)
        new_hash = _sha256_bytes(encoded)
        self._record('FILE_SAVED', target.relative_to(self.repo).as_posix(), actor, f'{current_hash[:12]}->{new_hash[:12]}')
        return self.read_file(path)

    def create_file(self, path: str, content: str = '', actor: str = '') -> dict[str, Any]:
        target = self._resolve(path, must_exist=False)
        if target.exists():
            raise WorkspaceError('Target already exists.')
        if target.parent != self.repo and self.repo not in target.parent.parents:
            raise WorkspaceError('Invalid target parent.')
        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode('utf-8')
        if len(encoded) > MAX_TEXT_BYTES:
            raise WorkspaceError('File is too large.')
        target.write_bytes(encoded)
        self._record('FILE_CREATED', target.relative_to(self.repo).as_posix(), actor)
        return self.read_file(target.relative_to(self.repo).as_posix())

    def search(self, query: str, limit: int = 100) -> dict[str, Any]:
        term = query.strip()
        if len(term) < 2:
            raise WorkspaceError('Search query must contain at least two characters.')
        safe_limit = max(1, min(int(limit), 250))
        lowered = term.lower()
        results: list[dict[str, Any]] = []
        for path in sorted(self.repo.rglob('*')):
            if len(results) >= safe_limit:
                break
            if not path.is_file() or path.is_symlink() or any(_is_excluded_part(part) for part in path.relative_to(self.repo).parts):
                continue
            rel = path.relative_to(self.repo).as_posix()
            if lowered in rel.lower():
                results.append({'path': rel, 'line': 0, 'preview': 'Filename match', 'language': _language(path)})
                if len(results) >= safe_limit:
                    break
            if path.stat().st_size > MAX_TEXT_BYTES or not _is_text_file(path):
                continue
            try:
                for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                    if lowered in line.lower():
                        results.append({
                            'path': rel,
                            'line': number,
                            'preview': line.strip()[:240],
                            'language': _language(path),
                        })
                        if len(results) >= safe_limit:
                            break
            except (OSError, UnicodeDecodeError):
                continue
        return {'query': term, 'count': len(results), 'items': results}

    def git_status(self) -> dict[str, Any]:
        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ['git', *args],
                cwd=self.repo,
                text=True,
                capture_output=True,
                timeout=10,
                env={k: v for k, v in os.environ.items() if k in {'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL'}},
            )

        try:
            root = run('rev-parse', '--show-toplevel')
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {'available': False, 'reason': 'Git is not available in this environment.', 'items': []}
        if root.returncode != 0:
            return {'available': False, 'reason': 'This workspace is not inside a Git repository.', 'items': []}

        branch_result = run('branch', '--show-current')
        commit_result = run('rev-parse', '--short=12', 'HEAD')
        status_result = run('status', '--porcelain=v1', '--branch')
        branch = branch_result.stdout.strip() or 'detached'
        commit = commit_result.stdout.strip() if commit_result.returncode == 0 else ''
        items: list[dict[str, str]] = []
        ahead = behind = 0
        for index, line in enumerate(status_result.stdout.splitlines()):
            if index == 0 and line.startswith('##'):
                ahead_match = re.search(r'ahead (\d+)', line)
                behind_match = re.search(r'behind (\d+)', line)
                ahead = int(ahead_match.group(1)) if ahead_match else 0
                behind = int(behind_match.group(1)) if behind_match else 0
                continue
            if len(line) < 3:
                continue
            items.append({'status': line[:2], 'path': line[3:].strip()})
        return {
            'available': True,
            'root': root.stdout.strip(),
            'branch': branch,
            'commit': commit,
            'dirty': bool(items),
            'ahead': ahead,
            'behind': behind,
            'items': items[:250],
        }

    def run_command(self, name: str, timeout_seconds: int = 300) -> dict[str, Any]:
        selected = name.strip().lower()
        if selected not in {'install', 'build', 'lint', 'typecheck', 'test'}:
            raise WorkspaceError('Only configured install/build/lint/typecheck/test commands are allowed.')
        config = load_config(self.repo)
        project_type = infer_project_type(self.repo)
        inferred = infer_commands(self.repo, project_type)
        spec = getattr(config, selected, None)
        command = getattr(spec, 'command', None) or inferred.get(selected)
        if not command:
            raise WorkspaceError(f'No {selected} command is configured or inferred.')
        timeout = max(1, min(int(timeout_seconds), 900))
        started = datetime.now(timezone.utc)
        try:
            completed = subprocess.run(
                command,
                cwd=self.repo,
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout,
                env={k: v for k, v in os.environ.items() if k in {'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL'}},
            )
            status = 'PASS' if completed.returncode == 0 else 'FAIL'
            returncode = completed.returncode
            stdout = completed.stdout[-40000:]
            stderr = completed.stderr[-40000:]
        except subprocess.TimeoutExpired as exc:
            status = 'TIMEOUT'
            returncode = None
            stdout = (exc.stdout or '')[-40000:] if isinstance(exc.stdout, str) else ''
            stderr = (exc.stderr or '')[-40000:] if isinstance(exc.stderr, str) else ''
        duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        result = {
            'name': selected,
            'command': command,
            'status': status,
            'exit_code': returncode,
            'duration_ms': duration_ms,
            'stdout': stdout,
            'stderr': stderr,
            'created_at': _now(),
        }
        output = self.state_root / f'command-{selected}.json'
        output.write_text(json.dumps(result, indent=2), encoding='utf-8')
        self._record('COMMAND_RUN', selected, '', f'{status} {duration_ms}ms')
        return result

    def events(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        rows = []
        for line in self.events_path.read_text(encoding='utf-8').splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows[-max(1, min(int(limit), 500)):]
