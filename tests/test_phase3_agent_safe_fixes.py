from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from basalt_proof.agent_runtime import (
    AgentRunError,
    apply_agent_run,
    approve_agent_run,
    load_agent_run,
    plan_agent_fix,
    revise_agent_run,
    rollback_agent_run,
)
from basalt_proof.cli import main
from basalt_proof.models import (
    AgentRunStatus,
    BasaltConfig,
    ImpactAnalysis,
    PolicyVerdict,
)
from basalt_proof.patch_engine import (
    PatchError,
    apply_patch,
    create_backup,
    parse_unified_diff,
    patch_stats,
    restore_backup,
    validate_patch_applies,
)
from basalt_proof.policy_kernel import evaluate_patch_policy


MODIFY_ADD_PATCH = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def add(a: int, b: int) -> int:
-    return a + b
+    return int(a + b)
"""

BREAK_ADD_PATCH = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def add(a: int, b: int) -> int:
-    return a + b
+    return a - b
"""

SECOND_ADD_PATCH = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def add(a: int, b: int) -> int:
-    return a + b
+    return (a + b)
"""


class Phase3FixtureMixin:
    def write_good_fixture(self, root: Path, *, max_attempts: int = 3) -> None:
        tests = root / "tests"
        tests.mkdir(parents=True, exist_ok=True)
        (root / "app.py").write_text(
            "def add(a: int, b: int) -> int:\n"
            "    return a + b\n\n"
            "def is_adult(age: int) -> bool:\n"
            "    return age >= 18\n",
            encoding="utf-8",
        )
        (tests / "test_app.py").write_text(
            "import unittest\n"
            "from app import add, is_adult\n\n"
            "class AppTests(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        self.assertEqual(add(2, 3), 5)\n\n"
            "    def test_boundary(self):\n"
            "        self.assertTrue(is_adult(18))\n"
            "        self.assertFalse(is_adult(17))\n",
            encoding="utf-8",
        )
        (root / "basalt.yaml").write_text(
            "project:\n  name: phase3-good\n  type: python\n"
            "commands:\n  lint: python -m compileall app.py tests\n"
            "  test: python -m unittest discover -s tests -v\n"
            "proof:\n  require_lint: true\n  require_tests: true\n"
            "  mutation_sample: false\n  scan_exclude: fixtures\n"
            "policy:\n  block_secrets: true\n  block_destructive_migrations: true\n"
            "sandbox:\n  mode: temp\n"
            "knowledge_graph:\n  auto_refresh: true\n"
            "context:\n  token_budget: 2000\n"
            "agents:\n  enabled: true\n  max_files: 4\n  max_changed_lines: 100\n"
            f"  max_attempts: {max_attempts}\n"
            "  require_human_approval_for_source: true\n"
            "  allow_test_only_auto_apply: false\n"
            "  protected_paths: .github/workflows,.env,infra,deploy\n"
            "  allowed_roles: ImplementationAgent,TestingAgent,BackendAgent,DatabaseAgent,DocumentationAgent\n",
            encoding="utf-8",
        )

    def write_weak_fixture(self, root: Path) -> None:
        tests = root / "tests"
        tests.mkdir(parents=True, exist_ok=True)
        (root / "app.py").write_text(
            "def is_adult(age: int) -> bool:\n"
            "    return age >= 18\n",
            encoding="utf-8",
        )
        (tests / "test_app.py").write_text(
            "import unittest\n"
            "from app import is_adult\n\n"
            "class AppTests(unittest.TestCase):\n"
            "    def test_adult(self):\n"
            "        self.assertTrue(is_adult(20))\n",
            encoding="utf-8",
        )
        (root / "basalt.yaml").write_text(
            "project:\n  name: phase3-weak\n  type: python\n"
            "commands:\n  lint: python -m compileall app.py tests\n"
            "  test: python -m unittest discover -s tests -v\n"
            "proof:\n  require_lint: true\n  require_tests: true\n"
            "  mutation_sample: true\n  mutation_max: 1\n  mutation_per_file: 1\n"
            "  mutation_include: app.py\n"
            "  mutation_test_command: python -m unittest discover -s tests -v\n"
            "policy:\n  block_secrets: true\n  block_destructive_migrations: true\n"
            "sandbox:\n  mode: temp\n"
            "knowledge_graph:\n  auto_refresh: true\n"
            "context:\n  token_budget: 2000\n"
            "agents:\n  enabled: true\n  max_files: 4\n  max_changed_lines: 100\n"
            "  max_attempts: 3\n  require_human_approval_for_source: true\n"
            "  allow_test_only_auto_apply: false\n"
            "  allowed_roles: ImplementationAgent,TestingAgent\n",
            encoding="utf-8",
        )

    def write_patch(self, root: Path, text: str, name: str = "candidate.patch") -> Path:
        path = root / name
        path.write_text(text, encoding="utf-8")
        return path


class PatchEngineTests(Phase3FixtureMixin, unittest.TestCase):
    def test_parse_and_measure_modification(self) -> None:
        changes = parse_unified_diff(MODIFY_ADD_PATCH)
        stats = patch_stats(changes)
        self.assertEqual(stats.files_changed, 1)
        self.assertEqual(stats.additions, 1)
        self.assertEqual(stats.deletions, 1)
        self.assertFalse(stats.test_only)

    def test_add_file_backup_apply_and_restore(self) -> None:
        patch = """--- /dev/null
