from __future__ import annotations

import fnmatch
import io
import json
import re
import tokenize
import tomllib
from pathlib import Path

from .models import SecurityFinding

SECRET_PATTERNS = [
    (
        "generic_api_key",
        re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    ),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private_key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----")),
    (
        "jwt_like_token",
        re.compile(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}"),
    ),
    ("stripe_like_secret", re.compile(r"sk_(live|test)_[A-Za-z0-9]{16,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
]

DESTRUCTIVE_SQL_PATTERNS = [
    ("drop_table", re.compile(r"(?i)\bDROP\s+TABLE\b")),
    ("drop_column", re.compile(r"(?i)\bDROP\s+COLUMN\b")),
    ("truncate", re.compile(r"(?i)\bTRUNCATE\b")),
    ("destructive_alter", re.compile(r"(?i)\bALTER\s+TABLE\b.*\bDROP\b")),
]

AUTH_RISK_PATTERNS = [
    ("hardcoded_admin_true", re.compile(r"(?i)(is_admin|admin)\s*[=:]\s*true")),
    ("auth_bypass_comment", re.compile(r"(?i)(todo|fixme).*(auth|permission|security|admin)")),
    ("debug_mode_true", re.compile(r"(?i)debug\s*[=:]\s*true")),
    ("disable_tls_verify", re.compile(r"(?i)(verify\s*=\s*false|rejectUnauthorized\s*:\s*false)")),
    ("dangerously_set_inner_html", re.compile(r"dangerouslySetInnerHTML")),
]

QUALITY_PATTERNS = [
    ("todo_in_source", re.compile(r"(?i)\b(todo|fixme|hack)\b")),
    ("console_log_leftover", re.compile(r"\bconsole\.log\(")),
]

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".yaml",
    ".yml",
    ".env",
    ".sql",
    ".toml",
    ".md",
    ".env.local",
}
SKIP_DIRS = {
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
    ".pytest_cache",
}
MAX_SCAN_BYTES = 1_500_000


def _matches_excluded_path(relative: str, excluded_paths: list[str] | None) -> bool:
    relative = relative.replace("\\", "/")
    for excluded in excluded_paths or []:
        normalized = excluded.strip().strip("/")
        if not normalized:
            continue
        if fnmatch.fnmatch(relative, normalized) or fnmatch.fnmatch(relative, normalized + "/**"):
            return True
        if relative == normalized or relative.startswith(normalized + "/"):
            return True
    return False


def _should_scan(path: Path, repo_path: Path, excluded_paths: list[str] | None = None) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    relative = path.relative_to(repo_path).as_posix()
    if _matches_excluded_path(relative, excluded_paths):
        return False
    try:
        if path.stat().st_size > MAX_SCAN_BYTES:
            return False
    except OSError:
        return False
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name.startswith(".env")


def _python_string_lines(text: str) -> set[int]:
    lines: set[int] = set()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type == tokenize.STRING:
                lines.update(range(token.start[0], token.end[0] + 1))
    except (tokenize.TokenError, IndentationError):
        return set()
    return lines


def _dependency_bounded(spec: str) -> bool:
    if " @ " in spec or spec.startswith(("git+", "http://", "https://", "file:")):
        return True
    return bool(re.search(r"(?:===|==|~=|!=|<=|>=|<|>)", spec))


def _scan_python_dependencies(repo_path: Path) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    requirements_files = [
        repo_path / "requirements.txt",
        repo_path / "requirements-dev.txt",
        repo_path / "dev-requirements.txt",
    ]
    bounded_requirement_found = False
    for req in requirements_files:
        if not req.exists():
            continue
        for line_no, raw in enumerate(req.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            if _dependency_bounded(line):
                bounded_requirement_found = True
            else:
                findings.append(
                    SecurityFinding(
                        "MEDIUM",
                        req.name,
                        line_no,
                        "unbounded_python_dependency",
                        f"Dependency `{line}` has no version bound.",
                    )
                )

    pyproject = repo_path / "pyproject.toml"
    dependencies: list[str] = []
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError):
            findings.append(
                SecurityFinding("MEDIUM", "pyproject.toml", 1, "invalid_pyproject", "pyproject.toml could not be parsed.")
            )
            data = {}
        project = data.get("project") or {}
        dependencies.extend(str(item) for item in project.get("dependencies") or [])
        for values in (project.get("optional-dependencies") or {}).values():
            dependencies.extend(str(item) for item in values or [])
        for dependency in dependencies:
            if not _dependency_bounded(dependency):
                findings.append(
                    SecurityFinding(
                        "LOW",
                        "pyproject.toml",
                        1,
                        "unbounded_pyproject_dependency",
                        f"Dependency `{dependency}` has no version bound.",
                    )
                )
            if dependency.startswith(("git+", "http://", "https://")) or " @ git+" in dependency:
                findings.append(
                    SecurityFinding(
                        "MEDIUM",
                        "pyproject.toml",
                        1,
                        "remote_python_dependency",
                        f"Dependency `{dependency}` is sourced directly from a remote URL and requires review.",
                    )
                )

    has_python_dependencies = bool(dependencies) or any(path.exists() for path in requirements_files)
    lockfiles = ("uv.lock", "poetry.lock", "Pipfile.lock")
    if has_python_dependencies and not bounded_requirement_found and not any((repo_path / name).exists() for name in lockfiles):
        findings.append(
            SecurityFinding(
                "LOW",
                "pyproject.toml" if pyproject.exists() else "requirements.txt",
                1,
                "missing_python_lockfile",
                "Python dependencies exist without a recognized lockfile. Reproducibility should be reviewed.",
            )
        )
    return findings


def _scan_node_dependencies(repo_path: Path) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    package_json = repo_path / "package.json"
    if not package_json.exists():
        return findings
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [SecurityFinding("MEDIUM", "package.json", 1, "invalid_package_json", "package.json could not be parsed.")]

    deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
    for name, version in deps.items():
        normalized = str(version).strip()
        if normalized in {"*", "latest", "next"}:
            findings.append(
                SecurityFinding(
                    "MEDIUM",
                    "package.json",
                    1,
                    "unpinned_node_dependency",
                    f"Dependency `{name}` uses non-deterministic version `{version}`.",
                )
            )
        if normalized.startswith(("git+", "http://", "https://", "github:")):
            findings.append(
                SecurityFinding(
                    "MEDIUM",
                    "package.json",
                    1,
                    "remote_node_dependency",
                    f"Dependency `{name}` is sourced directly from `{version}` and requires review.",
                )
            )
    if deps and not any((repo_path / lock).exists() for lock in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock")):
        findings.append(
            SecurityFinding(
                "MEDIUM",
                "package.json",
                1,
                "missing_node_lockfile",
                "Node dependencies exist but no supported lockfile was found.",
            )
        )
    scripts = data.get("scripts") or {}
    for script_name, command in scripts.items():
        lowered = str(command).lower()
        if any(token in lowered for token in ("curl ", "wget ", "rm -rf", "sudo ")):
            findings.append(
                SecurityFinding(
                    "HIGH",
                    "package.json",
                    1,
                    "dangerous_package_script",
                    f"Script `{script_name}` contains a dangerous command pattern.",
                )
            )
    return findings


def _scan_dependency_hygiene(repo_path: Path) -> list[SecurityFinding]:
    findings = _scan_node_dependencies(repo_path) + _scan_python_dependencies(repo_path)
    gitignore = repo_path / ".gitignore"
    if not gitignore.exists() or ".env" not in gitignore.read_text(encoding="utf-8", errors="ignore"):
        if any(path.name.startswith(".env") for path in repo_path.glob(".env*")):
            findings.append(
                SecurityFinding(
                    "MEDIUM",
                    ".gitignore",
                    1,
                    "env_not_ignored",
                    ".env files exist but .gitignore does not clearly ignore them.",
                )
            )
    return findings


def _scan_quality(
    path: Path,
    relative: str,
    text: str,
    python_string_lines: set[int] | None = None,
) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    string_lines = python_string_lines or set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        if len(line) > 180:
            findings.append(
                SecurityFinding(
                    "LOW",
                    relative,
                    line_number,
                    "long_line_complexity",
                    "Line is very long and may be hard to maintain.",
                )
            )
        for rule, pattern in QUALITY_PATTERNS:
            if line_number in string_lines:
                continue
            if pattern.search(line) and path.suffix.lower() in {".py", ".js", ".jsx", ".ts", ".tsx"}:
                if rule == "console_log_leftover" and ("test" in relative.lower() or "spec" in relative.lower()):
                    continue
                findings.append(
                    SecurityFinding(
                        "MEDIUM",
                        relative,
                        line_number,
                        rule,
                        "Potential quality or maintainability risk requires review.",
                    )
                )
    return findings


def _scan_workflow_permissions(relative: str, text: str) -> list[SecurityFinding]:
    if not relative.startswith(".github/workflows/"):
        return []
    findings: list[SecurityFinding] = []
    if re.search(r"(?mi)^permissions:\s*write-all\s*$", text):
        findings.append(
            SecurityFinding(
                "HIGH",
                relative,
                1,
                "workflow_write_all",
                "GitHub Actions workflow grants write-all permissions.",
            )
        )
    if "pull_request_target:" in text and "actions/checkout" in text:
        findings.append(
            SecurityFinding(
                "MEDIUM",
                relative,
                1,
                "pull_request_target_checkout",
                "Workflow combines pull_request_target with checkout and requires trust-boundary review.",
            )
        )
    return findings


def scan_repo(
    repo_path: Path,
    block_destructive_migrations: bool = True,
    block_secrets: bool = True,
    excluded_paths: list[str] | None = None,
) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    findings.extend(_scan_dependency_hygiene(repo_path))
    for path in repo_path.rglob("*"):
        if not path.is_file() or not _should_scan(path, repo_path, excluded_paths):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        relative = path.relative_to(repo_path).as_posix()
        string_lines = _python_string_lines(text) if path.suffix.lower() == ".py" else set()
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        SecurityFinding(
                            "HIGH" if block_secrets else "MEDIUM",
                            relative,
                            line_number,
                            rule,
                            "Possible secret detected. Move secrets to environment variables or a secret vault.",
                        )
                    )
            if block_destructive_migrations and path.suffix.lower() == ".sql":
                for rule, pattern in DESTRUCTIVE_SQL_PATTERNS:
                    if pattern.search(line):
                        findings.append(
                            SecurityFinding(
                                "HIGH",
                                relative,
                                line_number,
                                rule,
                                "Destructive SQL migration requires expand-and-contract approval.",
                            )
                        )
            if line_number not in string_lines:
                for rule, pattern in AUTH_RISK_PATTERNS:
                    if pattern.search(line):
                        level = "HIGH" if rule == "dangerously_set_inner_html" else "MEDIUM"
                        findings.append(
                            SecurityFinding(
                                level,
                                relative,
                                line_number,
                                rule,
                                "Possible auth/security risk requires review.",
                            )
                        )
        findings.extend(_scan_quality(path, relative, text, string_lines))
        findings.extend(_scan_workflow_permissions(relative, text))
    return findings
