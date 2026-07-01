from __future__ import annotations

import shlex
import shutil
import subprocess
import time
from pathlib import Path

from .models import CheckStatus, CommandResult, CommandSpec

SAFE_COMMAND_PREFIXES = (
    "npm ", "npm", "pnpm ", "pnpm", "yarn ", "yarn",
    "python ", "python", "python3 ", "python3",
    "pytest ", "pytest", "pip ", "pip", "pip3 ", "pip3",
    "uv ", "uv", "ruff ", "ruff", "mypy ", "mypy", "pyright ", "pyright",
    "npx ", "npx", "node ", "node", "tsc ", "tsc",
)
DANGEROUS_TOKENS = (
    "rm -rf /", "sudo ", "curl ", "wget ", "scp ", "ssh ", "chmod 777",
    "mkfs", ":(){", "> /dev/sd", "dd if=", "shutdown", "reboot",
    "docker run", "osascript", "open ", "nc ", "netcat", "python -c", "python3 -c",
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
    return False, "Command blocked by MVP allowlist. Use npm/pnpm/yarn/python/pytest/pip/ruff/mypy/npx/node/tsc commands."


class CommandExecutor:
    def __init__(self, sandbox: str = "temp", docker_image: str | None = None):
        self.sandbox = sandbox
        self.docker_image = docker_image

    def run(self, spec: CommandSpec, cwd: Path) -> CommandResult:
        if not spec.command:
            return CommandResult(
                name=spec.name,
                command=None,
                status=CheckStatus.SKIPPED if not spec.required else CheckStatus.FAIL,
                message="No command configured." if not spec.required else "Required command missing.",
            )

        allowed, reason = is_command_allowed(spec.command)
        if not allowed:
            return CommandResult(
                name=spec.name,
                command=spec.command,
                status=CheckStatus.FAIL,
                message=reason,
            )

        if self.sandbox == "docker":
            return self._run_docker(spec, cwd)
        return self._run_local(spec, cwd)

    def _run_local(self, spec: CommandSpec, cwd: Path) -> CommandResult:
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                spec.command,
                cwd=str(cwd),
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=spec.timeout_seconds,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            return CommandResult(
                name=spec.name,
                command=spec.command,
                status=CheckStatus.PASS if completed.returncode == 0 else CheckStatus.FAIL,
                exit_code=completed.returncode,
                duration_ms=duration_ms,
                stdout_tail=_tail(completed.stdout),
                stderr_tail=_tail(completed.stderr),
                message="Command passed." if completed.returncode == 0 else "Command failed.",
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return CommandResult(
                name=spec.name,
                command=spec.command,
                status=CheckStatus.FAIL,
                exit_code=None,
                duration_ms=duration_ms,
                stdout_tail=_tail(exc.stdout),
                stderr_tail=_tail(exc.stderr),
                message=f"Command timed out after {spec.timeout_seconds}s.",
            )

    def _run_docker(self, spec: CommandSpec, cwd: Path) -> CommandResult:
        if shutil.which("docker") is None:
            return CommandResult(
                name=spec.name,
                command=spec.command,
                status=CheckStatus.FAIL,
                message="Docker sandbox requested, but docker was not found on this machine.",
            )
        image = self.docker_image or "python:3.12-slim"
        docker_cmd = [
            "docker", "run", "--rm", "--network", "none",
            "--memory", "1g", "--cpus", "2",
            "-v", f"{cwd.resolve()}:/workspace",
            "-w", "/workspace",
            image,
            "sh", "-lc", spec.command,
        ]
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                docker_cmd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=spec.timeout_seconds + 30,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            return CommandResult(
                name=spec.name,
                command=" ".join(shlex.quote(x) for x in docker_cmd),
                status=CheckStatus.PASS if completed.returncode == 0 else CheckStatus.FAIL,
                exit_code=completed.returncode,
                duration_ms=duration_ms,
                stdout_tail=_tail(completed.stdout),
                stderr_tail=_tail(completed.stderr),
                message="Docker command passed." if completed.returncode == 0 else "Docker command failed.",
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return CommandResult(
                name=spec.name,
                command=" ".join(shlex.quote(x) for x in docker_cmd),
                status=CheckStatus.FAIL,
                exit_code=None,
                duration_ms=duration_ms,
                stdout_tail=_tail(exc.stdout),
                stderr_tail=_tail(exc.stderr),
                message=f"Docker command timed out after {spec.timeout_seconds + 30}s.",
            )


def run_command(spec: CommandSpec, cwd: Path, sandbox: str = "temp", docker_image: str | None = None) -> CommandResult:
    return CommandExecutor(sandbox=sandbox, docker_image=docker_image).run(spec, cwd)
