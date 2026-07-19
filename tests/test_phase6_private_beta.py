from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from basalt_proof.beta_models import DeploymentStatus, JobStatus, WorkspaceRole
from basalt_proof.cli import main
from basalt_proof.command_center import CommandCenterService
from basalt_proof.command_center_server import create_command_center_server
from basalt_proof.deployment_manager import DeploymentError, DeploymentManager
from basalt_proof.job_queue import DurableJobQueue, JobQueueError
from basalt_proof.private_beta import PrivateBetaPlatform
from basalt_proof.provider_registry import ProviderError, ProviderRegistry
from basalt_proof.software_factory import SUPPORTED_TEMPLATES, create_product
from basalt_proof.workspace_registry import WorkspaceError, WorkspaceRegistry
from basalt_proof.workspace_runtime import SandboxProfile, WorkspaceManager, WorkspaceRuntimeError


def make_repo(root: Path, name: str = "source") -> Path:
    repo = root / name
    repo.mkdir()
    (repo / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (repo / "test_app.py").write_text(
        "import unittest\nfrom app import add\n\nclass Tests(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n",
        encoding="utf-8",
    )
    (repo / "basalt.yaml").write_text(
        "project:\n  name: beta-fixture\n  type: python\n"
        "commands:\n  lint: python -m compileall app.py test_app.py\n  test: python -m unittest -v\n"
        "proof:\n  require_lint: true\n  require_tests: true\n  mutation_sample: false\n"
        "sandbox:\n  mode: temp\n",
        encoding="utf-8",
    )
    return repo


def write_verified_proof(root: Path, score: int = 98, status: str = "VERIFIED") -> Path:
    path = root / "proof-report.json"
    path.write_text(json.dumps({"final_status": status, "score": score, "sandbox": "temp"}), encoding="utf-8")
    return path


class WorkspaceRegistryTests(unittest.TestCase):
    def test_bootstrap_owner_membership(self):
        with tempfile.TemporaryDirectory() as td:
            registry = WorkspaceRegistry(Path(td) / "workspace.db")
            user = registry.create_user("founder@example.com", "Founder")
            team = registry.create_team("Basalt Labs", user.user_id)
            self.assertEqual(registry.member_role(team.team_id, user.user_id), WorkspaceRole.OWNER)
            self.assertEqual(registry.snapshot()["counts"]["teams"], 1)

    def test_user_creation_is_email_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            registry = WorkspaceRegistry(Path(td) / "workspace.db")
            first = registry.create_user("Founder@Example.com", "Founder")
            second = registry.create_user("founder@example.com", "Different Name")
            self.assertEqual(first.user_id, second.user_id)

    def test_invalid_email_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            registry = WorkspaceRegistry(Path(td) / "workspace.db")
            with self.assertRaises(WorkspaceError):
                registry.create_user("invalid", "Founder")

    def test_admin_can_add_developer(self):
        with tempfile.TemporaryDirectory() as td:
            registry = WorkspaceRegistry(Path(td) / "workspace.db")
            owner = registry.create_user("owner@example.com", "Owner")
            developer = registry.create_user("dev@example.com", "Developer")
            team = registry.create_team("Team", owner.user_id)
            membership = registry.add_member(team.team_id, developer.user_id, WorkspaceRole.DEVELOPER, owner.user_id)
            self.assertEqual(membership.role, WorkspaceRole.DEVELOPER)

    def test_viewer_cannot_create_project(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = WorkspaceRegistry(root / "workspace.db")
            owner = registry.create_user("owner@example.com", "Owner")
            viewer = registry.create_user("viewer@example.com", "Viewer")
            team = registry.create_team("Team", owner.user_id)
            registry.add_member(team.team_id, viewer.user_id, WorkspaceRole.VIEWER, owner.user_id)
            with self.assertRaises(WorkspaceError):
                registry.create_project(team.team_id, "Demo", make_repo(root), viewer.user_id)

    def test_developer_can_register_project(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = WorkspaceRegistry(root / "workspace.db")
            owner = registry.create_user("owner@example.com", "Owner")
            developer = registry.create_user("dev@example.com", "Developer")
            team = registry.create_team("Team", owner.user_id)
            registry.add_member(team.team_id, developer.user_id, WorkspaceRole.DEVELOPER, owner.user_id)
            project = registry.create_project(team.team_id, "Demo", make_repo(root), developer.user_id, template="saas-starter")
            self.assertEqual(project.template, "saas-starter")
            self.assertEqual(registry.require_project_role(project.project_id, developer.user_id, WorkspaceRole.DEVELOPER).project_id, project.project_id)

    def test_duplicate_project_slug_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = WorkspaceRegistry(root / "workspace.db")
            owner = registry.create_user("owner@example.com", "Owner")
            team = registry.create_team("Team", owner.user_id)
            registry.create_project(team.team_id, "Demo", make_repo(root, "one"), owner.user_id)
            with self.assertRaises(WorkspaceError):
                registry.create_project(team.team_id, "Demo", make_repo(root, "two"), owner.user_id)

    def test_project_status_requires_admin(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = WorkspaceRegistry(root / "workspace.db")
            owner = registry.create_user("owner@example.com", "Owner")
            developer = registry.create_user("dev@example.com", "Developer")
            team = registry.create_team("Team", owner.user_id)
            registry.add_member(team.team_id, developer.user_id, WorkspaceRole.DEVELOPER, owner.user_id)
            project = registry.create_project(team.team_id, "Demo", make_repo(root), owner.user_id)
            with self.assertRaises(WorkspaceError):
                registry.set_project_status(project.project_id, "PAUSED", developer.user_id)
            self.assertEqual(registry.set_project_status(project.project_id, "PAUSED", owner.user_id).status, "PAUSED")

    def test_activity_is_append_only_visible(self):
        with tempfile.TemporaryDirectory() as td:
            registry = WorkspaceRegistry(Path(td) / "workspace.db")
            user = registry.create_user("owner@example.com", "Owner")
            team = registry.create_team("Team", user.user_id)
            actions = [item["action"] for item in registry.activity()]
            self.assertIn("TEAM_CREATED", actions)
            self.assertEqual(registry.get_team(team.team_id).name, "Team")


class DurableJobQueueTests(unittest.TestCase):
    def test_idempotency_key_returns_existing_job(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DurableJobQueue(Path(td) / "jobs.db")
            first = queue.submit("p1", "VERIFY_PROJECT", {}, "u1", "same")
            second = queue.submit("p1", "VERIFY_PROJECT", {"different": True}, "u1", "same")
            self.assertEqual(first.job_id, second.job_id)

    def test_jobs_without_idempotency_key_are_distinct(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DurableJobQueue(Path(td) / "jobs.db")
            first = queue.submit("p1", "VERIFY_PROJECT", {}, "u1")
            second = queue.submit("p1", "VERIFY_PROJECT", {}, "u1")
            self.assertNotEqual(first.job_id, second.job_id)

    def test_claim_start_complete_lifecycle(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DurableJobQueue(Path(td) / "jobs.db")
            job = queue.submit("p1", "VERIFY_PROJECT", {}, "u1")
            self.assertEqual(queue.claim("worker").job_id, job.job_id)
            self.assertEqual(queue.start(job.job_id, "worker").status, JobStatus.RUNNING)
            done = queue.complete(job.job_id, "worker", {"ok": True})
            self.assertEqual(done.status, JobStatus.SUCCEEDED)
            self.assertTrue(done.result["ok"])

    def test_retryable_failure_enters_retry_wait(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DurableJobQueue(Path(td) / "jobs.db")
            job = queue.submit("p1", "VERIFY_PROJECT", {}, "u1", max_attempts=2)
            queue.claim("worker")
            queue.start(job.job_id, "worker")
            failed = queue.fail(job.job_id, "worker", "temporary", retryable=True)
            self.assertEqual(failed.status, JobStatus.RETRY_WAIT)

    def test_nonretryable_failure_is_terminal(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DurableJobQueue(Path(td) / "jobs.db")
            job = queue.submit("p1", "VERIFY_PROJECT", {}, "u1")
            queue.claim("worker")
            queue.start(job.job_id, "worker")
            failed = queue.fail(job.job_id, "worker", "permanent", retryable=False)
            self.assertEqual(failed.status, JobStatus.FAILED)

    def test_cancel_pending_job(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DurableJobQueue(Path(td) / "jobs.db")
            job = queue.submit("p1", "VERIFY_PROJECT", {}, "u1")
            cancelled = queue.cancel(job.job_id, "u1", "not needed")
            self.assertEqual(cancelled.status, JobStatus.CANCELLED)

    def test_terminal_job_cannot_be_cancelled(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DurableJobQueue(Path(td) / "jobs.db")
            job = queue.submit("p1", "VERIFY_PROJECT", {}, "u1")
            queue.claim("worker"); queue.start(job.job_id, "worker"); queue.complete(job.job_id, "worker", {})
            with self.assertRaises(JobQueueError):
                queue.cancel(job.job_id, "u1", "late")

    def test_manual_retry_requeues_failed_job(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DurableJobQueue(Path(td) / "jobs.db")
            job = queue.submit("p1", "VERIFY_PROJECT", {}, "u1")
            queue.claim("worker"); queue.start(job.job_id, "worker"); queue.fail(job.job_id, "worker", "bad", retryable=False)
            self.assertEqual(queue.retry(job.job_id, "u1").status, JobStatus.PENDING)

    def test_worker_ownership_is_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DurableJobQueue(Path(td) / "jobs.db")
            job = queue.submit("p1", "VERIFY_PROJECT", {}, "u1")
            queue.claim("worker-a")
            with self.assertRaises(JobQueueError):
                queue.start(job.job_id, "worker-b")

    def test_run_next_uses_registered_handler(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DurableJobQueue(Path(td) / "jobs.db")
            queue.submit("p1", "PING", {"value": 7}, "u1")
            result = queue.run_next("worker", {"PING": lambda job: {"value": job.payload["value"] + 1}})
            self.assertEqual(result.status, JobStatus.SUCCEEDED)
            self.assertEqual(result.result["value"], 8)

    def test_events_record_lifecycle(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DurableJobQueue(Path(td) / "jobs.db")
            job = queue.submit("p1", "PING", {}, "u1")
            queue.claim("worker")
            events = [item["event"] for item in queue.events(job.job_id)]
            self.assertEqual(events[:2], ["SUBMITTED", "CLAIMED"])


class _ProviderHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        payload = {
            "model": body["model"],
            "choices": [{"message": {"content": "provider-ok"}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        }
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        return


class ProviderRegistryTests(unittest.TestCase):
    def test_local_provider_inventory_is_available(self):
        registry = ProviderRegistry(environ={})
        snapshot = registry.snapshot()
        self.assertGreaterEqual(snapshot["configured"], 2)
        self.assertTrue(all("api_key_env" not in item for item in snapshot["providers"]))

    def test_local_privacy_selects_local_provider(self):
        selected = ProviderRegistry(environ={}).choose("reasoning", "local")
        self.assertEqual(selected.kind, "local")

    def test_environment_remote_profile_is_configured(self):
        registry = ProviderRegistry(environ={
            "BASALT_OPENAI_BASE_URL": "http://127.0.0.1:1",
            "BASALT_OPENAI_MODEL": "model-x",
            "BASALT_OPENAI_API_KEY": "secret",
        })
        self.assertTrue(registry.get("openai-compatible").configured)
        self.assertNotIn("secret", json.dumps(registry.inventory()))

    def test_remote_profile_without_key_is_not_configured(self):
        registry = ProviderRegistry(environ={
            "BASALT_OPENAI_BASE_URL": "http://127.0.0.1:1",
            "BASALT_OPENAI_MODEL": "model-x",
        })
        self.assertFalse(registry.get("openai-compatible").configured)

    def test_openai_compatible_adapter(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ProviderHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {
                "BASALT_OPENAI_BASE_URL": f"http://127.0.0.1:{server.server_address[1]}",
                "BASALT_OPENAI_MODEL": "model-x",
                "BASALT_OPENAI_API_KEY": "secret",
            }
            result = ProviderRegistry(environ=env).complete("openai-compatible", [{"role": "user", "content": "hello"}])
            self.assertEqual(result["content"], "provider-ok")
            self.assertEqual(result["usage"]["total_tokens"], 6)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_unconfigured_provider_fails_closed(self):
        registry = ProviderRegistry(environ={
            "BASALT_OPENAI_BASE_URL": "http://127.0.0.1:1",
            "BASALT_OPENAI_MODEL": "model-x",
        })
        with self.assertRaises(ProviderError):
            registry.complete("openai-compatible", [{"role": "user", "content": "hello"}])


class WorkspaceRuntimeTests(unittest.TestCase):
    def test_prepare_copies_source_and_excludes_git(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = make_repo(root)
            (source / ".git").mkdir(); (source / ".git" / "config").write_text("secret")
            manager = WorkspaceManager(root / "workspaces")
            manifest = manager.prepare("job-1", source)
            workspace = Path(manifest["workspace"])
            self.assertTrue((workspace / "app.py").exists())
            self.assertFalse((workspace / ".git").exists())

    def test_safe_environment_does_not_copy_secrets(self):
        safe = WorkspaceManager.safe_environment(source={"PATH": "/bin", "SECRET": "hidden", "HOME": "/tmp"})
        self.assertNotIn("SECRET", safe)
        self.assertEqual(safe["BASALT_NETWORK_POLICY"], "deny")

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = make_repo(root)
            (source / "link").symlink_to(source / "app.py")
            with self.assertRaises(WorkspaceRuntimeError):
                WorkspaceManager(root / "workspaces").prepare("job-1", source)

    def test_source_unchanged_check(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = make_repo(root)
            manager = WorkspaceManager(root / "workspaces")
            manifest = manager.prepare("job-1", source)
            self.assertTrue(manager.verify_source_unchanged(manifest))
            (source / "app.py").write_text("changed=True\n")
            self.assertFalse(manager.verify_source_unchanged(manifest))

    def test_cleanup_removes_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = make_repo(root)
            manager = WorkspaceManager(root / "workspaces")
            manager.prepare("job-1", source)
            manager.cleanup("job-1")
            self.assertFalse((root / "workspaces" / "job-1").exists())

    def test_file_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = make_repo(root)
            profile = SandboxProfile(name="tiny", max_files=1)
            with self.assertRaises(WorkspaceRuntimeError):
                WorkspaceManager(root / "workspaces").prepare("job-1", source, profile)


class DeploymentManagerTests(unittest.TestCase):
    def test_unverified_product_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = make_repo(root)
            manager = DeploymentManager(root / "deploy.db", root / "artifacts")
            with self.assertRaises(DeploymentError):
                manager.package_verified_product("p1", source, write_verified_proof(root, status="NOT_VERIFIED"), "preview", "u1")

    def test_preview_can_be_packaged_and_promoted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = make_repo(root)
            manager = DeploymentManager(root / "deploy.db", root / "artifacts")
            record = manager.package_verified_product("p1", source, write_verified_proof(root), "preview", "u1")
            self.assertEqual(record.status, DeploymentStatus.PACKAGED)
            promoted = manager.promote(record.deployment_id, "u1")
            self.assertEqual(promoted.status, DeploymentStatus.PROMOTED)

    def test_staging_requires_approval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = make_repo(root)
            manager = DeploymentManager(root / "deploy.db", root / "artifacts")
            record = manager.package_verified_product("p1", source, write_verified_proof(root), "staging", "u1")
            with self.assertRaises(DeploymentError):
                manager.promote(record.deployment_id, "u1")
            approved = manager.approve(record.deployment_id, "reviewer", "proof reviewed")
            self.assertEqual(manager.promote(approved.deployment_id, "reviewer").status, DeploymentStatus.PROMOTED)

    def test_production_requires_approval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = make_repo(root)
            manager = DeploymentManager(root / "deploy.db", root / "artifacts")
            record = manager.package_verified_product("p1", source, write_verified_proof(root), "production", "u1")
            self.assertEqual(record.status, DeploymentStatus.AWAITING_APPROVAL)

    def test_promoted_deployment_can_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = make_repo(root)
            manager = DeploymentManager(root / "deploy.db", root / "artifacts")
            record = manager.package_verified_product("p1", source, write_verified_proof(root), "preview", "u1")
            manager.promote(record.deployment_id, "u1")
            rolled = manager.rollback(record.deployment_id, "u1", "regression")
            self.assertEqual(rolled.status, DeploymentStatus.ROLLED_BACK)

    def test_restore_checks_artifact_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = make_repo(root)
            manager = DeploymentManager(root / "deploy.db", root / "artifacts")
            record = manager.package_verified_product("p1", source, write_verified_proof(root), "preview", "u1")
            Path(record.artifact_path).write_bytes(b"tampered")
            with self.assertRaises(DeploymentError):
                manager.restore_artifact(record.deployment_id, root / "restore")

    def test_restore_verified_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = make_repo(root)
            manager = DeploymentManager(root / "deploy.db", root / "artifacts")
            record = manager.package_verified_product("p1", source, write_verified_proof(root), "preview", "u1")
            restored = manager.restore_artifact(record.deployment_id, root / "restore")
            self.assertTrue(any(restored.rglob("app.py")))


class PrivateBetaPlatformTests(unittest.TestCase):
    def _platform_project(self, root: Path):
        platform = PrivateBetaPlatform(root / "beta")
        bootstrap = platform.bootstrap("owner@example.com", "Owner", "Basalt Team")
        project = platform.add_project(bootstrap["team"]["team_id"], "Demo", make_repo(root), bootstrap["user"]["user_id"])
        return platform, bootstrap, project

    def test_bootstrap_and_project_registration(self):
        with tempfile.TemporaryDirectory() as td:
            platform, _, project = self._platform_project(Path(td))
            self.assertEqual(platform.snapshot()["workspace"]["counts"]["projects"], 1)
            self.assertEqual(project["status"], "ACTIVE")

    def test_verify_job_runs_in_durable_queue(self):
        with tempfile.TemporaryDirectory() as td:
            platform, bootstrap, project = self._platform_project(Path(td))
            job = platform.submit_job(project["project_id"], "VERIFY_PROJECT", {"sandbox": "temp"}, bootstrap["user"]["user_id"])
            result = platform.run_job(job["job_id"])
            self.assertEqual(result["status"], "SUCCEEDED")
            self.assertEqual(result["result"]["status"], "VERIFIED")

    def test_factory_plan_job(self):
        with tempfile.TemporaryDirectory() as td:
            platform, bootstrap, project = self._platform_project(Path(td))
            job = platform.submit_job(project["project_id"], "FACTORY_PLAN", {
                "prompt": "Build an authenticated team dashboard with an API and notifications.",
                "name": "Team Control",
                "template": "saas-starter",
            }, bootstrap["user"]["user_id"])
            result = platform.run_job(job["job_id"])
            self.assertEqual(result["status"], "SUCCEEDED")
            self.assertEqual(result["result"]["epochs"], 5)

    def test_factory_create_job_writes_outside_source_repository(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            platform, bootstrap, project = self._platform_project(root)
            source = Path(project["repo_path"]).resolve()
            job = platform.submit_job(project["project_id"], "FACTORY_CREATE", {
                "prompt": "Build an authenticated multi-tenant dashboard with roles, subscriptions, and an API.",
                "name": "Private Beta Product",
                "template": "saas-starter",
                "sandbox": "temp",
            }, bootstrap["user"]["user_id"])
            result = platform.run_job(job["job_id"])
            self.assertEqual(result["status"], "SUCCEEDED")
            target = Path(result["result"]["target"]).resolve()
            self.assertNotEqual(target, source)
            self.assertNotIn(source, target.parents)
            self.assertEqual(result["result"]["proof_status"], "VERIFIED")

    def test_package_preview_defaults_to_registered_project_and_factory_proof(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            platform, bootstrap, project = self._platform_project(root)
            source = Path(project["repo_path"]).resolve()

            proof_dir = source / ".basalt" / "factory-proof"
            proof_dir.mkdir(parents=True, exist_ok=True)
            write_verified_proof(proof_dir)

            job = platform.submit_job(
                project["project_id"],
                "PACKAGE_PREVIEW",
                {},
                bootstrap["user"]["user_id"],
            )
            result = platform.run_job(job["job_id"])

            self.assertEqual(result["status"], "SUCCEEDED")
            self.assertEqual(result["result"]["status"], "PROMOTED")
            self.assertEqual(result["result"]["proof_status"], "VERIFIED")
            self.assertEqual(result["result"]["proof_score"], 98)
            self.assertEqual(
                Path(result["result"]["source_path"]).resolve(),
                source,
            )

    def test_snapshot_declares_beta_boundaries(self):
        with tempfile.TemporaryDirectory() as td:
            platform = PrivateBetaPlatform(Path(td) / "beta")
            readiness = platform.snapshot()["readiness"]
            self.assertTrue(readiness["durable_jobs"])
            self.assertFalse(readiness["production_cloud_deployments"])


@contextlib.contextmanager
def running_command_center(repo: Path, allow_actions: bool = False, token: str = "phase6-token"):
    server = create_command_center_server(repo, host="127.0.0.1", port=0, allow_actions=allow_actions, action_token=token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def request(server, method: str, path: str, body: dict | None = None, token: str | None = None):
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
    data = json.loads(raw.decode()) if "json" in content_type else raw
    connection.close()
    return response.status, data


class Phase6CommandCenterTests(unittest.TestCase):
    def test_overview_marks_phase6_active(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            overview = CommandCenterService(repo).overview()
            self.assertEqual(overview["roadmap"][5]["status"], "COMPLETE")
            self.assertEqual(overview["roadmap"][6]["status"], "ACTIVE")
            self.assertIn("private_beta", overview)

    def test_beta_state_is_readable_in_read_only_mode(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_command_center(repo) as server:
                status, data = request(server, "GET", "/api/v1/beta")
                self.assertEqual(status, 200)
                self.assertIn("readiness", data)

    def test_beta_bootstrap_requires_actions(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_command_center(repo) as server:
                status, data = request(server, "POST", "/api/v1/beta/bootstrap", {
                    "email": "owner@example.com", "display_name": "Owner", "team_name": "Team"
                })
                self.assertEqual(status, 403)
                self.assertEqual(data["error"]["code"], "ACTIONS_DISABLED")

    def test_beta_bootstrap_uses_action_token(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_command_center(repo, allow_actions=True) as server:
                status, data = request(server, "POST", "/api/v1/beta/bootstrap", {
                    "email": "owner@example.com", "display_name": "Owner", "team_name": "Team"
                }, token="phase6-token")
                self.assertEqual(status, 200)
                self.assertIn("team", data)

    def test_approval_center_includes_pending_deployment_decisions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = make_repo(root, "control")
            product = make_repo(root, "product")
            service = CommandCenterService(repo)
            platform = service.private_beta()

            bootstrap = platform.bootstrap(
                "owner@example.com",
                "Owner",
                "Basalt Team",
            )
            project = platform.add_project(
                bootstrap["team"]["team_id"],
                "Product",
                product,
                bootstrap["user"]["user_id"],
            )

            deployment = platform.deployments.package_verified_product(
                project["project_id"],
                product,
                write_verified_proof(root),
                "staging",
                bootstrap["user"]["user_id"],
            )

            overview = service.overview()
            self.assertEqual(overview["approvals"]["pending"], 1)

            item = overview["approvals"]["items"][0]
            self.assertEqual(item["kind"], "deployment")
            self.assertEqual(item["deployment_id"], deployment.deployment_id)
            self.assertEqual(item["action"], "approve")
            self.assertEqual(item["status"], "AWAITING_APPROVAL")

            platform.deployments.approve(
                deployment.deployment_id,
                "reviewer",
                "Proof and checksum reviewed.",
            )

            approved_overview = service.overview()
            self.assertEqual(approved_overview["approvals"]["pending"], 1)
            self.assertEqual(
                approved_overview["approvals"]["items"][0]["action"],
                "promote",
            )
            self.assertEqual(
                approved_overview["approvals"]["items"][0]["status"],
                "APPROVED",
            )

    def test_command_center_can_approve_and_promote_deployment(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = make_repo(root, "control")
            product = make_repo(root, "product")
            service = CommandCenterService(repo)
            platform = service.private_beta()

            bootstrap = platform.bootstrap(
                "owner@example.com",
                "Owner",
                "Basalt Team",
            )
            project = platform.add_project(
                bootstrap["team"]["team_id"],
                "Product",
                product,
                bootstrap["user"]["user_id"],
            )

            deployment = platform.deployments.package_verified_product(
                project["project_id"],
                product,
                write_verified_proof(root),
                "staging",
                bootstrap["user"]["user_id"],
            )

            with running_command_center(repo, allow_actions=True) as server:
                status, data = request(
                    server,
                    "POST",
                    f"/api/v1/beta/deployments/{deployment.deployment_id}/approve",
                    {
                        "actor": "Release Reviewer",
                        "reason": "Proof and artifact integrity reviewed.",
                    },
                    token="phase6-token",
                )
                self.assertEqual(status, 200)
                self.assertEqual(data["status"], "APPROVED")
                self.assertEqual(data["approved_by"], "Release Reviewer")

                status, data = request(
                    server,
                    "POST",
                    f"/api/v1/beta/deployments/{deployment.deployment_id}/promote",
                    {"actor": "Release Reviewer"},
                    token="phase6-token",
                )
                self.assertEqual(status, 200)
                self.assertEqual(data["status"], "PROMOTED")
                self.assertTrue(data["promoted_at"])

    def test_command_center_factory_build_writes_outside_source_repository(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            service = CommandCenterService(repo)
            run = service.factory_plan(
                "Build a booking platform with authentication, notifications, and a dashboard.",
                "Venue Core",
                "saas-starter",
                ["venue owners", "customers"],
                ["no production secrets", "local verification only"],
                "local",
            )
            result = service.factory_build(run["run_id"])
            target = Path(result["target_path"]).resolve()
            self.assertEqual(result["status"], "VERIFIED")
            self.assertNotEqual(target, repo.resolve())
            self.assertNotIn(repo.resolve(), target.parents)
            self.assertTrue(target.exists())

    def test_command_center_unifies_factory_state_transactions(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            service = CommandCenterService(repo)
            run = service.factory_plan(
                "Build a booking platform with authentication, notifications, and a dashboard.",
                "Venue Core",
                "saas-starter",
                ["venue owners", "customers"],
                ["no production secrets", "local verification only"],
                "local",
            )
            result = service.factory_build(run["run_id"])
            overview = service.overview()
            factory_rows = [item for item in overview["transactions"]["recent"] if item.get("kind") == "factory"]
            self.assertEqual(result["status"], "VERIFIED")
            self.assertEqual(overview["transactions"]["total"], 1)
            self.assertEqual(len(factory_rows), 1)
            self.assertEqual(factory_rows[0]["status"], "COMMITTED")
            self.assertEqual(factory_rows[0]["base_version"], 0)
            self.assertEqual(factory_rows[0]["result_version"], 1)
            self.assertEqual(factory_rows[0]["run_id"], run["run_id"])
            self.assertFalse(factory_rows[0]["rollback_available"])

    def test_brand_asset_is_served(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            with running_command_center(repo) as server:
                status, data = request(server, "GET", "/assets/brand/basalt-wordmark-dark.png")
                self.assertEqual(status, 200)
                self.assertIsInstance(data, bytes)
                self.assertTrue(data.startswith(b"\x89PNG"))


class Phase6FactoryAndCliTests(unittest.TestCase):
    def test_supported_templates_are_expanded(self):
        self.assertTrue({"api-service", "web-app", "saas-starter"}.issubset(SUPPORTED_TEMPLATES))

    def test_saas_starter_is_verified_before_assembly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = make_repo(root)
            target = root / "product"
            run = create_product(
                repo,
                "Build an authenticated multi-tenant team dashboard with subscription controls and an API.",
                "Private Beta SaaS",
                target,
                template="saas-starter",
                sandbox="temp",
            )
            self.assertEqual(run.status.value, "VERIFIED")
            self.assertTrue((target / "app" / "tenancy.py").exists())
            self.assertTrue((target / "tests" / "test_saas_foundation.py").exists())

    def test_beta_cli_bootstrap_and_status(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_repo(Path(td))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["beta", "bootstrap", str(repo), "--email", "owner@example.com", "--name", "Owner", "--team", "Team", "--json"])
            self.assertEqual(code, 0)
            bootstrap = json.loads(output.getvalue())
            status_output = io.StringIO()
            with contextlib.redirect_stdout(status_output):
                status_code = main(["beta", "status", str(repo), "--json"])
            self.assertEqual(status_code, 0)
            self.assertEqual(json.loads(status_output.getvalue())["workspace"]["counts"]["teams"], 1)
            self.assertIn("team_id", bootstrap["team"])


if __name__ == "__main__":
    unittest.main()
