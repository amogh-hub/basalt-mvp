from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from basalt_proof.ast_graph import build_knowledge_graph
from basalt_proof.config import infer_commands, infer_project_type, load_config
from basalt_proof.models import CheckStatus, CommandResult, CommandSpec
from basalt_proof.mutation import _python_candidates, run_mutation_sample
from basalt_proof.proof import verify_repo
from basalt_proof.runner import CommandExecutor, is_command_allowed
from basalt_proof.security import scan_repo


class ProjectDetectionTests(unittest.TestCase):
    def test_fastapi_project_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "app.py").write_text(
                "from fastapi import FastAPI\napp = FastAPI()\n",
                encoding="utf-8",
            )
            self.assertEqual(infer_project_type(repo), "fastapi")

    def test_vite_react_project_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "package.json").write_text(
                json.dumps(
                    {
                        "dependencies": {"react": "^19.0.0"},
                        "devDependencies": {"vite": "^7.0.0"},
                        "scripts": {"build": "vite build", "test": "node --test"},
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(infer_project_type(repo), "vite-react")

    def test_next_project_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "package.json").write_text(
                json.dumps({"dependencies": {"next": "^16.0.0", "react": "^19.0.0"}}),
                encoding="utf-8",
            )
            self.assertEqual(infer_project_type(repo), "nextjs")

    def test_node_lockfile_uses_npm_ci(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "package.json").write_text(
                json.dumps({"scripts": {"test": "node --test"}}),
                encoding="utf-8",
            )
            (repo / "package-lock.json").write_text("{}\n", encoding="utf-8")
            commands = infer_commands(repo, "node")
            self.assertEqual(commands["install"], "npm ci")
            self.assertEqual(commands["test"], "npm run test")

    def test_default_config_prefers_auto_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            config = load_config(repo)
            self.assertEqual(config.sandbox, "auto")
            self.assertTrue(config.docker_fallback)
            self.assertEqual(config.docker_image, "python:3.13-slim")


class SandboxTests(unittest.TestCase):
    def test_auto_sandbox_falls_back_safely(self) -> None:
        with patch("basalt_proof.runner.docker_status", return_value=(False, "daemon unavailable")):
            executor = CommandExecutor(sandbox="auto", fallback_to_temp=True)
        self.assertEqual(executor.effective_sandbox, "temp-fallback")
        self.assertEqual(executor.fallback_reason, "daemon unavailable")

    def test_required_docker_can_fail_closed(self) -> None:
        with patch("basalt_proof.runner.docker_status", return_value=(False, "not installed")):
            executor = CommandExecutor(sandbox="docker", fallback_to_temp=False)
        result = executor.run(CommandSpec("test", "python -m unittest", required=True), Path("."))
        self.assertEqual(result.status, CheckStatus.FAIL)
        self.assertIn("required but unavailable", result.message)

    def test_docker_command_uses_no_network_for_tests(self) -> None:
        completed = type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "ok", "stderr": ""},
        )()
        with patch("basalt_proof.runner.docker_status", return_value=(True, "27.0")):
            executor = CommandExecutor(sandbox="auto", docker_image="python:3.13-slim")
        with patch("basalt_proof.runner.subprocess.run", return_value=completed) as mocked:
            result = executor.run(
                CommandSpec("test", "python -m unittest", required=True, allow_network=False),
                Path("."),
            )
        docker_command = mocked.call_args.args[0]
        self.assertEqual(result.status, CheckStatus.PASS)
        self.assertIn("--network", docker_command)
        self.assertEqual(docker_command[docker_command.index("--network") + 1], "none")
        self.assertIn("no-new-privileges", docker_command)

    def test_dangerous_shell_command_is_blocked(self) -> None:
        allowed, reason = is_command_allowed("python -m unittest && sudo reboot")
        self.assertFalse(allowed)
        self.assertIn("dangerous token", reason.lower())


class SecurityAndDependencyTests(unittest.TestCase):
    def test_node_latest_dependency_is_medium(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "package.json").write_text(
                json.dumps({"dependencies": {"example": "latest"}}),
                encoding="utf-8",
            )
            findings = scan_repo(repo)
            self.assertTrue(
                any(
                    item.rule == "unpinned_node_dependency" and item.level == "MEDIUM"
                    for item in findings
                )
            )

    def test_pyproject_dependency_hygiene_is_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "pyproject.toml").write_text(
                '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["fastapi"]\n',
                encoding="utf-8",
            )
            findings = scan_repo(repo)
            rules = {item.rule for item in findings}
            self.assertIn("unbounded_pyproject_dependency", rules)
            self.assertIn("missing_python_lockfile", rules)

    def test_write_all_workflow_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            workflow = repo / ".github" / "workflows"
            workflow.mkdir(parents=True)
            (workflow / "danger.yml").write_text(
                "name: danger\npermissions: write-all\n",
                encoding="utf-8",
            )
            findings = scan_repo(repo)
            self.assertTrue(
                any(item.rule == "workflow_write_all" and item.level == "HIGH" for item in findings)
            )


