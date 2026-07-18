from __future__ import annotations

import contextlib
import io
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from basalt_proof.agent_runtime import plan_agent_fix
from basalt_proof.cli import main
from basalt_proof.command_center import CommandCenterService
from basalt_proof.command_center_server import (
    CommandCenterServerConfig,
    create_command_center_server,
    validate_bind,
)
from basalt_proof.models import AgentRunStatus


def make_repo(root: Path) -> Path:
    repo = root / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "app.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_app.py").write_text(
        "import unittest\n"
        "from app import add\n\n"
        "class AppTests(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n",
        encoding="utf-8",
    )
    (repo / "basalt.yaml").write_text(
        "project:\n  name: phase4-fixture\n  type: python\n"
        "commands:\n  lint: python -m compileall app.py tests\n"
        "  test: python -m unittest discover -s tests -v\n"
        "proof:\n  require_lint: true\n  require_tests: true\n  mutation_sample: false\n"
        "sandbox:\n  mode: temp\n"
        "agents:\n  enabled: true\n  max_files: 4\n  max_changed_lines: 100\n"
        "  require_human_approval_for_source: true\n"
        "  allowed_roles: ImplementationAgent,TestingAgent\n",
        encoding="utf-8",
    )
    return repo


def write_report(repo: Path) -> None:
    out = repo / ".basalt"
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "project_name": "phase4-fixture",
        "project_type": "python",
        "repo_path": str(repo),
        "started_at": "2026-07-17T10:00:00+00:00",
        "finished_at": "2026-07-17T10:00:02+00:00",
        "final_status": "VERIFIED",
        "score": 98,
        "sandbox": "temp",
        "sandbox_requested": "temp",
        "checks": [
            {"name": "lint", "status": "PASS", "sandbox": "temp", "duration_ms": 15, "message": "Compiled"},
            {"name": "tests", "status": "PASS", "sandbox": "temp", "duration_ms": 30, "message": "Passed"},
        ],
        "security_findings": [{"level": "LOW", "file": "app.py", "line": 1, "rule": "info", "message": "Review"}],
        "mutations": [{"file": "app.py", "mutation_type": "return", "survived": False, "message": "Killed"}],
    }
    (out / "proof-report.json").write_text(json.dumps(report), encoding="utf-8")
    (out / "proof-report.md").write_text("# Proof\n", encoding="utf-8")


