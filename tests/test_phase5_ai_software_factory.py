from __future__ import annotations

import contextlib
import io
import json
import tempfile
import threading
import unittest
from dataclasses import replace
from http.client import HTTPConnection
from pathlib import Path

from basalt_proof.cli import main
from basalt_proof.command_center import CommandCenterService
from basalt_proof.command_center_server import create_command_center_server
from basalt_proof.design_system import TOKENS, audit_design_system, write_design_system_artifacts
from basalt_proof.epoch_planner import (
    PatchProposalRecord,
    aggregate_patch_proposals,
    build_task_graph,
    validate_task_graph,
)
from basalt_proof.factory_models import FactoryRunStatus, FactoryTask
from basalt_proof.model_router import ModelRouter
from basalt_proof.prevention_engine import build_engineering_plan, detect_contradictions
from basalt_proof.product_brain import build_product_blueprint, validate_blueprint
from basalt_proof.software_factory import (
    FactoryError,
    build_factory_run,
    create_product,
    factory_snapshot,
    list_factory_runs,
    load_factory_run,
    plan_factory_run,
)
from basalt_proof.state_coordinator import ContractLockError, StateConflictError, StateCoordinator


def make_source_repo(root: Path) -> Path:
    repo = root / "basalt-source"
    repo.mkdir()
    (repo / "engine.py").write_text("def identity(value):\n    return value\n", encoding="utf-8")
    (repo / "basalt.yaml").write_text(
        "project:\n  name: phase5-fixture\n  type: python\n"
        "commands:\n  lint: python -m compileall engine.py\n  test: null\n"
        "proof:\n  require_lint: true\n  require_tests: false\n  mutation_sample: false\n"
        "sandbox:\n  mode: temp\n",
        encoding="utf-8",
    )
    return repo


class ProductBrainTests(unittest.TestCase):
    def test_intent_extracts_known_features(self):
        blueprint = build_product_blueprint(
            "Build a booking platform with authentication, payments, dashboards, and notifications.",
            "Arena",
            "fullstack-lite",
        )
        names = {item.name for item in blueprint.features}
        self.assertTrue({"Booking", "Authentication", "Payments", "Dashboard", "Notifications"}.issubset(names))

    def test_high_risk_features_create_governed_requirements(self):
        blueprint = build_product_blueprint("Build secure authentication and payment checkout for teams.", "Ledger")
        self.assertTrue(any(item.risk_level == "HIGH" for item in blueprint.features))
        self.assertTrue(any("governance" in item.title.lower() for item in blueprint.requirements))

    def test_blueprint_hash_is_deterministic(self):
        first = build_product_blueprint("Build a searchable API for product records.", "Catalog")
        second = build_product_blueprint("Build a searchable API for product records.", "Catalog")
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(first.blueprint_id, second.blueprint_id)

    def test_short_intent_is_rejected(self):
        with self.assertRaises(ValueError):
            build_product_blueprint("tiny", "Demo")

    def test_blueprint_validation_passes_for_generated_blueprint(self):
        blueprint = build_product_blueprint("Build an admin dashboard with API integration.", "Control")
        self.assertEqual(validate_blueprint(blueprint), [])

    def test_blueprint_has_nonfunctional_requirements_and_assumptions(self):
        blueprint = build_product_blueprint("Build a notification service for customer accounts.", "Signal")
        self.assertGreaterEqual(len(blueprint.non_functional_requirements), 4)
        self.assertTrue(any(item.risk == "HIGH" for item in blueprint.assumptions))


class PreventionFirstTests(unittest.TestCase):
    def test_auth_contract_lock_is_created(self):
        blueprint = build_product_blueprint("Build login and account management with an API.", "Identity")
        plan = build_engineering_plan(blueprint)
        locks = {item.name for item in plan.contract_locks}
        self.assertIn("AUTH_CONTRACT", locks)
        self.assertIn("API_CONTRACT", locks)
        self.assertEqual(plan.status, "LOCKED")

    def test_contradictory_auth_intent_is_blocked(self):
        blueprint = build_product_blueprint("Build login for users but use no authentication anywhere.", "Conflict")
        plan = build_engineering_plan(blueprint)
        self.assertEqual(plan.status, "BLOCKED")
        self.assertTrue(plan.contradictions)

    def test_requirement_linked_test_plan_is_complete(self):
        blueprint = build_product_blueprint("Build a booking API for customers.", "Booker")
        plan = build_engineering_plan(blueprint)
        requirement_ids = {item.id for item in blueprint.requirements + blueprint.non_functional_requirements}
        linked = {item.requirement_id for item in plan.test_plan}
        self.assertEqual(requirement_ids, linked)

    def test_design_system_decision_is_locked(self):
        blueprint = build_product_blueprint("Build a dashboard for service operations.", "Ops")
        plan = build_engineering_plan(blueprint)
        self.assertTrue(any("Basalt Obsidian" in item["decision"] for item in plan.decisions))


