from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .models import CheckStatus, CommandResult, CommandSpec

SAFE_COMMAND_PREFIXES = (
    "npm ",
    "npm",
    "pnpm ",
    "pnpm",
    "yarn ",
    "yarn",
    "python ",
    "python",
    "python3 ",
    "python3",
    "pytest ",
    "pytest",
    "pip ",
    "pip",
    "pip3 ",
    "pip3",
    "uv ",
    "uv",
    "ruff ",
    "ruff",
    "mypy ",
    "mypy",
    "pyright ",
    "pyright",
    "npx ",
    "npx",
    "node ",
    "node",
    "tsc ",
    "tsc",
    "coverage ",
    "coverage",
    "tox ",
    "tox",
)
DANGEROUS_TOKENS = (
    "rm -rf /",
    "sudo ",
    "curl ",
    "wget ",
    "scp ",
    "ssh ",
    "chmod 777",
    "mkfs",
    ":(){",
    "> /dev/sd",
    "dd if=",
    "shutdown",
    "reboot",
    "docker run",
    "osascript",
    "open ",
    "nc ",
    "netcat",
    "python -c",
    "python3 -c",
    "eval ",
)


def _tail(text: str | bytes | None, limit: int = 5000) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    if len(text) <= limit:
        return text
    return text[-limit:]


def is_command_allowed(command: str) -> tuple[bool, str]:
    normalized = command.strip()
    if not normalized:
        return False, "Empty command."
    lowered = normalized.lower()
    for token in DANGEROUS_TOKENS:
        if token in lowered:
            return False, f"Command contains dangerous token blocked by Policy Kernel: {token}"
    if any(normalized.startswith(prefix) for prefix in SAFE_COMMAND_PREFIXES):
        return True, "allowed"
    return (
        False,
        "Command blocked by the Basalt allowlist. Use supported Python or Node package/test/build commands.",
    )


def docker_status(timeout_seconds: int = 8) -> tuple[bool, str]:
    if shutil.which("docker") is None:
        return False, "Docker CLI was not found."
    try:
        completed = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Docker daemon check failed: {exc}"
    if completed.returncode != 0:
        reason = _tail(completed.stderr or completed.stdout, 500).strip()
        return False, reason or "Docker daemon is unavailable."
    return True, completed.stdout.strip() or "available"


