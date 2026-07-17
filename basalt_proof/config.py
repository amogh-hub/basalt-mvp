from __future__ import annotations

import ast
import json
import re
import tomllib
from pathlib import Path
from typing import Any

from .models import BasaltConfig, CommandSpec

NODE_TYPES = {"node", "react", "vite-react", "nextjs"}
PYTHON_TYPES = {"python", "fastapi"}


def _parse_scalar(value: str) -> Any:
    value = value.strip().strip('"').strip("'")
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in {"null", "none", "~"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def _minimal_yaml_parse(text: str) -> dict[str, Any]:
    """Parse Basalt's dependency-free YAML subset.

    The alpha config deliberately supports top-level sections and nested scalar
    values. Lists are represented as comma-separated strings so the CLI stays
    dependency-free.
    """
    result: dict[str, Any] = {}
    current_section: str | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        line = raw_line.rstrip()
        if not line.startswith((" ", "\t")) and line.endswith(":"):
            current_section = line[:-1].strip()
            result[current_section] = {}
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        parsed_value = _parse_scalar(value)
        if raw_line.startswith((" ", "\t")) and current_section:
            result.setdefault(current_section, {})[key] = parsed_value
        else:
            result[key] = parsed_value
            current_section = None
    return result


def load_raw_config(repo_path: Path) -> dict[str, Any]:
    for name in ("basalt.yaml", "basalt.yml"):
        path = repo_path / name
        if path.exists():
            return _minimal_yaml_parse(path.read_text(encoding="utf-8"))
    json_path = repo_path / "basalt.json"
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))
    return {}


def _package_json(repo_path: Path) -> dict[str, Any]:
    path = repo_path / "package.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_pyproject(repo_path: Path) -> dict[str, Any]:
    path = repo_path / "pyproject.toml"
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return {}