+++ b/tests/test_extra.py
@@ -0,0 +1,2 @@
+def test_truth():
+    assert True
"""
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            changes = parse_unified_diff(patch)
            backup = repo / ".basalt" / "backup"
            create_backup(repo, changes, backup)
            apply_patch(repo, changes)
            self.assertTrue((repo / "tests/test_extra.py").exists())
            restore_backup(repo, backup)
            self.assertFalse((repo / "tests/test_extra.py").exists())

    def test_path_traversal_is_rejected(self) -> None:
        patch = """--- /dev/null
+++ b/../escape.py
@@ -0,0 +1 @@
+BAD = True
"""
        with self.assertRaises(PatchError):
            parse_unified_diff(patch)

    def test_binary_patch_is_rejected(self) -> None:
        with self.assertRaises(PatchError):
            parse_unified_diff("GIT binary patch\nliteral 1\nA\n")

    def test_stale_patch_is_rejected_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
            patch = """--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-VALUE = 1
+VALUE = 3
"""
            with self.assertRaises(PatchError):
                validate_patch_applies(repo, parse_unified_diff(patch))
            self.assertEqual((repo / "app.py").read_text(encoding="utf-8"), "VALUE = 2\n")


class PolicyKernelTests(unittest.TestCase):
    def decision(self, patch: str, role: str, **kwargs):
        config = BasaltConfig(project_name="policy", **kwargs)
        changes = parse_unified_diff(patch)
        impact = [ImpactAnalysis(target="app.py", found=True, risk_level="LOW")]
        return evaluate_patch_policy(config, role, changes, impact, "state", "state")

    def test_testing_agent_test_patch_requires_human_by_default(self) -> None:
        patch = """--- /dev/null
+++ b/tests/test_more.py
@@ -0,0 +1 @@
+assert True
"""
        decision = self.decision(patch, "TestingAgent")
        self.assertEqual(decision.verdict, PolicyVerdict.REQUIRE_HUMAN_APPROVAL)
        self.assertTrue(decision.patch_stats.test_only)

    def test_testing_agent_cannot_modify_source(self) -> None:
        decision = self.decision(MODIFY_ADD_PATCH, "TestingAgent")
        self.assertEqual(decision.verdict, PolicyVerdict.BLOCK)
        self.assertIn("capability_scope_violation", decision.risk_flags)

    def test_read_only_review_agent_cannot_author_patch(self) -> None:
        decision = self.decision(MODIFY_ADD_PATCH, "CodeReviewAgent")
        self.assertEqual(decision.verdict, PolicyVerdict.BLOCK)

    def test_secret_introduction_is_blocked(self) -> None:
        secret_value = "abcdefghijkl" + "mnop"
        patch = (
            "--- /dev/null\n"
            "+++ b/config.py\n"
            "@@ -0,0 +1 @@\n"
            f'+api_key = "{secret_value}"\n'
        )
        decision = self.decision(patch, "ImplementationAgent")
        self.assertEqual(decision.verdict, PolicyVerdict.BLOCK)
        self.assertIn("secret_introduction", decision.risk_flags)

    def test_destructive_sql_is_blocked(self) -> None:
        patch = """--- /dev/null
+++ b/db/migration.sql
@@ -0,0 +1 @@
+DROP TABLE users;
"""
        decision = self.decision(patch, "DatabaseAgent")
        self.assertEqual(decision.verdict, PolicyVerdict.BLOCK)
        self.assertIn("destructive_migration", decision.risk_flags)

    def test_auth_change_requires_contract_locks(self) -> None:
        patch = """--- /dev/null
+++ b/auth/session.py
@@ -0,0 +1,2 @@
+def validate_session(token):
+    return bool(token)
"""
        decision = self.decision(patch, "BackendAgent")
        self.assertEqual(decision.verdict, PolicyVerdict.REQUIRE_HUMAN_APPROVAL)
        self.assertIn("AUTH_CONTRACT", decision.required_locks)
        self.assertIn("security_review", decision.required_approvals)

    def test_atomic_file_limit_is_enforced(self) -> None:
        patch = """--- /dev/null