class MutationEngineTests(unittest.TestCase):
    def test_python_engine_generates_multiple_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.py"
            path.write_text(
                "def eligible(age):\n    return age >= 18\n\ndef total(a, b):\n    return a + b\n",
                encoding="utf-8",
            )
            candidates = _python_candidates(path, per_file=3)
            self.assertGreaterEqual(len(candidates), 2)
            self.assertEqual(candidates[0].original, "GtE")
            self.assertEqual(candidates[0].replacement, "Gt")

    def test_mutation_sampling_respects_maximum(self) -> None:
        class AlwaysKilledExecutor:
            def run(self, spec, cwd):
                return CommandResult(
                    name=spec.name,
                    command=spec.command,
                    status=CheckStatus.FAIL,
                )

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "policy.py").write_text(
                "def eligible(age):\n    return age >= 18\n\ndef total(a, b):\n    return a + b\n",
                encoding="utf-8",
            )
            results = run_mutation_sample(
                repo,
                CommandSpec("test", "python -m unittest", required=True),
                executor=AlwaysKilledExecutor(),
                max_mutations=2,
                per_file=3,
            )
            self.assertEqual(len(results), 2)
            self.assertTrue(all(not item.survived for item in results))


class KnowledgeGraphTests(unittest.TestCase):
    def test_graph_counts_languages_and_tests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "app.py").write_text("def run():\n    return True\n", encoding="utf-8")
            tests = repo / "tests"
            tests.mkdir()
            (tests / "test_app.py").write_text("def test_run():\n    assert True\n", encoding="utf-8")
            (repo / "ui.ts").write_text("export function load() { return true; }\n", encoding="utf-8")
            graph = build_knowledge_graph(repo)
            self.assertEqual(graph.languages["Python"], 2)
            self.assertEqual(graph.languages["TypeScript"], 1)
            self.assertEqual(len(graph.test_files), 1)


class EndToEndProofTests(unittest.TestCase):
    def _write_repo(self, root: Path, weak: bool = False, secret: bool = False) -> None:
        app = "def eligible(age):\n    return age >= 18\n"
        if secret:
            secret_value = "A" * 20
            app += f'api_key = "{secret_value}"\n'
        (root / "app.py").write_text(app, encoding="utf-8")
        tests = root / "tests"
        tests.mkdir()
        assertion = "self.assertTrue(True)" if weak else "self.assertTrue(eligible(18))\n        self.assertFalse(eligible(17))"
        (tests / "test_app.py").write_text(
            "import unittest\nfrom app import eligible\n\n"
            "class AppTests(unittest.TestCase):\n"
            "    def test_eligible(self):\n"
            f"        {assertion}\n\n"
            "if __name__ == '__main__':\n    unittest.main()\n",
            encoding="utf-8",
        )
        (root / "basalt.yaml").write_text(
            "project:\n  name: fixture\n  type: python\n"
            "commands:\n  lint: python -m compileall app.py tests\n  test: python -m unittest discover -s tests -v\n"
            "proof:\n  require_lint: true\n  require_tests: true\n  mutation_sample: true\n"
            "  mutation_max: 1\n  mutation_include: app.py\n  min_verified_score: 80\n"
            "policy:\n  block_secrets: true\n  block_destructive_migrations: true\n"
            "sandbox:\n  mode: temp\n",
            encoding="utf-8",
        )

    def test_real_fixture_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self._write_repo(repo)
            report = verify_repo(repo)
            self.assertEqual(report.final_status.value, "VERIFIED")
            self.assertGreaterEqual(report.score, 90)
            self.assertEqual(len(report.mutations), 1)
            self.assertFalse(report.mutations[0].survived)

    def test_weak_fixture_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self._write_repo(repo, weak=True)
            report = verify_repo(repo)
            self.assertEqual(report.final_status.value, "WEAK_PROOF")
            self.assertTrue(report.mutations[0].survived)

    def test_secret_fixture_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self._write_repo(repo, secret=True)
            report = verify_repo(repo)
            self.assertEqual(report.final_status.value, "BLOCKED_BY_POLICY")


if __name__ == "__main__":
    unittest.main()