def infer_project_type(repo_path: Path) -> str:
    pkg = _package_json(repo_path)
    if pkg:
        deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
        scripts = pkg.get("scripts") or {}
        text = json.dumps({"deps": deps, "scripts": scripts}).lower()
        if "next" in deps or re.search(r"\bnext\b", text):
            return "nextjs"
        if "vite" in deps or re.search(r"\bvite\b", text):
            return "vite-react" if "react" in deps else "node"
        if "react" in deps:
            return "react"
        return "node"

    python_files = list(repo_path.rglob("*.py"))
    if python_files:
        for path in python_files[:80]:
            if any(part in {".venv", "venv", ".git", "node_modules", "tests", "test"} for part in path.parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except (SyntaxError, OSError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import) and any(alias.name == "fastapi" for alias in node.names):
                    return "fastapi"
                if isinstance(node, ast.ImportFrom) and node.module == "fastapi":
                    return "fastapi"
        return "python"

    if (repo_path / "pyproject.toml").exists() or (repo_path / "requirements.txt").exists():
        return "python"
    return "unknown"


def _package_manager(repo_path: Path) -> str:
    if (repo_path / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (repo_path / "yarn.lock").exists():
        return "yarn"
    return "npm"


def _run_script(package_manager: str, script: str) -> str:
    if package_manager == "yarn":
        return f"yarn {script}"
    return f"{package_manager} run {script}"


def _node_install_command(repo_path: Path, package_manager: str) -> str | None:
    if not (repo_path / "package.json").exists():
        return None
    if package_manager == "pnpm":
        return "pnpm install --frozen-lockfile" if (repo_path / "pnpm-lock.yaml").exists() else "pnpm install"
    if package_manager == "yarn":
        return "yarn install --frozen-lockfile" if (repo_path / "yarn.lock").exists() else "yarn install"
    return "npm ci" if (repo_path / "package-lock.json").exists() else "npm install"


def _infer_node_commands(repo_path: Path) -> dict[str, str | None]:
    pkg = _package_json(repo_path)
    scripts: dict[str, str] = pkg.get("scripts", {}) or {}
    pm = _package_manager(repo_path)
    typecheck = None
    if "typecheck" in scripts:
        typecheck = _run_script(pm, "typecheck")
    elif (repo_path / "tsconfig.json").exists():
        typecheck = "npx tsc --noEmit"
    test = None
    for candidate in ("test:ci", "test", "check"):
        if candidate in scripts:
            test = _run_script(pm, candidate)
            break
    return {
        "install": _node_install_command(repo_path, pm),
        "build": _run_script(pm, "build") if "build" in scripts else None,
        "lint": _run_script(pm, "lint") if "lint" in scripts else None,
        "typecheck": typecheck,
        "test": test,
    }


def _requirements_has(repo_path: Path, token: str) -> bool:
    token = token.lower()
    for filename in ("requirements.txt", "requirements-dev.txt", "dev-requirements.txt"):
        path = repo_path / filename
        if path.exists() and token in path.read_text(encoding="utf-8", errors="ignore").lower():
            return True
    pyproject = repo_path / "pyproject.toml"
    return pyproject.exists() and token in pyproject.read_text(encoding="utf-8", errors="ignore").lower()


def _python_install_command(repo_path: Path) -> str | None:
    if (repo_path / "requirements.txt").exists():
        return "python -m pip install --target .basalt-deps -r requirements.txt"
    if (repo_path / "pyproject.toml").exists():
        project = _read_pyproject(repo_path).get("project", {})
        has_dependencies = bool(project.get("dependencies"))
        suffix = "" if has_dependencies else " --no-deps --no-build-isolation"
        return f"python -m pip install --target .basalt-deps .{suffix}"
    return None


def _infer_python_commands(repo_path: Path) -> dict[str, str | None]:
    has_tests = (repo_path / "tests").exists()
    use_pytest = _requirements_has(repo_path, "pytest") or (repo_path / "pytest.ini").exists()
    test_command = None
    if has_tests:
        test_command = "python -m pytest -q" if use_pytest else "python -m unittest discover -s tests -v"
    lint = "ruff check ." if _requirements_has(repo_path, "ruff") else "python -m compileall ."
    typecheck = "python -m mypy ." if _requirements_has(repo_path, "mypy") else None
    return {
        "install": _python_install_command(repo_path),
        "build": None,
        "lint": lint,
        "typecheck": typecheck,
        "test": test_command,
    }


def infer_commands(repo_path: Path, project_type: str) -> dict[str, str | None]:
    if project_type in NODE_TYPES:
        return _infer_node_commands(repo_path)
    if project_type in PYTHON_TYPES:
        return _infer_python_commands(repo_path)
    return {"install": None, "build": None, "lint": None, "typecheck": None, "test": None}


def _command_spec(
    name: str,
    command: str | None,
    required: bool,
    timeout: int = 300,
    allow_network: bool = False,
) -> CommandSpec:
    return CommandSpec(
        name=name,
        command=command,
        required=required,
        timeout_seconds=timeout,
        allow_network=allow_network,
    )


def _csv_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _default_docker_image(project_type: str) -> str:
    if project_type in NODE_TYPES:
        return "node:22-bookworm-slim"
    return "python:3.13-slim"


def load_config(repo_path: Path) -> BasaltConfig:
    raw = load_raw_config(repo_path)
    project = raw.get("project", {}) if isinstance(raw.get("project", {}), dict) else {}
    commands_raw = raw.get("commands", {}) if isinstance(raw.get("commands", {}), dict) else {}
    proof = raw.get("proof", {}) if isinstance(raw.get("proof", {}), dict) else {}
    policy = raw.get("policy", {}) if isinstance(raw.get("policy", {}), dict) else {}
    sandbox = raw.get("sandbox", {}) if isinstance(raw.get("sandbox", {}), dict) else {}

    project_name = str(project.get("name") or repo_path.name)
    project_type = str(project.get("type") or infer_project_type(repo_path))
    inferred = infer_commands(repo_path, project_type)
    merged_commands = {**inferred}
    for key, value in commands_raw.items():
        merged_commands[key] = None if value in ("", None) else value

    require_build_default = bool(merged_commands.get("build")) and project_type in NODE_TYPES
    require_type_default = bool(merged_commands.get("typecheck")) and project_type in {"react", "vite-react", "nextjs"}
    network_mode = str(sandbox.get("network") or "install-only")
    install_network = network_mode in {"install-only", "full"}
    specs = [
        _command_spec("install", merged_commands.get("install"), required=False, timeout=900, allow_network=install_network),
        _command_spec(
            "build",
            merged_commands.get("build"),
            required=bool(proof.get("require_build", require_build_default)),
            timeout=600,
        ),
        _command_spec(
            "lint",
            merged_commands.get("lint"),
            required=bool(proof.get("require_lint", False)),
            timeout=300,
        ),
        _command_spec(
            "typecheck",
            merged_commands.get("typecheck"),
            required=bool(proof.get("require_typecheck", require_type_default)),
            timeout=400,
        ),
        _command_spec(
            "test",
            merged_commands.get("test"),
            required=bool(proof.get("require_tests", True)),
            timeout=600,
        ),
    ]

    docker_image = str(sandbox.get("docker_image") or _default_docker_image(project_type))
    return BasaltConfig(
        project_name=project_name,
        project_type=project_type,
        commands=specs,
        mutation_sample=bool(proof.get("mutation_sample", True)),
        mutation_max=max(0, int(proof.get("mutation_max", 8))),
        mutation_per_file=max(1, int(proof.get("mutation_per_file", 2))),
        mutation_include=_csv_list(proof.get("mutation_include")),
        mutation_exclude=_csv_list(proof.get("mutation_exclude")),
        security_scan=str(proof.get("security_scan", "basic")),
        scan_exclude=_csv_list(proof.get("scan_exclude")),
        max_test_failures=int(proof.get("max_test_failures", 0)),
        min_verified_score=max(0, min(100, int(proof.get("min_verified_score", 80)))),
        block_secrets=bool(policy.get("block_secrets", True)),
        block_destructive_migrations=bool(policy.get("block_destructive_migrations", True)),
        require_human_approval_for_deploy=bool(policy.get("require_human_approval_for_deploy", True)),
        generate_dashboard=bool(proof.get("dashboard", True)),
        generate_patch_plan=bool(proof.get("patch_plan", True)),
        generate_pr_pack=bool(proof.get("pr_pack", True)),
        sandbox=str(sandbox.get("mode") or "auto"),
        docker_image=docker_image,
        docker_network=network_mode,
        docker_fallback=bool(sandbox.get("fallback_to_temp", True)),
    )


def render_default_config(project_name: str = "my-app", project_type: str = "python") -> str:
    if project_type in NODE_TYPES:
        commands = (
            "  install: npm install\n"
            "  build: npm run build\n"
            "  lint: npm run lint\n"
            "  typecheck: npx tsc --noEmit\n"
            "  test: npm test"
        )
        require_build = "true"
        require_typecheck = "true" if project_type in {"react", "vite-react", "nextjs"} else "false"
    else:
        commands = (
            "  install: null\n"
            "  build: null\n"
            "  lint: python -m compileall .\n"
            "  typecheck: null\n"
            "  test: python -m unittest discover -s tests -v"
        )
        require_build = "false"
        require_typecheck = "false"
    return f"""project:\n  name: {project_name}\n  type: {project_type}\ncommands:\n{commands}\nproof:\n  require_build: {require_build}\n  require_lint: true\n  require_typecheck: {require_typecheck}\n  require_tests: true\n  mutation_sample: true\n  mutation_max: 8\n  mutation_per_file: 2\n  mutation_include: null\n  mutation_exclude: examples,dist,build\n  security_scan: basic\n  scan_exclude: examples/demo_policy_violation,fixtures\n  min_verified_score: 80\n  dashboard: true\n  patch_plan: true\n  pr_pack: true\npolicy:\n  block_secrets: true\n  block_destructive_migrations: true\n  require_human_approval_for_deploy: true\nsandbox:\n  mode: auto\n  docker_image: null\n  network: install-only\n  fallback_to_temp: true\n"""
