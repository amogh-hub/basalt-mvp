from __future__ import annotations

import hmac
import json
import secrets
import socket
import threading
import webbrowser
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .command_center import AgentRunError, CommandCenterService
from .deployment_manager import DeploymentError
from .job_queue import JobQueueError
from .private_beta import PrivateBetaError
from .preview import PreviewError
from .release import API_SERVER_VERSION, PRODUCT_NAME, VERSION
from .software_factory import FactoryError
from .workspace_registry import WorkspaceError
from .workspace_service import BuildWorkspaceService, WorkspaceError as BuildWorkspaceError


MAX_REQUEST_BYTES = 1_000_000


@dataclass(frozen=True)
class CommandCenterServerConfig:
    host: str = "127.0.0.1"
    port: int = 7337
    allow_actions: bool = False
    action_token: str = ""
    unsafe_bind: bool = False
    open_browser: bool = True


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return bool(socket.inet_pton(socket.AF_INET, normalized) and normalized.startswith("127."))
    except OSError:
        return False


def validate_bind(config: CommandCenterServerConfig) -> None:
    if not (0 <= config.port <= 65535):
        raise ValueError("Port must be between 0 and 65535.")
    if not _is_loopback_host(config.host) and not config.unsafe_bind:
        raise ValueError(
            "Command Center binds only to localhost by default. Use --unsafe-bind only inside a trusted network."
        )


def _asset_text(name: str) -> str:
    resource = files("basalt_proof").joinpath("webui", name)
    return resource.read_text(encoding="utf-8")


def _asset_bytes(*parts: str) -> bytes:
    resource = files("basalt_proof").joinpath("webui", *parts)
    return resource.read_bytes()


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data, indent=2, sort_keys=False).encode("utf-8")


