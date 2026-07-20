from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from basalt_proof import __version__
from basalt_proof.architecture import architecture_snapshot
from basalt_proof.command_center import CommandCenterService, _proof_metrics
from basalt_proof.command_center_server import create_command_center_server
from basalt_proof.config import infer_commands
from basalt_proof.knowledge_graph import build_project_graph
from basalt_proof.operations import operations_snapshot
from basalt_proof.preview import PreviewError, StaticPreviewManager
from basalt_proof.factory_models import FactoryTask
from basalt_proof.software_factory import FactoryError, _dependency_order
from basalt_proof.state_coordinator import StateCoordinator
from basalt_proof.workspace_service import BuildWorkspaceService


def make_repo(root: Path, *, static: bool = False) -> Path:
    repo = root / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "app" / "service.py").write_text(
        "import sqlite3\n\n"
        "def health():\n    return {'status': 'ok'}\n\n"
        "SCHEMA = '''CREATE TABLE IF NOT EXISTS widgets(id INTEGER PRIMARY KEY);'''\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_service.py").write_text("import unittest\n", encoding="utf-8")
    (repo / "basalt.yaml").write_text(
        "project:\n  name: rc4-fixture\n  type: python\n"
        "commands:\n  lint: python -m compileall app tests\n  test: python -m unittest discover -s tests\n",
        encoding="utf-8",
    )
    if static:
        (repo / "index.html").write_text("<!doctype html><title>Preview</title><h1>Ready</h1>", encoding="utf-8")
        (repo / "app.js").write_text("window.ready = true;\n", encoding="utf-8")
    return repo


def request(server, method: str, path: str, body: dict | None = None, token: str = ""):
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=30)
    headers = {"Accept": "application/json"}
    payload = None
    if body is not None:
        payload = json.dumps(body)
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Basalt-Action-Token"] = token
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    content_type = response.getheader("Content-Type", "")
    connection.close()
    data = json.loads(raw.decode("utf-8")) if "json" in content_type else raw
    return response.status, data