class EpochPlannerTests(unittest.TestCase):
    def test_task_graph_has_five_dependency_safe_epochs(self):
        blueprint = build_product_blueprint("Build booking, login, and dashboard workflows.", "Flow", "fullstack-lite")
        plan = build_engineering_plan(blueprint)
        tasks, epochs = build_task_graph(blueprint, plan)
        self.assertEqual([item.number for item in epochs], [1, 2, 3, 4, 5])
        self.assertGreaterEqual(len(tasks), 11)
        validate_task_graph(tasks)

    def test_implementation_waits_for_shared_truth(self):
        blueprint = build_product_blueprint("Build an API dashboard with authentication.", "Flow")
        plan = build_engineering_plan(blueprint)
        tasks, _ = build_task_graph(blueprint, plan)
        backend = next(item for item in tasks if item.task_id == "TASK-BE-001")
        self.assertIn("TASK-ARCH-001", backend.dependencies)
        self.assertIn("TASK-PROD-001", backend.dependencies)

    def test_cycle_is_rejected(self):
        tasks = [
            FactoryTask("A", "A", "A", "BackendAgent", 2, "Implementation", dependencies=["B"]),
            FactoryTask("B", "B", "B", "BackendAgent", 2, "Implementation", dependencies=["A"]),
        ]
        with self.assertRaises(ValueError):
            validate_task_graph(tasks)

    def test_patch_aggregator_groups_intersecting_contracts(self):
        batches = aggregate_patch_proposals(
            [
                PatchProposalRecord("p1", "t1", ["api.py"], ["API_CONTRACT"], "MEDIUM"),
                PatchProposalRecord("p2", "t2", ["ui.js"], ["API_CONTRACT"], "HIGH"),
                PatchProposalRecord("p3", "t3", ["docs.md"], [], "LOW"),
            ]
        )
        self.assertEqual(len(batches), 2)
        connected = next(item for item in batches if "p1" in item.patch_ids)
        self.assertEqual(set(connected.patch_ids), {"p1", "p2"})
        self.assertEqual(connected.risk_level, "HIGH")


class ModelRouterTests(unittest.TestCase):
    def test_local_router_selects_template_codegen_for_backend(self):
        task = FactoryTask("T", "Build", "Build", "BackendAgent", 2, "Implementation")
        assignment = ModelRouter().route(task, privacy_mode="local")
        self.assertEqual(assignment.provider, "local")
        self.assertEqual(assignment.model, "basalt-template-codegen")

    def test_high_risk_code_uses_diverse_review_family(self):
        task = FactoryTask("T", "Build", "Build", "BackendAgent", 2, "Implementation", risk_level="HIGH")
        assignment = ModelRouter().route(task, privacy_mode="local")
        self.assertTrue(assignment.diversity_enforced)
        self.assertIn("basalt-deterministic-planner", assignment.review_model)

    def test_local_privacy_never_routes_to_unconfigured_remote_model(self):
        task = FactoryTask("T", "Plan", "Plan", "ProductAgent", 1, "Shared Truth")
        assignment = ModelRouter().route(task, privacy_mode="local")
        self.assertEqual(assignment.provider, "local")

    def test_inventory_declares_provider_availability(self):
        inventory = ModelRouter().inventory()
        self.assertTrue(any(item["model"] == "basalt-deterministic-planner" and item["available"] for item in inventory))
        self.assertTrue(all("privacy_modes" in item for item in inventory))


