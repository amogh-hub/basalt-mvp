from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from basalt_proof.config import load_config
from basalt_proof.models import (
    BasaltConfig,
    CheckStatus,
    CommandResult,
    FinalStatus,
    KnowledgeGraph,
    ProofReport,
    SecurityFinding,
)
from basalt_proof.patches import build_fix_suggestions
from basalt_proof.proof import _final_status, _score_report
from basalt_proof.runner import is_command_allowed
from basalt_proof.security import scan_repo


class ConfigTests(unittest.TestCase):
    def test_csv_configuration_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            config_text = (
                "project:\n"
                "  name: self-test\n"
                "  type: python\n"
                "commands:\n"
                "  test: python -m unittest discover -s tests\n"
                "proof:\n"
                "  mutation_include: basalt_proof/proof.py\n"
                "  mutation_exclude: examples,basalt-demo-run\n"
                "  scan_exclude: examples/demo_policy_violation,basalt-demo-run\n"
            )
            (repo / "basalt.yaml").write_text(config_text, encoding="utf-8")

            config = load_config(repo)

            self.assertEqual(config.project_name, "self-test")
            self.assertEqual(config.mutation_include, ["basalt_proof/proof.py"])
            self.assertEqual(config.mutation_exclude, ["examples", "basalt-demo-run"])
            self.assertEqual(
                config.scan_exclude,
                ["examples/demo_policy_violation", "basalt-demo-run"],
            )

    def test_safe_defaults_remain_enabled(self) -> None:
        config = BasaltConfig(project_name="basalt")
        self.assertTrue(config.mutation_sample)
        self.assertTrue(config.block_secrets)
        self.assertTrue(config.block_destructive_migrations)


class RunnerPolicyTests(unittest.TestCase):
    def test_safe_python_command_is_allowed(self) -> None:
        allowed, _ = is_command_allowed("python -m unittest discover -s tests")
        self.assertTrue(allowed)

    def test_dangerous_command_is_blocked(self) -> None:
        allowed, reason = is_command_allowed("sudo rm -rf /")
        self.assertFalse(allowed)
        self.assertIn("dangerous token", reason.lower())


class SecurityScannerTests(unittest.TestCase):
    def test_real_secret_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            value = "A" * 20
            (repo / "app.py").write_text(
                f'api_key = "{value}"\n',
                encoding="utf-8",
            )

            findings = scan_repo(repo)

            self.assertTrue(any(item.rule == "generic_api_key" for item in findings))

    def test_excluded_fixture_is_not_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            fixture = repo / "examples" / "demo_policy_violation"
            fixture.mkdir(parents=True)
            value = "B" * 20
            (fixture / "app.py").write_text(
                f'api_key = "{value}"\n',
                encoding="utf-8",
            )

            findings = scan_repo(
                repo,
                excluded_paths=["examples/demo_policy_violation"],
            )

            self.assertFalse(any(item.level == "HIGH" for item in findings))

    def test_rule_declarations_do_not_flag_the_scanner_itself(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "scanner.py").write_text(
                'import re\nRULE = re.compile(r"dangerouslySetInnerHTML")\n',
                encoding="utf-8",
            )

            findings = scan_repo(repo)

            self.assertFalse(
                any(item.rule == "dangerously_set_inner_html" for item in findings)
            )

    def test_long_lines_are_quality_information_not_policy_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "README.md").write_text("x" * 220 + "\n", encoding="utf-8")

            findings = scan_repo(repo)
            line_findings = [
                item for item in findings if item.rule == "long_line_complexity"
            ]

            self.assertEqual(len(line_findings), 1)
            self.assertEqual(line_findings[0].level, "LOW")


class PatchSuggestionTests(unittest.TestCase):
    def test_low_finding_remains_low_in_patch_suggestions(self) -> None:
        report = ProofReport(
            project_name="basalt",
            repo_path=".",
            started_at="start",
            finished_at="finish",
            final_status=FinalStatus.VERIFIED,
            score=98,
            project_type="python",
            security_findings=[
                SecurityFinding(
                    level="LOW",
                    file="README.md",
                    line=1,
                    rule="long_line_complexity",
                    message="Line is very long and may be hard to maintain.",
                )
            ],
            knowledge_graph=KnowledgeGraph(
                files_scanned=1,
                test_files=["tests/test_phase1_self_verification.py"],
            ),
        )

        suggestions = build_fix_suggestions(report)
        suggestion = next(
            item
            for item in suggestions
            if item.title == "Optional cleanup: long_line_complexity"
        )

        self.assertEqual(suggestion.severity, "LOW")


class ProofModelTests(unittest.TestCase):
    def _report(self, checks: list[CommandResult]) -> ProofReport:
        return ProofReport(
            project_name="basalt",
            repo_path=".",
            started_at="start",
            finished_at="finish",
            final_status=FinalStatus.NOT_VERIFIED,
            score=0,
            project_type="python",
            checks=checks,
            knowledge_graph=KnowledgeGraph(
                files_scanned=1,
                test_files=["tests/test_phase1_self_verification.py"],
            ),
        )

    def test_failed_required_test_reduces_score(self) -> None:
        report = self._report(
            [
                CommandResult(
                    name="test",
                    command="python -m unittest",
                    status=CheckStatus.FAIL,
                )
            ]
        )

        self.assertEqual(_score_report(report), 75)

    def test_failed_required_test_is_not_verified(self) -> None:
        report = self._report(
            [
                CommandResult(
                    name="test",
                    command="python -m unittest",
                    status=CheckStatus.FAIL,
                )
            ]
        )

        self.assertEqual(_final_status(report), FinalStatus.NOT_VERIFIED)

    def test_passing_proof_without_risks_is_verified(self) -> None:
        report = self._report(
            [
                CommandResult(
                    name="test",
                    command="python -m unittest",
                    status=CheckStatus.PASS,
                )
            ]
        )

        self.assertEqual(_final_status(report), FinalStatus.VERIFIED)


if __name__ == "__main__":
    unittest.main()