def create_command_center_server(
    repo: Path,
    host: str = "127.0.0.1",
    port: int = 7337,
    allow_actions: bool = False,
    action_token: str | None = None,
    unsafe_bind: bool = False,
    out_dir: Path | None = None,
) -> ThreadingHTTPServer:
    token = action_token or (secrets.token_urlsafe(32) if allow_actions else "")
    config = CommandCenterServerConfig(
        host=host,
        port=port,
        allow_actions=allow_actions,
        action_token=token,
        unsafe_bind=unsafe_bind,
        open_browser=False,
    )
    validate_bind(config)
    service = CommandCenterService(repo, out_dir)
    workspace = BuildWorkspaceService(repo)

    class Handler(BaseHTTPRequestHandler):
        server_version = API_SERVER_VERSION

        def log_message(self, format: str, *args: object) -> None:
            return

        def _security_headers(self, content_type: str) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            )

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self._security_headers(content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, data: Any) -> None:
            self._send(status, _json_bytes(data), "application/json; charset=utf-8")

        def _error(self, status: int, code: str, message: str) -> None:
            self._send_json(status, {"error": {"code": code, "message": message}})

        def _read_json(self) -> dict[str, Any]:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ValueError("Invalid Content-Length header.") from exc
            if length < 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("Request body is too large.")
            body = self.rfile.read(length)
            if not body:
                return {}
            try:
                data = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Request body must be valid JSON.") from exc
            if not isinstance(data, dict):
                raise ValueError("JSON request body must be an object.")
            return data

        def _host_allowed(self) -> bool:
            if config.unsafe_bind:
                return True
            host_header = self.headers.get("Host", "").strip()
            if not host_header:
                return False
            if host_header.startswith("[") and "]" in host_header:
                hostname = host_header[1 : host_header.index("]")]
            else:
                hostname = host_header.split(":", 1)[0]
            return _is_loopback_host(hostname)

        def _origin_allowed(self) -> bool:
            origin = self.headers.get("Origin", "").strip()
            if not origin:
                return True
            host_header = self.headers.get("Host", "").strip()
            return origin in {f"http://{host_header}", f"https://{host_header}"}

        def _require_action_access(self) -> bool:
            if not self._origin_allowed():
                self._error(HTTPStatus.FORBIDDEN, "ORIGIN_REJECTED", "Cross-origin action request rejected.")
                return False
            if not config.allow_actions:
                self._error(
                    HTTPStatus.FORBIDDEN,
                    "ACTIONS_DISABLED",
                    "Command Center actions are disabled. Restart with --allow-actions.",
                )
                return False
            supplied = self.headers.get("X-Basalt-Action-Token", "")
            if not supplied or not hmac.compare_digest(supplied, config.action_token):
                self._error(HTTPStatus.FORBIDDEN, "INVALID_ACTION_TOKEN", "Action token is missing or invalid.")
                return False
            return True

        def _route_parts(self) -> list[str]:
            return [unquote(item) for item in urlparse(self.path).path.split("/") if item]

        def do_GET(self) -> None:
            if not self._host_allowed():
                self._error(HTTPStatus.FORBIDDEN, "HOST_REJECTED", "Untrusted Host header rejected.")
                return
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path == "/":
                    self._send(HTTPStatus.OK, _asset_text("index.html").encode("utf-8"), "text/html; charset=utf-8")
                    return
                if path == "/workspace":
                    self._send(HTTPStatus.OK, _asset_text("workspace.html").encode("utf-8"), "text/html; charset=utf-8")
                    return
                if path == "/assets/styles.css":
                    self._send(HTTPStatus.OK, _asset_text("styles.css").encode("utf-8"), "text/css; charset=utf-8")
                    return
                if path == "/assets/app.js":
                    self._send(HTTPStatus.OK, _asset_text("app.js").encode("utf-8"), "application/javascript; charset=utf-8")
                    return
                if path == "/assets/workspace.css":
                    self._send(HTTPStatus.OK, _asset_text("workspace.css").encode("utf-8"), "text/css; charset=utf-8")
                    return
                if path == "/assets/workspace.js":
                    self._send(HTTPStatus.OK, _asset_text("workspace.js").encode("utf-8"), "application/javascript; charset=utf-8")
                    return
                if path.startswith("/preview"):
                    requested = path[len("/preview/"):] if path.startswith("/preview/") else ""
                    asset, content_type = service.preview_manager().resolve(requested)
                    self._send(HTTPStatus.OK, asset.read_bytes(), content_type)
                    return
                if path.startswith("/assets/brand/"):
                    name = path.rsplit("/", 1)[-1]
                    allowed = {
                        "basalt-wordmark-mask.png",
                        "basalt-wordmark-dark.png",
                        "basalt-wordmark-light.png",
                        "basalt-mark-dark.png",
                        "basalt-mark-light.png",
                    }
                    if name not in allowed:
                        self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "Brand asset not found.")
                        return
                    self._send(HTTPStatus.OK, _asset_bytes("brand", name), "image/png")
                    return
                if path == "/api/v1/health":
                    self._send_json(
                        HTTPStatus.OK,
                        {"status": "ok", "service": PRODUCT_NAME, "version": VERSION, "api_version": "v1"},
                    )
                    return
                if path == "/api/v1/bootstrap":
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "actions_enabled": config.allow_actions,
                            "action_token": config.action_token if config.allow_actions else "",
                            "host": config.host,
                            "port": self.server.server_address[1],
                        },
                    )
                    return
                if path == "/api/v1/overview":
                    data = service.overview()
                    data["actions"] = {"enabled": config.allow_actions}
                    self._send_json(HTTPStatus.OK, data)
                    return
                if path == "/api/v1/proof":
                    self._send_json(HTTPStatus.OK, service.proof_report())
                    return
                if path == "/api/v1/workspace":
                    self._send_json(HTTPStatus.OK, workspace.snapshot())
                    return
                if path == "/api/v1/workspace/tree":
                    query = parse_qs(parsed.query)
                    self._send_json(HTTPStatus.OK, workspace.tree(str((query.get("path") or [""])[0]), int((query.get("depth") or [4])[0])))
                    return
                if path == "/api/v1/workspace/file":
                    query = parse_qs(parsed.query)
                    self._send_json(HTTPStatus.OK, workspace.read_file(str((query.get("path") or [""])[0])))
                    return
                if path == "/api/v1/workspace/search":
                    query = parse_qs(parsed.query)
                    self._send_json(HTTPStatus.OK, workspace.search(str((query.get("q") or [""])[0]), int((query.get("limit") or [100])[0])))
                    return
                if path == "/api/v1/workspace/events":
                    self._send_json(HTTPStatus.OK, {"items": workspace.events()})
                    return
                if path == "/api/v1/workspace/git":
                    self._send_json(HTTPStatus.OK, workspace.git_status())
                    return
                if path == "/api/v1/workspace/git/diff":
                    query = parse_qs(parsed.query)
                    self._send_json(
                        HTTPStatus.OK,
                        workspace.git_diff(
                            str((query.get("path") or [""])[0]),
                            str((query.get("staged") or ["false"])[0]).lower() in {"1", "true", "yes"},
                        ),
                    )
                    return
                if path == "/api/v1/architecture":
                    self._send_json(HTTPStatus.OK, service.architecture())
                    return
                if path == "/api/v1/preview":
                    self._send_json(HTTPStatus.OK, service.preview_state())
                    return
                if path == "/api/v1/operations":
                    self._send_json(HTTPStatus.OK, service.operations())
                    return
                if path == "/api/v1/artifacts":
                    self._send_json(HTTPStatus.OK, {"items": service.artifacts()})
                    return
                parts = self._route_parts()
                if len(parts) == 5 and parts[:4] == ["api", "v1", "artifacts", "content"]:
                    query = parse_qs(parsed.query)
                    offset = int((query.get("offset") or [0])[0])
                    limit = int((query.get("limit") or [200000])[0])
                    self._send_json(HTTPStatus.OK, service.read_artifact(parts[4], offset=offset, limit=limit))
                    return
                if path == "/api/v1/runs":
                    self._send_json(HTTPStatus.OK, {"items": service.recent_runs()})
                    return
                if path == "/api/v1/factory":
                    self._send_json(HTTPStatus.OK, service.factory_state())
                    return
                if path == "/api/v1/factory/runs":
                    self._send_json(HTTPStatus.OK, {"items": service.factory_runs()})
                    return
                if path == "/api/v1/beta":
                    self._send_json(HTTPStatus.OK, service.beta_state())
                    return
                if path == "/api/v1/beta/projects":
                    self._send_json(HTTPStatus.OK, {"items": service.private_beta().registry.list_projects()})
                    return
                if path == "/api/v1/beta/jobs":
                    self._send_json(HTTPStatus.OK, {"items": service.private_beta().jobs.list()})
                    return
                if path == "/api/v1/beta/providers":
                    self._send_json(HTTPStatus.OK, service.private_beta().providers.snapshot())
                    return
                if path == "/api/v1/beta/deployments":
                    self._send_json(HTTPStatus.OK, service.private_beta().deployments.snapshot())
                    return
                if len(parts) == 4 and parts[:3] == ["api", "v1", "runs"]:
                    self._send_json(HTTPStatus.OK, service.run_detail(parts[3]))
                    return
                if len(parts) == 5 and parts[:4] == ["api", "v1", "factory", "runs"]:
                    self._send_json(HTTPStatus.OK, service.factory_run_detail(parts[4]))
                    return
                if len(parts) == 5 and parts[:4] == ["api", "v1", "beta", "jobs"]:
                    self._send_json(HTTPStatus.OK, service.private_beta().jobs.get(parts[4]).to_dict())
                    return
                if len(parts) == 5 and parts[:4] == ["api", "v1", "beta", "deployments"]:
                    self._send_json(HTTPStatus.OK, service.private_beta().deployments.get(parts[4]).to_dict())
                    return
                if path == "/api/v1/graph/query":
                    query = parse_qs(parsed.query)
                    term = str((query.get("term") or [""])[0]).strip()
                    if not term:
                        self._error(HTTPStatus.BAD_REQUEST, "TERM_REQUIRED", "Query term is required.")
                        return
                    graph = service.ensure_graph()
                    matches = {
                        "term": term,
                        "files": [asdict(item) for item in graph.files if term.lower() in item.path.lower()][:30],
                        "symbols": [
                            asdict(item)
                            for item in graph.symbols
                            if term.lower() in item.name.lower() or term.lower() in item.qualified_name.lower()
                        ][:50],
                        "features": [asdict(item) for item in graph.features if term.lower() in item.name.lower()][:30],
                    }
                    self._send_json(HTTPStatus.OK, matches)
                    return
                self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "Route not found.")
            except FileNotFoundError as exc:
                self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", str(exc))
            except (AgentRunError, BuildWorkspaceError, PermissionError, ValueError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, "REQUEST_REJECTED", str(exc))
            except Exception:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "Command Center request failed.")

        def do_POST(self) -> None:
            if not self._host_allowed():
                self._error(HTTPStatus.FORBIDDEN, "HOST_REJECTED", "Untrusted Host header rejected.")
                return
            parts = self._route_parts()
            try:
                if not self._origin_allowed():
                    self._error(HTTPStatus.FORBIDDEN, "ORIGIN_REJECTED", "Cross-origin request rejected.")
                    return
                data = self._read_json()
                if parts == ["api", "v1", "impact"]:
                    result = service.impact(str(data.get("target", "")), int(data.get("depth", 3)))
                    self._send_json(HTTPStatus.OK, result)
                    return
                if parts == ["api", "v1", "context"]:
                    targets = data.get("targets") or []
                    if not isinstance(targets, list):
                        raise ValueError("Context targets must be a list.")
                    result = service.context(
                        str(data.get("task", "")),
                        str(data.get("role", "CodeReviewAgent")),
                        [str(item) for item in targets],
                        int(data["budget"]) if data.get("budget") is not None else None,
                    )
                    self._send_json(HTTPStatus.OK, result)
                    return
                if parts == ["api", "v1", "workspace", "diff"]:
                    result = workspace.diff_file(
                        str(data.get("path", "")),
                        str(data.get("content", "")),
                        str(data.get("expected_sha256", "")),
                    )
                    self._send_json(HTTPStatus.OK, result)
                    return
                if parts == ["api", "v1", "workspace", "diagnostics"]:
                    result = workspace.diagnostics(
                        str(data.get("path", "")),
                        str(data.get("content", "")),
                    )
                    self._send_json(HTTPStatus.OK, result)
                    return
                if parts == ["api", "v1", "workspace", "file"]:
                    if not self._require_action_access():
                        return
                    result = workspace.save_file(str(data.get("path", "")), str(data.get("content", "")), str(data.get("expected_sha256", "")), str(data.get("actor", "")))
                    self._send_json(HTTPStatus.OK, result)
                    return
                if parts == ["api", "v1", "workspace", "create"]:
                    if not self._require_action_access():
                        return
                    result = workspace.create_file(str(data.get("path", "")), str(data.get("content", "")), str(data.get("actor", "")))
                    self._send_json(HTTPStatus.OK, result)
                    return
                if parts == ["api", "v1", "workspace", "command"]:
                    if not self._require_action_access():
                        return
                    result = workspace.run_command(str(data.get("name", "")), int(data.get("timeout_seconds", 300)))
                    self._send_json(HTTPStatus.OK, result)
                    return
                if parts == ["api", "v1", "verify"]:
                    if not self._require_action_access():
                        return
                    self._send_json(HTTPStatus.OK, service.verify(data.get("sandbox")))
                    return
                if parts in (["api", "v1", "preview", "start"], ["api", "v1", "preview", "stop"]):
                    if not self._require_action_access():
                        return
                    actor = str(data.get("actor", "local-user"))
                    result = service.preview_start(actor) if parts[-1] == "start" else service.preview_stop(actor)
                    self._send_json(HTTPStatus.OK, result)
                    return
                if parts == ["api", "v1", "factory", "plan"]:
                    if not self._require_action_access():
                        return
                    users = data.get("users") or []
                    constraints = data.get("constraints") or []
                    if not isinstance(users, list) or not isinstance(constraints, list):
                        raise ValueError("Factory users and constraints must be lists.")
                    result = service.factory_plan(
                        str(data.get("prompt", "")),
                        str(data.get("name", "")),
                        str(data.get("template", "python-service")),
                        [str(item) for item in users],
                        [str(item) for item in constraints],
                        str(data.get("privacy", "local")),
                    )
                    self._send_json(HTTPStatus.OK, result)
                    return
                if len(parts) == 6 and parts[:4] == ["api", "v1", "factory", "runs"]:
                    if not self._require_action_access():
                        return
                    if parts[5] == "build":
                        result = service.factory_build(parts[4], str(data.get("sandbox", "temp")))
                    elif parts[5] == "rollback":
                        result = service.factory_rollback(
                            parts[4], str(data.get("actor", "")), str(data.get("reason", ""))
                        )
                    elif parts[5] == "register":
                        result = service.factory_register(parts[4], str(data.get("actor", "Local user")))
                    elif parts[5] == "package":
                        result = service.factory_package(
                            parts[4], str(data.get("actor", "Local user")), str(data.get("environment", "staging"))
                        )
                    else:
                        self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "Unknown factory run action.")
                        return
                    self._send_json(HTTPStatus.OK, result)
                    return
                if parts == ["api", "v1", "beta", "bootstrap"]:
                    if not self._require_action_access():
                        return
                    self._send_json(HTTPStatus.OK, service.beta_bootstrap(
                        str(data.get("email", "")), str(data.get("display_name", "")), str(data.get("team_name", ""))
                    ))
                    return
                if parts == ["api", "v1", "beta", "projects"]:
                    if not self._require_action_access():
                        return
                    self._send_json(HTTPStatus.OK, service.beta_add_project(
                        str(data.get("team_id", "")), str(data.get("name", "")),
                        str(data.get("repo_path", service.repo)), str(data.get("created_by", "")),
                        str(data.get("template", "fullstack-lite")), str(data.get("privacy_mode", "local"))
                    ))
                    return
                if parts == ["api", "v1", "beta", "jobs"]:
                    if not self._require_action_access():
                        return
                    payload = data.get("payload") or {}
                    if not isinstance(payload, dict):
                        raise ValueError("Job payload must be an object.")
                    self._send_json(HTTPStatus.OK, service.beta_submit_job(
                        str(data.get("project_id", "")), str(data.get("job_type", "")), payload,
                        str(data.get("created_by", "")), str(data.get("idempotency_key", ""))
                    ))
                    return
                if len(parts) == 6 and parts[:4] == ["api", "v1", "beta", "jobs"]:
                    if not self._require_action_access():
                        return
                    job_id, action = parts[4], parts[5]
                    if action == "run":
                        result = service.beta_run_job(job_id, str(data.get("worker_id", "command-center-worker")))
                    elif action == "cancel":
                        result = service.beta_cancel_job(job_id, str(data.get("actor", "")), str(data.get("reason", "")))
                    elif action == "retry":
                        result = service.beta_retry_job(job_id, str(data.get("actor", "")))
                    else:
                        self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "Unknown beta job action.")
                        return
                    self._send_json(HTTPStatus.OK, result)
                    return
                if len(parts) == 6 and parts[:4] == ["api", "v1", "beta", "deployments"]:
                    if not self._require_action_access():
                        return
                    deployment_id, action = parts[4], parts[5]
                    if action == "approve":
                        result = service.beta_approve_deployment(deployment_id, str(data.get("actor", "")), str(data.get("reason", "")))
                    elif action == "promote":
                        result = service.beta_promote_deployment(deployment_id, str(data.get("actor", "")))
                    elif action == "rollback":
                        result = service.beta_rollback_deployment(deployment_id, str(data.get("actor", "")), str(data.get("reason", "")))
                    else:
                        self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "Unknown deployment action.")
                        return
                    self._send_json(HTTPStatus.OK, result)
                    return
                if len(parts) == 5 and parts[:3] == ["api", "v1", "runs"]:
                    if not self._require_action_access():
                        return
                    run_id = parts[3]
                    action = parts[4]
                    if action == "approve":
                        result = service.approve(run_id, str(data.get("actor", "")), str(data.get("reason", "")))
                    elif action == "reject":
                        result = service.reject(run_id, str(data.get("actor", "")), str(data.get("reason", "")))
                    elif action == "apply":
                        result = service.apply(
                            run_id,
                            str(data.get("approval_token", "")),
                            str(data.get("sandbox")) if data.get("sandbox") else None,
                        )
                    elif action == "rollback":
                        result = service.rollback(run_id, str(data.get("actor", "")), str(data.get("reason", "")))
                    else:
                        self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "Unknown run action.")
                        return
                    self._send_json(HTTPStatus.OK, result)
                    return
                self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "Route not found.")
            except (
                AgentRunError,
                DeploymentError,
                JobQueueError,
                PrivateBetaError,
                PreviewError,
                FactoryError,
                WorkspaceError,
                BuildWorkspaceError,
                FileNotFoundError,
                PermissionError,
                ValueError,
            ) as exc:
                self._error(HTTPStatus.BAD_REQUEST, "REQUEST_REJECTED", str(exc))
            except Exception:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "Command Center action failed.")

    server = ThreadingHTTPServer((config.host, config.port), Handler)
    server.daemon_threads = True
    server.basalt_config = config  # type: ignore[attr-defined]
    server.basalt_service = service  # type: ignore[attr-defined]
    return server


def serve_command_center(
    repo: Path,
    host: str = "127.0.0.1",
    port: int = 7337,
    allow_actions: bool = False,
    unsafe_bind: bool = False,
    open_browser: bool = True,
    out_dir: Path | None = None,
) -> None:
    server = create_command_center_server(
        repo,
        host=host,
        port=port,
        allow_actions=allow_actions,
        unsafe_bind=unsafe_bind,
        out_dir=out_dir,
    )
    actual_host, actual_port = server.server_address[:2]
    display_host = "127.0.0.1" if actual_host in {"0.0.0.0", "::"} else actual_host
    url = f"http://{display_host}:{actual_port}"
    print(f"{PRODUCT_NAME} · {VERSION}")
    print(f"- repository: {Path(repo).resolve()}")
    print(f"- URL: {url}")
    print(f"- actions: {'enabled' if allow_actions else 'read-only'}")
    print("- stop: Ctrl+C")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


__all__ = [
    "CommandCenterServerConfig",
    "create_command_center_server",
    "serve_command_center",
    "validate_bind",
]