class CommandExecutor:
    def __init__(
        self,
        sandbox: str = "auto",
        docker_image: str | None = None,
        docker_network: str = "install-only",
        fallback_to_temp: bool = True,
    ):
        self.requested_sandbox = sandbox
        self.docker_image = docker_image
        self.docker_network = docker_network
        self.fallback_to_temp = fallback_to_temp
        self.fallback_reason: str | None = None
        self.effective_sandbox = self._resolve_sandbox(sandbox)

    def _resolve_sandbox(self, sandbox: str) -> str:
        if sandbox == "temp":
            return "temp"
        if sandbox not in {"auto", "docker"}:
            return "temp"
        available, reason = docker_status()
        if available:
            return "docker"
        if sandbox == "docker" and not self.fallback_to_temp:
            self.fallback_reason = reason
            return "docker-unavailable"
        self.fallback_reason = reason
        return "temp-fallback"

    def run(self, spec: CommandSpec, cwd: Path) -> CommandResult:
        if not spec.command:
            return CommandResult(
                name=spec.name,
                command=None,
                status=CheckStatus.SKIPPED if not spec.required else CheckStatus.FAIL,
                message="No command configured." if not spec.required else "Required command missing.",
                sandbox=self.effective_sandbox,
            )

        allowed, reason = is_command_allowed(spec.command)
        if not allowed:
            return CommandResult(
                name=spec.name,
                command=spec.command,
                status=CheckStatus.FAIL,
                message=reason,
                sandbox=self.effective_sandbox,
            )

        if self.effective_sandbox == "docker":
            return self._run_docker(spec, cwd)
        if self.effective_sandbox == "docker-unavailable":
            return CommandResult(
                name=spec.name,
                command=spec.command,
                status=CheckStatus.FAIL,
                message=f"Docker sandbox required but unavailable: {self.fallback_reason}",
                sandbox=self.effective_sandbox,
            )
        return self._run_local(spec, cwd)

    def _run_local(self, spec: CommandSpec, cwd: Path) -> CommandResult:
        started = time.perf_counter()
        env = os.environ.copy()
        env.setdefault("CI", "true")
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        deps_path = str(cwd / ".basalt-deps")
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = deps_path + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            try:
                completed = subprocess.run(
                    shlex.split(spec.command),
                    cwd=str(cwd),
                    shell=False,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    timeout=spec.timeout_seconds,
                    env=env,
                )
                duration_ms = int((time.perf_counter() - started) * 1000)
                stdout_file.seek(0)
                stderr_file.seek(0)
                stdout_text = stdout_file.read().decode("utf-8", errors="replace")
                stderr_text = stderr_file.read().decode("utf-8", errors="replace")
                message = "Command passed." if completed.returncode == 0 else "Command failed."
                if self.effective_sandbox == "temp-fallback" and self.fallback_reason:
                    message += f" Docker was unavailable; safe temp fallback used ({self.fallback_reason})."
                return CommandResult(
                    name=spec.name,
                    command=spec.command,
                    status=CheckStatus.PASS if completed.returncode == 0 else CheckStatus.FAIL,
                    exit_code=completed.returncode,
                    duration_ms=duration_ms,
                    stdout_tail=_tail(stdout_text),
                    stderr_tail=_tail(stderr_text),
                    message=message,
                    sandbox=self.effective_sandbox,
                )
            except subprocess.TimeoutExpired:
                duration_ms = int((time.perf_counter() - started) * 1000)
                stdout_file.seek(0)
                stderr_file.seek(0)
                stdout_text = stdout_file.read().decode("utf-8", errors="replace")
                stderr_text = stderr_file.read().decode("utf-8", errors="replace")
                return CommandResult(
                    name=spec.name,
                    command=spec.command,
                    status=CheckStatus.FAIL,
                    exit_code=None,
                    duration_ms=duration_ms,
                    stdout_tail=_tail(stdout_text),
                    stderr_tail=_tail(stderr_text),
                    message=f"Command timed out after {spec.timeout_seconds}s.",
                    sandbox=self.effective_sandbox,
                )

    def _network_for(self, spec: CommandSpec) -> str:
        if self.docker_network == "full":
            return "bridge"
        if self.docker_network == "install-only" and spec.allow_network:
            return "bridge"
        return "none"

    def _run_docker(self, spec: CommandSpec, cwd: Path) -> CommandResult:
        image = self.docker_image or "python:3.13-slim"
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            self._network_for(spec),
            "--memory",
            "1g",
            "--cpus",
            "2",
            "--pids-limit",
            "256",
            "--security-opt",
            "no-new-privileges",
            "-e",
            "CI=true",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-e",
            "PYTHONPATH=/workspace/.basalt-deps:/workspace",
            "-v",
            f"{cwd.resolve()}:/workspace",
            "-w",
            "/workspace",
            image,
            "sh",
            "-lc",
            spec.command,
        ]
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                docker_cmd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=spec.timeout_seconds + 45,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            return CommandResult(
                name=spec.name,
                command=" ".join(shlex.quote(item) for item in docker_cmd),
                status=CheckStatus.PASS if completed.returncode == 0 else CheckStatus.FAIL,
                exit_code=completed.returncode,
                duration_ms=duration_ms,
                stdout_tail=_tail(completed.stdout),
                stderr_tail=_tail(completed.stderr),
                message="Docker command passed." if completed.returncode == 0 else "Docker command failed.",
                sandbox="docker",
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return CommandResult(
                name=spec.name,
                command=" ".join(shlex.quote(item) for item in docker_cmd),
                status=CheckStatus.FAIL,
                exit_code=None,
                duration_ms=duration_ms,
                stdout_tail=_tail(exc.stdout),
                stderr_tail=_tail(exc.stderr),
                message=f"Docker command timed out after {spec.timeout_seconds + 45}s.",
                sandbox="docker",
            )


def run_command(
    spec: CommandSpec,
    cwd: Path,
    sandbox: str = "auto",
    docker_image: str | None = None,
) -> CommandResult:
    return CommandExecutor(sandbox=sandbox, docker_image=docker_image).run(spec, cwd)