class RC4IdentityAndProofTests(unittest.TestCase):
    def test_release_identity_is_central_and_truthful(self):
        root = Path(__file__).parents[1]
        self.assertEqual(__version__, "3.0.0rc4")
        self.assertIn('version = "3.0.0rc4"', (root / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn("basalt-v3-production-candidate", (root / "basalt.yaml").read_text(encoding="utf-8"))
        active = "\n".join(
            (root / path).read_text(encoding="utf-8")
            for path in [
                "basalt_proof/command_center_server.py",
                "basalt_proof/dashboard.py",
                "basalt_proof/software_factory.py",
                "basalt_proof/webui/index.html",
            ]
        )
        self.assertNotIn("v2.5 Private Beta Full Build System", active)
        self.assertIn("Basalt v3 Production Candidate", active)

    def test_proof_metrics_exclude_skipped_checks_from_applicable_count(self):
        metrics = _proof_metrics({
            "final_status": "VERIFIED",
            "score": 98,
            "checks": [
                {"status": "PASS"}, {"status": "PASS"}, {"status": "SKIPPED"},
                {"status": "SKIP"}, {"status": "NOT_APPLICABLE"},
            ],
        })
        self.assertEqual(metrics["checks"]["passed"], 2)
        self.assertEqual(metrics["checks"]["applicable"], 2)
        self.assertEqual(metrics["checks"]["skipped"], 3)

    def test_inferred_python_lint_is_bounded_to_source_roots(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            (repo / ".basalt").mkdir()
            (repo / ".basalt" / "generated.py").write_text("broken =\n", encoding="utf-8")
            command = infer_commands(repo, "python")["lint"]
            self.assertIn("compileall", command)
            self.assertNotEqual(command.strip(), "python -m compileall .")
            self.assertIn("app", command)
            self.assertIn("tests", command)


class RC4ArchitecturePreviewOperationsTests(unittest.TestCase):
    def test_architecture_is_derived_from_repository_truth(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            graph = build_project_graph(repo, store_path=None)
            data = architecture_snapshot(repo, graph)
            self.assertTrue(data["fresh"])
            self.assertGreaterEqual(data["summary"]["source_files"], 2)
            self.assertIn("widgets", data["database"]["tables"])
            self.assertEqual(data["truth"]["mode"], "STATIC_REPOSITORY_ANALYSIS")

    def test_static_preview_lifecycle_is_same_origin_and_shell_free(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td), static=True)
            manager = StaticPreviewManager(repo, Path(td) / "state")
            self.assertEqual(manager.snapshot()["status"], "STOPPED")
            running = manager.start("Tester")
            self.assertEqual(running["status"], "RUNNING")
            self.assertFalse(running["security"]["arbitrary_shell"])
            asset, content_type = manager.resolve("")
            self.assertEqual(asset.name, "index.html")
            self.assertEqual(content_type, "text/html")
            with self.assertRaises(PreviewError):
                manager.resolve("../secret.txt")
            self.assertEqual(manager.stop("Tester")["status"], "STOPPED")

    def test_operations_report_only_observed_local_conditions(self):
        data = operations_snapshot(
            {"final_status": "WEAK_PROOF", "score": 72},
            {"fresh": False},
            [{"status": "AWAITING_APPROVAL"}, {"rollback_available": True}],
            {"jobs": {"counts": {"FAILED": 1}}, "deployments": {"counts": {}}},
            {"status": "STOPPED"},
        )
        self.assertEqual(data["status"], "DEGRADED")
        self.assertGreaterEqual(data["metrics"]["high_incidents"], 2)
        self.assertEqual(data["scope"], "LOCAL_CONTROL_PLANE")
        self.assertIn("No external uptime", data["recovery"]["claim"])


class RC4GitAndStateTests(unittest.TestCase):

    def test_factory_task_order_respects_dependencies_and_rejects_cycles(self):
        tasks = [
            FactoryTask("review", "Review", "Review output", "CodeReviewAgent", 2, "Review", dependencies=["test"]),
            FactoryTask("build", "Build", "Build output", "BackendAgent", 0, "Build"),
            FactoryTask("test", "Test", "Test output", "TestingAgent", 1, "Test", dependencies=["build"]),
        ]
        self.assertEqual([item.task_id for item in _dependency_order(tasks)], ["build", "test", "review"])
        cyclic = [
            FactoryTask("a", "A", "A", "BackendAgent", 0, "A", dependencies=["b"]),
            FactoryTask("b", "B", "B", "TestingAgent", 1, "B", dependencies=["a"]),
        ]
        with self.assertRaises(FactoryError):
            _dependency_order(cyclic)
    def test_git_diff_is_read_only_and_reports_scope(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Basalt", "-c", "user.email=basalt@example.com", "commit", "-qm", "initial"],
                cwd=repo,
                check=True,
            )
            target = repo / "app" / "service.py"
            target.write_text(target.read_text(encoding="utf-8") + "\nVALUE = 4\n", encoding="utf-8")
            service = BuildWorkspaceService(repo)
            status = service.git_status()
            self.assertTrue(status["dirty"])
            self.assertEqual(status["summary"]["unstaged"], 1)
            self.assertFalse(status["capabilities"]["commit"])
            diff = service.git_diff("app/service.py")
            self.assertIn("+VALUE = 4", diff["diff"])

    def test_factory_rollback_appends_state_instead_of_rewriting_history(self):
        with tempfile.TemporaryDirectory() as td:
            coordinator = StateCoordinator(Path(td) / "state.sqlite3")
            coordinator.bootstrap("base-hash")
            coordinator.begin("run-1", 0, "Build")
            committed = coordinator.commit("run-1", 0, "result-hash", "Built")
            rolled = coordinator.rollback_commit("run-1", committed.version, "base-hash", "Tester", "Acceptance rollback")
            self.assertEqual(rolled.version, 2)
            self.assertEqual(rolled.state_hash, "base-hash")
            self.assertEqual(coordinator.get_version(1).state_hash, "result-hash")
            statuses = {item["run_id"]: item["status"] for item in coordinator.snapshot()["transactions"]}
            self.assertEqual(statuses["run-1"], "ROLLED_BACK")


class RC4BrowserApiContractTests(unittest.TestCase):
    def test_ui_declares_phase7_surfaces_and_accessibility(self):
        root = Path(__file__).parents[1] / "basalt_proof" / "webui"
        html = (root / "index.html").read_text(encoding="utf-8")
        js = (root / "app.js").read_text(encoding="utf-8")
        workspace = (root / "workspace.js").read_text(encoding="utf-8")
        for section in ("architecture", "preview", "operations", "evidence"):
            self.assertIn(f'id="{section}"', html)
        self.assertIn("skip-link", html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn("renderArchitecture", js)
        self.assertIn("renderOperations", js)
        self.assertIn("sessionStorage", workspace)
        self.assertIn("goToLocation(item.line, item.column", workspace)
        self.assertIn("NOT_APPLICABLE", workspace)

    def test_command_center_serves_new_read_apis_and_governed_preview(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td), static=True)
            server = create_command_center_server(repo, port=0, allow_actions=True, action_token="rc4-token")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, architecture = request(server, "GET", "/api/v1/architecture")
                self.assertEqual(status, 200)
                self.assertGreater(architecture["summary"]["source_files"], 0)
                status, preview = request(server, "GET", "/api/v1/preview")
                self.assertEqual(status, 200)
                self.assertEqual(preview["status"], "STOPPED")
                status, _ = request(server, "POST", "/api/v1/preview/start", {"actor": "Tester"})
                self.assertEqual(status, 403)
                status, started = request(server, "POST", "/api/v1/preview/start", {"actor": "Tester"}, "rc4-token")
                self.assertEqual(status, 200)
                self.assertEqual(started["status"], "RUNNING")
                status, page = request(server, "GET", "/preview/")
                self.assertEqual(status, 200)
                self.assertIn(b"<h1>Ready</h1>", page)
                status, operations = request(server, "GET", "/api/v1/operations")
                self.assertEqual(status, 200)
                self.assertEqual(operations["scope"], "LOCAL_CONTROL_PLANE")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


    def test_evidence_content_works_with_external_state_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = make_repo(root)
            state = root / "external-evidence"
            service = CommandCenterService(repo, out_dir=state)
            service.architecture()
            item = next(item for item in service.artifacts() if item["name"] == "architecture-snapshot.json")
            content = service.read_artifact(item["content_id"])
            self.assertEqual(content["relative_evidence_path"], "architecture-snapshot.json")
            self.assertEqual(content["content"]["truth"]["mode"], "STATIC_REPOSITORY_ANALYSIS")

    def test_workspace_capabilities_and_palette_match_configured_commands(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            snapshot = BuildWorkspaceService(repo).snapshot()
            self.assertTrue(snapshot["capabilities"]["static_preview"])
            self.assertTrue(snapshot["capabilities"]["live_preview"])
            self.assertIsNone(snapshot["commands"]["build"])
        root = Path(__file__).parents[1] / "basalt_proof" / "webui"
        workspace = (root / "workspace.js").read_text(encoding="utf-8")
        self.assertIn('.filter((name) => Boolean(state.snapshot?.commands?.[name]))', workspace)

    def test_evidence_vault_exposes_hash_schema_origin_and_mutability(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            service = CommandCenterService(repo)
            service.architecture()
            service.operations()
            evidence = {item["name"]: item for item in service.artifacts()}
            item = evidence["architecture-snapshot.json"]
            self.assertEqual(len(item["sha256"]), 64)
            self.assertIn("schema", item)
            self.assertIn("origin", item)
            self.assertFalse(item["immutable"])
            self.assertEqual(item["integrity"], "HASH_TRACKED")


if __name__ == "__main__":
    unittest.main()