class StateCoordinatorTests(unittest.TestCase):
    def test_bootstrap_and_commit_increment_monotonic_state(self):
        with tempfile.TemporaryDirectory() as td:
            coordinator = StateCoordinator(Path(td) / "state.sqlite3")
            initial = coordinator.bootstrap("hash0")
            coordinator.begin("run1", initial.version, "build")
            coordinator.acquire_locks(["API_CONTRACT"], "Orchestrator", "run1", initial.version)
            committed = coordinator.commit("run1", initial.version, "hash1", "verified build")
            self.assertEqual(committed.version, 1)
            self.assertEqual(coordinator.current().state_hash, "hash1")

    def test_stale_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            coordinator = StateCoordinator(Path(td) / "state.sqlite3")
            coordinator.bootstrap("hash0")
            coordinator.begin("run1", 0, "build")
            coordinator.commit("run1", 0, "hash1", "first")
            with self.assertRaises(StateConflictError):
                coordinator.commit("run2", 0, "hash2", "stale")

    def test_contract_lock_conflict_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            coordinator = StateCoordinator(Path(td) / "state.sqlite3")
            coordinator.bootstrap("hash0")
            coordinator.acquire_locks(["AUTH_CONTRACT"], "AgentA", "run-a", 0)
            with self.assertRaises(ContractLockError):
                coordinator.acquire_locks(["AUTH_CONTRACT"], "AgentB", "run-b", 0)

    def test_abort_releases_locks(self):
        with tempfile.TemporaryDirectory() as td:
            coordinator = StateCoordinator(Path(td) / "state.sqlite3")
            coordinator.bootstrap("hash0")
            coordinator.begin("run1", 0, "build")
            coordinator.acquire_locks(["API_CONTRACT"], "Agent", "run1", 0)
            coordinator.abort("run1", "failed")
            coordinator.acquire_locks(["API_CONTRACT"], "Agent2", "run2", 0)
            self.assertEqual(coordinator.snapshot()["locks"][0]["run_id"], "run2")

    def test_snapshot_contains_transactions_and_locks(self):
        with tempfile.TemporaryDirectory() as td:
            coordinator = StateCoordinator(Path(td) / "state.sqlite3")
            coordinator.bootstrap("hash0")
            coordinator.begin("run1", 0, "build")
            snap = coordinator.snapshot()
            self.assertEqual(snap["current"]["version"], 0)
            self.assertEqual(snap["transactions"][0]["status"], "OPEN")