@contextlib.contextmanager
def running_server(repo: Path, *, allow_actions: bool = False, action_token: str | None = None):
    server = create_command_center_server(
        repo,
        host="127.0.0.1",
        port=0,
        allow_actions=allow_actions,
        action_token=action_token,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def request(server, method: str, path: str, body: dict | str | None = None, headers: dict | None = None):
    port = server.server_address[1]
    connection = HTTPConnection("127.0.0.1", port, timeout=20)
    payload = None
    selected_headers = dict(headers or {})
    if isinstance(body, dict):
        payload = json.dumps(body)
        selected_headers["Content-Type"] = "application/json"
    elif isinstance(body, str):
        payload = body
        selected_headers["Content-Type"] = "application/json"
    connection.request(method, path, body=payload, headers=selected_headers)
    response = connection.getresponse()
    raw = response.read()
    result_headers = dict(response.getheaders())
    connection.close()
    data = json.loads(raw.decode("utf-8")) if "application/json" in result_headers.get("Content-Type", "") else raw.decode("utf-8")
    return response.status, result_headers, data


class CommandCenterServiceTests(unittest.TestCase):
    def test_overview_compresses_truth(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            write_report(repo)
            overview = CommandCenterService(repo).overview()
            self.assertEqual(overview["truth"]["status"], "VERIFIED")
            self.assertEqual(overview["truth"]["score"], 98)
            self.assertTrue(overview["truth"]["graph_fresh"])
            self.assertGreater(overview["graph"]["symbols"], 0)
            self.assertEqual(overview["proof"]["checks"]["passed"], 2)
            self.assertEqual(overview["roadmap"][4]["status"], "COMPLETE")
            self.assertEqual(overview["roadmap"][5]["status"], "ACTIVE")

    def test_overview_without_proof_report_is_safe(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            overview = CommandCenterService(repo).overview()
            self.assertEqual(overview["truth"]["status"], "NOT_RUN")
            self.assertEqual(overview["truth"]["score"], 0)
            self.assertTrue(overview["graph"]["fresh"])

    def test_artifact_vault_only_exposes_known_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            write_report(repo)
            (repo / ".basalt" / "private.tmp").write_text("not exposed", encoding="utf-8")
            service = CommandCenterService(repo)
            ids = {item["id"] for item in service.artifacts()}
            self.assertIn("proof-report.json", ids)
            self.assertNotIn("private.tmp", ids)
            artifact = service.read_artifact("proof-report.json")
            self.assertEqual(artifact["content"]["score"], 98)
            with self.assertRaises(FileNotFoundError):
                service.read_artifact("../../LICENSE")

    def test_impact_and_context_tools_write_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            service = CommandCenterService(repo)
            impact = service.impact("app.py", depth=2)
            self.assertTrue(impact["found"])
            context = service.context("Review addition behavior", "CodeReviewAgent", ["app.py"], 1200)
            self.assertEqual(context["agent_role"], "CodeReviewAgent")
            self.assertTrue((repo / ".basalt" / "impact-analysis.json").exists())
            self.assertTrue((repo / ".basalt" / "context-pack.json").exists())

    def test_pending_approval_is_visible_from_index(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            run_root = repo / ".basalt" / "agent-runs"
            run_root.mkdir(parents=True)
            (run_root / "index.json").write_text(
                json.dumps([{"run_id": "run_pending", "status": "AWAITING_APPROVAL", "task": "Safe change", "risk": "MEDIUM"}]),
                encoding="utf-8",
            )
            overview = CommandCenterService(repo).overview()
            self.assertEqual(overview["approvals"]["pending"], 1)


class CommandCenterServerTests(unittest.TestCase):
    def test_non_loopback_bind_fails_closed(self):
        with self.assertRaises(ValueError):
            validate_bind(CommandCenterServerConfig(host="0.0.0.0", port=7337))
        validate_bind(CommandCenterServerConfig(host="0.0.0.0", port=7337, unsafe_bind=True))

    def test_health_and_static_ui_have_security_headers(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_server(repo) as server:
                status, headers, data = request(server, "GET", "/api/v1/health")
                self.assertEqual(status, 200)
                self.assertEqual(data["status"], "ok")
                self.assertEqual(headers["X-Frame-Options"], "DENY")
                status, headers, page = request(server, "GET", "/")
                self.assertEqual(status, 200)
                self.assertIn("Basalt AI Software Factory", page)
                self.assertIn("default-src 'self'", headers["Content-Security-Policy"])

    def test_bootstrap_never_enables_actions_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_server(repo) as server:
                status, _headers, data = request(server, "GET", "/api/v1/bootstrap")
                self.assertEqual(status, 200)
                self.assertFalse(data["actions_enabled"])
                self.assertEqual(data["action_token"], "")

    def test_bootstrap_exposes_per_launch_token_to_same_origin_app(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_server(repo, allow_actions=True, action_token="phase4-token") as server:
                status, _headers, data = request(server, "GET", "/api/v1/bootstrap")
                self.assertEqual(status, 200)
                self.assertTrue(data["actions_enabled"])
                self.assertEqual(data["action_token"], "phase4-token")

    def test_overview_endpoint_returns_truth_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            write_report(repo)
            with running_server(repo) as server:
                status, _headers, data = request(server, "GET", "/api/v1/overview")
                self.assertEqual(status, 200)
                self.assertEqual(data["truth"]["status"], "VERIFIED")
                self.assertFalse(data["actions"]["enabled"])

    def test_malformed_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_server(repo) as server:
                status, _headers, data = request(server, "POST", "/api/v1/impact", "{not-json")
                self.assertEqual(status, 400)
                self.assertEqual(data["error"]["code"], "REQUEST_REJECTED")

    def test_untrusted_host_header_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_server(repo) as server:
                status, _headers, data = request(
                    server,
                    "GET",
                    "/api/v1/bootstrap",
                    headers={"Host": "attacker.example"},
                )
                self.assertEqual(status, 403)
                self.assertEqual(data["error"]["code"], "HOST_REJECTED")

    def test_cross_origin_post_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_server(repo) as server:
                status, _headers, data = request(
                    server,
                    "POST",
                    "/api/v1/impact",
                    {"target": "app.py"},
                    {"Origin": "https://attacker.example"},
                )
                self.assertEqual(status, 403)
                self.assertEqual(data["error"]["code"], "ORIGIN_REJECTED")

    def test_analysis_endpoints_work_in_read_only_mode(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_server(repo) as server:
                status, _headers, impact = request(server, "POST", "/api/v1/impact", {"target": "app.py", "depth": 2})
                self.assertEqual(status, 200)
                self.assertTrue(impact["found"])
                status, _headers, context = request(
                    server,
                    "POST",
                    "/api/v1/context",
                    {"task": "Review app", "role": "CodeReviewAgent", "targets": ["app.py"], "budget": 1000},
                )
                self.assertEqual(status, 200)
                self.assertEqual(context["agent_role"], "CodeReviewAgent")

    def test_mutating_action_is_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_server(repo) as server:
                status, _headers, data = request(server, "POST", "/api/v1/verify", {"sandbox": "temp"})
                self.assertEqual(status, 403)
                self.assertEqual(data["error"]["code"], "ACTIONS_DISABLED")

    def test_mutating_action_requires_action_token(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_server(repo, allow_actions=True, action_token="expected") as server:
                status, _headers, data = request(server, "POST", "/api/v1/verify", {"sandbox": "temp"})
                self.assertEqual(status, 403)
                self.assertEqual(data["error"]["code"], "INVALID_ACTION_TOKEN")

    def test_artifact_preview_endpoint(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            write_report(repo)
            with running_server(repo) as server:
                status, _headers, data = request(server, "GET", "/api/v1/artifacts/content/proof-report.json")
                self.assertEqual(status, 200)
                self.assertEqual(data["content"]["final_status"], "VERIFIED")

    def test_approval_action_returns_one_time_token(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            patch = repo / "candidate.patch"
            patch.write_text(
                "--- a/app.py\n"
                "+++ b/app.py\n"
                "@@ -1,2 +1,2 @@\n"
                " def add(a: int, b: int) -> int:\n"
                "-    return a + b\n"
                "+    return int(a + b)\n",
                encoding="utf-8",
            )
            run = plan_agent_fix(
                repo,
                "Keep addition typed",
                agent_role="ImplementationAgent",
                targets=["app.py"],
                patch_file=patch,
                sandbox="temp",
            )
            self.assertEqual(run.status, AgentRunStatus.AWAITING_APPROVAL)
            with running_server(repo, allow_actions=True, action_token="session") as server:
                status, _headers, data = request(
                    server,
                    "POST",
                    f"/api/v1/runs/{run.run_id}/approve",
                    {"actor": "Command Center Test", "reason": "Validated patch scope"},
                    {"X-Basalt-Action-Token": "session"},
                )
                self.assertEqual(status, 200)
                self.assertEqual(data["status"], "APPROVED")
                self.assertTrue(data["approval_token"])
                stored = json.loads((repo / ".basalt" / "agent-runs" / run.run_id / "run.json").read_text(encoding="utf-8"))
                self.assertNotIn(data["approval_token"], json.dumps(stored))


class CommandCenterCliTests(unittest.TestCase):
    def test_snapshot_cli(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            write_report(repo)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["command-center", str(repo), "--snapshot", "--json"])
            self.assertEqual(code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["truth"]["status"], "VERIFIED")

    def test_command_center_help_is_registered(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as caught:
                main(["command-center", "--help"])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("--allow-actions", output.getvalue())


if __name__ == "__main__":
    unittest.main()