+++ b/a.py
@@ -0,0 +1 @@
+A = 1
--- /dev/null
+++ b/b.py
@@ -0,0 +1 @@
+B = 1
"""
        decision = self.decision(patch, "ImplementationAgent", agent_max_files=1)
        self.assertEqual(decision.verdict, PolicyVerdict.BLOCK)
        self.assertIn("atomic_file_limit_exceeded", decision.risk_flags)

    def test_test_only_auto_apply_can_be_explicitly_enabled(self) -> None:
        patch = """--- /dev/null
+++ b/tests/test_more.py
@@ -0,0 +1 @@
+assert True
"""
        decision = self.decision(
            patch,
            "TestingAgent",
            agent_allow_test_only_auto_apply=True,
        )
        self.assertEqual(decision.verdict, PolicyVerdict.ALLOW)

    def test_protected_path_is_blocked(self) -> None:
        patch = """--- /dev/null
+++ b/infra/main.tf
@@ -0,0 +1 @@
+resource \"x\" \"y\" {}
"""
        decision = self.decision(
            patch,
            "DevOpsAgent",
            agent_protected_paths=["infra"],
        )
        self.assertEqual(decision.verdict, PolicyVerdict.BLOCK)
        self.assertIn("protected_path", decision.risk_flags)


class AgentRuntimeTests(Phase3FixtureMixin, unittest.TestCase):
    def test_built_in_weak_proof_plan_creates_governed_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_weak_fixture(repo)
            run = plan_agent_fix(
                repo,
                "Strengthen boundary proof",
                agent_role="TestingAgent",
                targets=["app.py"],
                sandbox="temp",
            )
            self.assertEqual(run.status, AgentRunStatus.AWAITING_APPROVAL)
            self.assertEqual(run.policy_decision.verdict, PolicyVerdict.REQUIRE_HUMAN_APPROVAL)
            run_dir = repo / ".basalt" / "agent-runs" / run.run_id
            self.assertTrue((run_dir / "candidate.patch").exists())
            self.assertTrue((run_dir / "patch-proposal.json").exists())
            self.assertTrue((run_dir / "policy-decision.json").exists())

    def test_approval_token_is_hashed_and_one_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_good_fixture(repo)
            patch = self.write_patch(repo, MODIFY_ADD_PATCH)
            run = plan_agent_fix(repo, "Safe source edit", patch_file=patch, sandbox="temp")
            approved, token = approve_agent_run(repo, run.run_id, "Amogh", "Reviewed patch")
            self.assertEqual(approved.status, AgentRunStatus.APPROVED)
            state_text = (repo / ".basalt" / "agent-runs" / run.run_id / "run.json").read_text()
            self.assertNotIn(token, state_text)
            with self.assertRaises(AgentRunError):
                apply_agent_run(repo, run.run_id, "wrong-token", sandbox="temp")

    def test_successful_patch_becomes_verified_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_good_fixture(repo)
            patch = self.write_patch(repo, MODIFY_ADD_PATCH)
            run = plan_agent_fix(repo, "Keep addition typed", patch_file=patch, sandbox="temp")
            _, token = approve_agent_run(repo, run.run_id, "Amogh", "Proof scope reviewed")
            result = apply_agent_run(repo, run.run_id, token, sandbox="temp")
            self.assertEqual(result.status, AgentRunStatus.VERIFIED)
            self.assertTrue(result.verification_delta.accepted)
            self.assertNotEqual(result.base_state_hash, result.current_state_hash)
            self.assertIn("return int(a + b)", (repo / "app.py").read_text())
            transaction = json.loads(
                (repo / ".basalt" / "agent-runs" / run.run_id / "state-transaction.json").read_text()
            )
            self.assertTrue(transaction["proof_accepted"])

    def test_weak_proof_fix_is_verified_and_improves_score(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_weak_fixture(repo)
            run = plan_agent_fix(repo, "Kill survived boundary mutation", agent_role="TestingAgent", sandbox="temp")
            _, token = approve_agent_run(repo, run.run_id, "Amogh", "Generated tests reviewed")
            result = apply_agent_run(repo, run.run_id, token, sandbox="temp")
            self.assertEqual(result.status, AgentRunStatus.VERIFIED)
            self.assertGreater(result.verification_delta.after_score, result.verification_delta.before_score)
            self.assertEqual(result.verification_delta.after_survived_mutations, 0)

    def test_stale_repository_state_prevents_apply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_good_fixture(repo)
            patch = self.write_patch(repo, MODIFY_ADD_PATCH)
            run = plan_agent_fix(repo, "Safe edit", patch_file=patch, sandbox="temp")
            _, token = approve_agent_run(repo, run.run_id, "Amogh", "Reviewed")
            (repo / "new_file.py").write_text("VALUE = 1\n", encoding="utf-8")
            result = apply_agent_run(repo, run.run_id, token, sandbox="temp")
            self.assertEqual(result.status, AgentRunStatus.STALE_STATE)
            self.assertIn("return a + b", (repo / "app.py").read_text())

    def test_proof_regression_is_automatically_rolled_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_good_fixture(repo)
            patch = self.write_patch(repo, BREAK_ADD_PATCH)
            run = plan_agent_fix(repo, "Bad implementation experiment", patch_file=patch, sandbox="temp")
            _, token = approve_agent_run(repo, run.run_id, "Amogh", "Exercise rollback")
            result = apply_agent_run(repo, run.run_id, token, sandbox="temp")
            self.assertEqual(result.status, AgentRunStatus.ROLLED_BACK)
            self.assertTrue(result.rollback_performed)
            self.assertFalse(result.verification_delta.accepted)
            self.assertIn("return a + b", (repo / "app.py").read_text())

    def test_verified_transaction_can_be_manually_rolled_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_good_fixture(repo)
            patch = self.write_patch(repo, MODIFY_ADD_PATCH)
            run = plan_agent_fix(repo, "Safe edit", patch_file=patch, sandbox="temp")
            _, token = approve_agent_run(repo, run.run_id, "Amogh", "Reviewed")
            applied = apply_agent_run(repo, run.run_id, token, sandbox="temp")
            self.assertEqual(applied.status, AgentRunStatus.VERIFIED)
            rolled = rollback_agent_run(repo, run.run_id, "Amogh", "Revert experiment")
            self.assertEqual(rolled.status, AgentRunStatus.ROLLED_BACK)
            self.assertIn("return a + b", (repo / "app.py").read_text())
            self.assertNotIn("return int(a + b)", (repo / "app.py").read_text())

    def test_loop_governor_detects_repeated_patch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_good_fixture(repo)
            patch = self.write_patch(repo, MODIFY_ADD_PATCH)
            run = plan_agent_fix(repo, "Safe edit", patch_file=patch, sandbox="temp")
            result = revise_agent_run(repo, run.run_id, patch)
            self.assertEqual(result.status, AgentRunStatus.STUCK)
            self.assertIn("repeated", result.message)

    def test_loop_governor_enforces_attempt_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_good_fixture(repo, max_attempts=1)
            first = self.write_patch(repo, MODIFY_ADD_PATCH, "first.patch")
            second = self.write_patch(repo, SECOND_ADD_PATCH, "second.patch")
            run = plan_agent_fix(repo, "Safe edit", patch_file=first, sandbox="temp")
            result = revise_agent_run(repo, run.run_id, second)
            self.assertEqual(result.status, AgentRunStatus.STUCK)
            self.assertIn("attempts", result.message)

    def test_run_state_can_be_reloaded_with_agent_court(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_good_fixture(repo)
            patch = self.write_patch(repo, MODIFY_ADD_PATCH)
            run = plan_agent_fix(repo, "Safe edit", patch_file=patch, sandbox="temp")
            loaded, run_dir = load_agent_run(repo, run.run_id)
            roles = {action.agent_role for action in loaded.agent_actions}
            self.assertTrue({"PlannerAgent", "ContextCompiler", "TestingAgent", "SecurityAgent", "CodeReviewAgent"}.issubset(roles))
            self.assertTrue((run_dir / "run-summary.md").exists())
            self.assertTrue((repo / ".basalt" / "agent-runs" / "audit.jsonl").exists())


class AgentCliTests(Phase3FixtureMixin, unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(arguments)
        return code, output.getvalue()

    def test_agent_plan_and_status_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.write_good_fixture(repo)
            patch = self.write_patch(repo, MODIFY_ADD_PATCH)
            code, output = self.run_cli(
                [
                    "agent",
                    "plan",
                    str(repo),
                    "--task",
                    "Safe edit",
                    "--patch",
                    str(patch),
                    "--sandbox",
                    "temp",
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("AWAITING_APPROVAL", output)
            run_id = next(line.split(":", 1)[1].strip() for line in output.splitlines() if line.startswith("- run:"))
            code, status_output = self.run_cli(["agent", "status", str(repo), run_id])
            self.assertEqual(code, 0)
            self.assertIn(run_id, status_output)
            self.assertIn("Policy", (repo / ".basalt" / "agent-runs" / run_id / "run-summary.md").read_text())


if __name__ == "__main__":
    unittest.main()