class DesignSystemTests(unittest.TestCase):
    def test_locked_palette_has_no_lime_accent(self):
        self.assertNotEqual(TOKENS["color"]["accent"].lower(), "#d7ff4f")
        self.assertEqual(TOKENS["name"], "Basalt Obsidian")

    def test_audit_detects_legacy_lime(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "styles.css").write_text(":root { --accent: #d7ff4f; }", encoding="utf-8")
            findings = audit_design_system(repo)
            self.assertTrue(any(item.rule == "no_lime" and item.level == "HIGH" for item in findings))

    def test_design_artifacts_are_written(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            out = repo / ".basalt"
            paths = write_design_system_artifacts(repo, out)
            self.assertEqual(len(paths), 3)
            self.assertTrue((out / "basalt-design-tokens.json").exists())


class SoftwareFactoryTests(unittest.TestCase):
    def test_plan_writes_blueprint_plan_graph_and_models(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_source_repo(Path(td))
            run = plan_factory_run(repo, "Build an authenticated booking API and dashboard.", "Venue", "fullstack-lite")
            self.assertEqual(run.status, FactoryRunStatus.PLANNED)
            self.assertTrue(Path(run.blueprint_path).exists())
            self.assertTrue(Path(run.engineering_plan_path).exists())
            self.assertTrue(Path(run.task_graph_path).exists())
            self.assertEqual(len(run.epochs), 5)

    def test_contradiction_blocks_factory_plan(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_source_repo(Path(td))
            run = plan_factory_run(repo, "Build login for users but use no authentication anywhere.", "Blocked")
            self.assertEqual(run.status, FactoryRunStatus.BLOCKED)

    def test_fullstack_product_is_verified_before_assembly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = make_source_repo(root)
            target = root / "product"
            run = create_product(
                repo,
                "Build a booking platform with authentication, dashboard, notifications, and an API.",
                "Venue Core",
                target,
                template="fullstack-lite",
                sandbox="temp",
            )
            self.assertEqual(run.status, FactoryRunStatus.VERIFIED)
            self.assertEqual(run.proof_status, "VERIFIED")
            self.assertGreaterEqual(run.proof_score, 80)
            self.assertTrue((target / "app" / "service.py").exists())
            self.assertTrue((target / "web" / "styles.css").exists())
            self.assertTrue((target / ".basalt" / "factory-proof" / "proof-report.json").exists())
            self.assertNotIn("#d7ff4f", (target / "web" / "styles.css").read_text(encoding="utf-8").lower())

    def test_nonempty_target_is_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = make_source_repo(root)
            run = plan_factory_run(repo, "Build a searchable product API.", "Catalog")
            target = root / "target"
            target.mkdir()
            (target / "keep.txt").write_text("safe", encoding="utf-8")
            with self.assertRaises(FactoryError):
                build_factory_run(repo, run.run_id, target)
            self.assertEqual((target / "keep.txt").read_text(), "safe")

    def test_factory_run_can_be_reloaded_and_listed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_source_repo(Path(td))
            run = plan_factory_run(repo, "Build a profile and notification API.", "Signal")
            loaded = load_factory_run(repo, run.run_id)
            self.assertEqual(loaded.run_id, run.run_id)
            self.assertEqual(list_factory_runs(repo)[0]["run_id"], run.run_id)

    def test_stale_factory_plan_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = make_source_repo(root)
            run = plan_factory_run(repo, "Build a product search API.", "Search")
            coordinator = StateCoordinator(repo / ".basalt" / "factory-state.sqlite3")
            coordinator.begin("external", 0, "other change")
            coordinator.commit("external", 0, "new-state", "other verified change")
            with self.assertRaises(FactoryError):
                build_factory_run(repo, run.run_id, root / "target")
            self.assertEqual(load_factory_run(repo, run.run_id).status, FactoryRunStatus.BLOCKED)


class FactoryCliTests(unittest.TestCase):
    def test_factory_plan_and_status_cli(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_source_repo(Path(td))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["factory", "plan", str(repo), "--prompt", "Build an API dashboard for teams.", "--name", "Team Ops", "--json"])
            self.assertEqual(code, 0)
            run = json.loads(output.getvalue())
            status_output = io.StringIO()
            with contextlib.redirect_stdout(status_output):
                status_code = main(["factory", "status", str(repo), run["run_id"], "--json"])
            self.assertEqual(status_code, 0)
            self.assertEqual(json.loads(status_output.getvalue())["status"], "PLANNED")

    def test_factory_models_cli(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["factory", "models", ".", "--json"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue()))


@contextlib.contextmanager
def running_server(repo: Path, allow_actions: bool = False, token: str = "phase5-token"):
    server = create_command_center_server(repo, host="127.0.0.1", port=0, allow_actions=allow_actions, action_token=token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


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
    data = json.loads(response.read().decode("utf-8"))
    connection.close()
    return response.status, data


class Phase5CommandCenterTests(unittest.TestCase):
    def test_overview_marks_phase5_complete_in_private_beta(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_source_repo(Path(td))
            overview = CommandCenterService(repo).overview()
            self.assertEqual(overview["roadmap"][4]["status"], "COMPLETE")
            self.assertEqual(overview["roadmap"][5]["status"], "COMPLETE")
            self.assertIn("factory", overview)

    def test_factory_api_is_readable_but_planning_requires_actions(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_source_repo(Path(td))
            with running_server(repo) as server:
                status, data = request(server, "GET", "/api/v1/factory")
                self.assertEqual(status, 200)
                self.assertIn("models", data)
                status, data = request(server, "POST", "/api/v1/factory/plan", {"name": "Demo", "prompt": "Build an API dashboard for teams."})
                self.assertEqual(status, 403)
                self.assertEqual(data["error"]["code"], "ACTIONS_DISABLED")

    def test_factory_plan_endpoint_uses_action_token(self):
        with tempfile.TemporaryDirectory() as td:
            repo = make_source_repo(Path(td))
            with running_server(repo, allow_actions=True) as server:
                status, data = request(
                    server,
                    "POST",
                    "/api/v1/factory/plan",
                    {"name": "Demo", "prompt": "Build an API dashboard for team operations.", "template": "python-service"},
                    token="phase5-token",
                )
                self.assertEqual(status, 200)
                self.assertEqual(data["status"], "PLANNED")
                run_id = data["run_id"]
                status, detail = request(server, "GET", f"/api/v1/factory/runs/{run_id}")
                self.assertEqual(status, 200)
                self.assertEqual(detail["run_id"], run_id)


if __name__ == "__main__":
    unittest.main()
