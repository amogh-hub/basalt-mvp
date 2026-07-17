from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import BasaltConfig, CommandSpec


def _parse_scalar(value: str) -> Any:
    value = value.strip().strip('"').strip("'")
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in {"null", "none", "~"}:
        return None
    if value.isdigit():
        return int(value)
    return value


def _minimal_yaml_parse(text: str) -> dict[str, Any]:
    """Small YAML subset parser so Basalt runs dependency-free.

    Supports top-level sections with nested scalar key/value pairs.
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


def infer_project_type(repo_path: Path) -> str:
    pkg = _package_json(repo_path)
    if pkg:
        deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
        scripts = pkg.get("scripts") or {}
        text = json.dumps({"deps": deps, "scripts": scripts}).lower()
        if "next" in deps or "next" in text:
            return "nextjs"
        if "vite" in deps or "vite" in text:
            return "vite-react"
        if "react" in deps:
            return "react"
        return "node"
    if (repo_path / "main.py").exists() or (repo_path / "app.py").exists():
        combined = "\n".join(p.read_text(encoding="utf-8", errors="ignore")[:5000] for p in repo_path.glob("*.py"))
        if re.search(r"from\s+fastapi\s+import|import\s+fastapi", combined):
            return "fastapi"
    if (repo_path / "pyproject.toml").exists() or (repo_path / "requirements.txt").exists() or list(repo_path.rglob("*.py")):
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


def _infer_node_commands(repo_path: Path) -> dict[str, str | None]:
    pkg = _package_json(repo_path)
    scripts: dict[str, str] = pkg.get("scripts", {}) or {}
    pm = _package_manager(repo_path)
    typecheck = None
    if "typecheck" in scripts:
        typecheck = _run_script(pm, "typecheck")
    elif (repo_path / "tsconfig.json").exists():
        typecheck = "npx tsc --noEmit"
    return {
        "install": f"{pm} install" if pkg else None,
        "build": _run_script(pm, "build") if "build" in scripts else None,
        "lint": _run_script(pm, "lint") if "lint" in scripts else None,
        "typecheck": typecheck,
        "test": f"{pm} test" if "test" in scripts else None,
    }


def _requirements_has(repo_path: Path, token: str) -> bool:
    req = repo_path / "requirements.txt"
    if req.exists() and token.lower() in req.read_text(encoding="utf-8", errors="ignore").lower():
        return True
    pyproject = repo_path / "pyproject.toml"
    return pyproject.exists() and token.lower() in pyproject.read_text(encoding="utf-8", errors="ignore").lower()


def _infer_python_commands(repo_path: Path, project_type: str = "python") -> dict[str, str | None]:
    has_tests = (repo_path / "tests").exists()
    use_pytest = _requirements_has(repo_path, "pytest") or (repo_path / "pytest.ini").exists()
    test_command = "python -m pytest" if use_pytest and has_tests else ("python -m unittest discover -s tests" if has_tests else None)
    typecheck = "python -m mypy ." if _requirements_has(repo_path, "mypy") else None
    return {
        "install": "python -m pip install -r requirements.txt" if (repo_path / "requirements.txt").exists() else None,
        "build": None,
        "lint": "python -m compileall .",
        "typecheck": typecheck,
        "test": test_command,
    }


def infer_commands(repo_path: Path, project_type: str) -> dict[str, str | None]:
    if project_type in {"node", "react", "vite-react", "nextjs"}:
        return _infer_node_commands(repo_path)
    if project_type in {"python", "fastapi"}:
        return _infer_python_commands(repo_path, project_type)
    return {"install": None, "build": None, "lint": None, "typecheck": None, "test": None}


def _command_spec(name: str, command: str | None, required: bool, timeout: int = 300) -> CommandSpec:
    return CommandSpec(name=name, command=command, required=required, timeout_seconds=timeout)


def _csv_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


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
    merged_commands = {**inferred, **{k: v for k, v in commands_raw.items() if v not in ("", None)}}

    require_build_default = bool(merged_commands.get("build")) and project_type in {"node", "react", "vite-react", "nextjs"}
    require_type_default = bool(merged_commands.get("typecheck")) and project_type in {"react", "vite-react", "nextjs"}
    specs = [
        _command_spec("install", merged_commands.get("install"), required=False, timeout=900),
        _command_spec("build", merged_commands.get("build"), required=bool(proof.get("require_build", require_build_default)), timeout=600),
        _command_spec("lint", merged_commands.get("lint"), required=bool(proof.get("require_lint", False)), timeout=300),
        _command_spec("typecheck", merged_commands.get("typecheck"), required=bool(proof.get("require_typecheck", require_type_default)), timeout=400),
        _command_spec("test", merged_commands.get("test"), required=bool(proof.get("require_tests", True)), timeout=600),
    ]

    return BasaltConfig(
        project_name=project_name,
        project_type=project_type,
        commands=specs,
        mutation_sample=bool(proof.get("mutation_sample", True)),
        mutation_max=int(proof.get("mutation_max", 8)),
        mutation_include=_csv_list(proof.get("mutation_include")),
        mutation_exclude=_csv_list(proof.get("mutation_exclude")),
        security_scan=str(proof.get("security_scan", "basic")),
        scan_exclude=_csv_list(proof.get("scan_exclude")),
        max_test_failures=int(proof.get("max_test_failures", 0)),
        block_secrets=bool(policy.get("block_secrets", True)),
        block_destructive_migrations=bool(policy.get("block_destructive_migrations", True)),
        require_human_approval_for_deploy=bool(policy.get("require_human_approval_for_deploy", True)),
        generate_dashboard=bool(proof.get("dashboard", True)),
        generate_patch_plan=bool(proof.get("patch_plan", True)),
        generate_pr_pack=bool(proof.get("pr_pack", True)),
        sandbox=str(sandbox.get("mode") or "temp"),
        docker_image=str(sandbox.get("docker_image")) if sandbox.get("docker_image") else None,
    )


def render_default_config(project_name: str = "my-app", project_type: str = "python") -> str:
    if project_type in {"node", "react", "vite-react", "nextjs"}:
        commands = """  install: npm install\n  build: npm run build\n  lint: npm run lint\n  typecheck: npx tsc --noEmit\n  test: npm test"""
        require_build = "true"
        require_typecheck = "false"
    else:
        commands = """  install: null\n  build: null\n  lint: python -m compileall .\n  typecheck: null\n  test: python -m unittest discover -s tests"""
        require_build = "false"
        require_typecheck = "false"
    return f"""project:\n  name: {project_name}\n  type: {project_type}\ncommands:\n{commands}\nproof:\n  require_build: {require_build}\n  require_lint: false\n  require_typecheck: {require_typecheck}\n  require_tests: true\n  mutation_sample: true\n  mutation_max: 8\n  security_scan: basic\n  dashboard: true\n  patch_plan: true\n  pr_pack: true\npolicy:\n  block_secrets: true\n  block_destructive_migrations: true\n  require_human_approval_for_deploy: true\nsandbox:\n  mode: temp\n  docker_image: null\n"""
