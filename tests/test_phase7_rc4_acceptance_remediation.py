from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from basalt_proof.command_center import CommandCenterService
from basalt_proof.command_center_server import create_command_center_server
from basalt_proof.context_compiler import compile_context_for_repo
from basalt_proof.proof import verify_repo
from basalt_proof.workspace_service import BuildWorkspaceService


def make_repo(root: Path) -> Path:
    repo = root / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "app" / "service.py").write_text(
        "def is_adult(age: int) -> bool:\n    return age >= 18\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_service.py").write_text(
        "import unittest\nfrom app.service import is_adult\n\n"
        "class T(unittest.TestCase):\n    def test_boundary(self): self.assertTrue(is_adult(18))\n",
        encoding="utf-8",
    )
    (repo / "basalt.yaml").write_text(
        "project:\n  name: remediation-fixture\n  type: python\n"
        "commands:\n  install: null\n  build: null\n  lint: python -m compileall app tests\n  typecheck: null\n  test: python -m unittest discover -s tests -v\n"
        "proof:\n  require_build: false\n  require_lint: true\n  require_typecheck: false\n"
        "  require_tests: true\n  mutation_sample: false\n  security_scan: basic\n  min_verified_score: 80\n"
        "sandbox:\n  mode: temp\n  fallback_to_temp: true\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text("ignored/\n.basalt/\n", encoding="utf-8")
    (repo / "ignored").mkdir()
    (repo / "ignored" / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    return repo



def request(server, method: str, path: str, body: dict | None = None, token: str = ""):
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=60)
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
    status = response.status
    connection.close()
    return status, json.loads(raw.decode("utf-8"))

def init_git(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Basalt", "-c", "user.email=basalt@example.com", "commit", "-qm", "initial"],
        cwd=repo,
        check=True,
    )


class WorkspaceRemediationTests(unittest.TestCase):
    def test_workspace_truth_semantics_and_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            init_git(repo)
            service = BuildWorkspaceService(repo)
            snapshot = service.snapshot()
            self.assertEqual(snapshot["command_metadata"]["lint"]["label"], "Syntax check")
            self.assertEqual(snapshot["command_metadata"]["lint"]["kind"], "syntax")
            self.assertIn("not a full linter", snapshot["command_metadata"]["lint"]["purpose"])
            self.assertTrue(snapshot["repository_state_hash"])

            ignored = service.read_file("ignored/sample.py")
            self.assertTrue(ignored["git"]["ignored"])
            self.assertIn(".gitignore", ignored["git"]["rule"])
            self.assertEqual(ignored["line_count"], 2)  # editor lines include trailing newline

            tracked = service.read_file("app/service.py")
            self.assertTrue(tracked["git"]["tracked"])
            saved = service.save_file(
                "app/service.py",
                tracked["content"] + "\n# acceptance\n",
                tracked["sha256"],
                "Tester",
            )
            self.assertTrue(saved["git"]["tracked"])
            command = service.run_command("lint")
            self.assertEqual(command["display_name"], "Syntax check")
            self.assertEqual(command["kind"], "syntax")
            self.assertEqual(command["status"], "PASS")
            events = service.events()
            self.assertEqual([item["event"] for item in events], ["FILE_SAVED", "COMMAND_RUN"])
            self.assertTrue(all(item["event_id"].startswith("evt_") for item in events))
            self.assertTrue(events[0]["before_sha256"])
            self.assertTrue(events[0]["after_sha256"])
            self.assertEqual(events[1]["exit_code"], 0)
            self.assertTrue(events[1]["repository_state_hash"])

            git = service.git_status()
            self.assertFalse(git["ahead_behind_available"])
            self.assertIsNone(git["ahead"])
            self.assertIsNone(git["behind"])

    def test_ui_contracts_cover_acceptance_findings(self):
        root = Path(__file__).parents[1] / "basalt_proof" / "webui"
        app = (root / "app.js").read_text(encoding="utf-8")
        workspace = (root / "workspace.js").read_text(encoding="utf-8")
        html = (root / "index.html").read_text(encoding="utf-8")
        workspace_html = (root / "workspace.html").read_text(encoding="utf-8")
        styles = (root / "styles.css").read_text(encoding="utf-8")
        workspace_css = (root / "workspace.css").read_text(encoding="utf-8")

        for expected in (
            "Register in Control Plane",
            "Package for staging approval",
            "Historical proof",
            "active output quarantined",
            "Depends on",
            "Expected output",
            "Omitted candidates",
            "SATURATED",
            "Reason paths",
            "artifact-load-more",
            "scrollIntoView",
            "No eligible transaction",
        ):
            self.assertIn(expected, app + html)
        for expected in (
            "IGNORED BY GIT",
            "No cursor",
            "NOT_APPLICABLE",
            "showActivityDetail",
            "repository_state_hash",
            "ahead_behind_available",
            "if (tab?.dirty)",
            "requestAnimationFrame(navigate)",
        ):
            self.assertIn(expected, workspace + workspace_html)
        self.assertNotIn("No private-beta projects registered", app)
        self.assertNotIn("Private Beta Full Build System", (Path(__file__).parents[1] / "basalt_proof" / "command_center.py").read_text(encoding="utf-8"))
        self.assertIn("overflow-wrap: anywhere", styles)
        self.assertIn("white-space: pre-wrap", workspace_css)
        self.assertIn('id="activity-dialog"', workspace_html)

    def test_proof_report_records_exact_project_state(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            report = verify_repo(repo, sandbox_override="temp")
            self.assertTrue(report.project_state_hash)
            data = report.to_dict()
            self.assertEqual(data["project_state_hash"], report.knowledge_graph.state_hash)



class ContextAndEvidenceRemediationTests(unittest.TestCase):
    def test_context_pack_is_inspectable_and_reproducible(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            out = repo / ".basalt"
            pack, artifacts = compile_context_for_repo(
                repo,
                out,
                task="Review age boundary correctness and security",
                agent_role="CodeReviewAgent",
                targets=["app/service.py"],
                token_budget=500,
                excluded_paths=[".basalt"],
                refresh=True,
            )
            self.assertTrue(pack.manifest_hash)
            self.assertTrue(pack.selection_rule_version)
            self.assertIn(pack.budget_status, {"AVAILABLE", "NEAR_LIMIT", "SATURATED"})
            self.assertIsInstance(pack.token_allocation, list)
            self.assertTrue(all("path" in item and "estimated_tokens" in item for item in pack.token_allocation))
            self.assertIsInstance(pack.omitted_candidates, list)
            self.assertTrue(pack.context_precision_explanation)
            markdown = next(path for path in artifacts if path.suffix == ".md").read_text(encoding="utf-8")
            self.assertIn("Manifest hash", markdown)
            self.assertIn("Budget status", markdown)
            self.assertIn("Omitted Candidates", markdown)

    def test_large_artifact_supports_governed_chunks(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            service = CommandCenterService(repo)
            run_dir = service.out_dir / "agent-runs" / "run-large"
            run_dir.mkdir(parents=True)
            path = run_dir / "large.txt"
            path.write_text("A" * 2_100_000, encoding="utf-8")
            item = next(item for item in service.artifacts() if item["name"] == "large.txt")
            self.assertTrue(item["chunked_preview"])
            first = service.read_artifact(item["id"], offset=0, limit=100_000)
            self.assertTrue(first["truncated"])
            self.assertEqual(first["content_bytes"], 100_000)
            second = service.read_artifact(item["id"], offset=first["next_offset"], limit=100_000)
            self.assertEqual(second["content_offset"], 100_000)


class FactoryControlPlaneRemediationTests(unittest.TestCase):
    def test_verified_factory_output_registers_packages_and_requires_approval(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            service = CommandCenterService(repo)
            planned = service.factory_plan(
                "Build a booking platform with authentication, owner dashboards, notifications, and an API.",
                "Acceptance Product",
                template="saas-starter",
                users=["owners", "customers"],
                constraints=["No production secrets", "No deployment"],
            )
            built = service.factory_build(planned["run_id"], "temp")
            self.assertEqual(built["status"], "VERIFIED")
            link = service.factory_register(planned["run_id"], "Tester")
            self.assertTrue(link["project_id"].startswith("proj_"))
            self.assertEqual(service.factory_register(planned["run_id"], "Tester")["project_id"], link["project_id"])

            packaged = service.factory_package(planned["run_id"], "Tester", "staging")
            deployment = packaged["deployment"]
            self.assertEqual(deployment["status"], "AWAITING_APPROVAL")
            packaged_again = service.factory_package(planned["run_id"], "Tester", "staging")
            self.assertTrue(packaged_again["idempotent"])
            self.assertEqual(packaged_again["deployment"]["deployment_id"], deployment["deployment_id"])
            overview = service.overview()
            self.assertEqual(overview["approvals"]["pending"], 1)
            self.assertEqual(overview["approvals"]["items"][0]["kind"], "deployment")

            approved = service.beta_approve_deployment(deployment["deployment_id"], "Reviewer", "Acceptance approval")
            self.assertEqual(approved["status"], "APPROVED")
            promoted = service.beta_promote_deployment(deployment["deployment_id"], "Reviewer")
            self.assertEqual(promoted["status"], "PROMOTED")
            rolled = service.beta_rollback_deployment(deployment["deployment_id"], "Reviewer", "Acceptance rollback")
            self.assertEqual(rolled["status"], "ROLLED_BACK")

            detail = service.factory_run_detail(planned["run_id"])
            self.assertEqual(detail["control_plane"]["project_id"], link["project_id"])
            self.assertEqual(detail["control_plane"]["deployment_id"], deployment["deployment_id"])
            factory_artifact = next(item for item in detail["evidence"] if item["name"] == "product-blueprint.json")
            self.assertEqual(factory_artifact["provenance"]["factory_run_id"], planned["run_id"])
            self.assertEqual(factory_artifact["provenance"]["product_name"], "Acceptance Product")


    def test_http_factory_control_plane_approval_lifecycle(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            server = create_command_center_server(repo, port=0, allow_actions=True, action_token="rc4-action")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, planned = request(
                    server, "POST", "/api/v1/factory/plan",
                    {
                        "name": "HTTP Acceptance Product",
                        "prompt": "Build a booking API with authentication and notifications",
                        "template": "api-service",
                        "users": ["owners", "customers"],
                        "constraints": ["No deployment secrets"],
                        "privacy": "local",
                    },
                    "rc4-action",
                )
                self.assertEqual(status, 200)
                run_id = planned["run_id"]
                status, built = request(server, "POST", f"/api/v1/factory/runs/{run_id}/build", {"sandbox": "temp"}, "rc4-action")
                self.assertEqual(status, 200)
                self.assertEqual(built["status"], "VERIFIED")
                status, registered = request(server, "POST", f"/api/v1/factory/runs/{run_id}/register", {"actor": "Builder"}, "rc4-action")
                self.assertEqual(status, 200)
                self.assertTrue(registered["project_id"].startswith("proj_"))
                status, packaged = request(server, "POST", f"/api/v1/factory/runs/{run_id}/package", {"actor": "Builder", "environment": "staging"}, "rc4-action")
                self.assertEqual(status, 200)
                deployment_id = packaged["deployment"]["deployment_id"]
                self.assertEqual(packaged["deployment"]["status"], "AWAITING_APPROVAL")
                status, overview = request(server, "GET", "/api/v1/overview")
                self.assertEqual(status, 200)
                self.assertEqual(overview["approvals"]["pending"], 1)
                status, rejected = request(server, "POST", f"/api/v1/beta/deployments/{deployment_id}/approve", {"actor": "", "reason": ""}, "rc4-action")
                self.assertEqual(status, 400)
                self.assertIn("required", rejected["error"]["message"].lower())
                status, approved = request(server, "POST", f"/api/v1/beta/deployments/{deployment_id}/approve", {"actor": "Reviewer", "reason": "Proof and checksum reviewed"}, "rc4-action")
                self.assertEqual(status, 200)
                self.assertEqual(approved["status"], "APPROVED")
                status, promoted = request(server, "POST", f"/api/v1/beta/deployments/{deployment_id}/promote", {"actor": "Reviewer"}, "rc4-action")
                self.assertEqual(status, 200)
                self.assertEqual(promoted["status"], "PROMOTED")
                status, rolled = request(server, "POST", f"/api/v1/beta/deployments/{deployment_id}/rollback", {"actor": "Reviewer", "reason": "Acceptance rollback"}, "rc4-action")
                self.assertEqual(status, 200)
                self.assertEqual(rolled["status"], "ROLLED_BACK")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_rollback_detail_exposes_restored_and_quarantine_truth(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            service = CommandCenterService(repo)
            planned = service.factory_plan("Build a local API with authentication", "Rollback Product", template="api-service")
            built = service.factory_build(planned["run_id"], "temp")
            self.assertEqual(built["status"], "VERIFIED")
            rolled = service.factory_rollback(planned["run_id"], "Tester", "Acceptance rollback")
            self.assertEqual(rolled["status"], "ROLLED_BACK")
            detail = service.factory_run_detail(planned["run_id"])
            self.assertTrue(detail["rollback"]["performed"])
            self.assertTrue(detail["rollback"]["restored_state_hash"])
            self.assertTrue(detail["rollback"]["quarantine_path"])
            self.assertFalse(detail["rollback"]["target_active"])
            self.assertTrue(Path(detail["rollback"]["quarantine_path"]).exists())
            self.assertFalse(Path(detail["target_path"]).exists())


if __name__ == "__main__":
    unittest.main()
