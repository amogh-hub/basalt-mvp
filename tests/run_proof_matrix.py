from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TARGETS = [
    "tests.test_phase1_self_verification",
    "tests.test_phase2_knowledge_context.ProjectKnowledgeGraphTests.test_python_ast_symbols_routes_and_calls",
    "tests.test_phase2_knowledge_context.ProjectKnowledgeGraphTests.test_freshness_detects_changed_new_and_removed_files",
    "tests.test_phase2_knowledge_context.ContextCompilerTests.test_context_pack_selects_target_and_related_tests",
    "tests.test_phase2_knowledge_context.ContextCompilerTests.test_no_refresh_rejects_stale_graph",
    "tests.test_phase3_agent_safe_fixes.PatchEngineTests",
    "tests.test_phase3_agent_safe_fixes.PolicyKernelTests",
    "tests.test_phase4_command_center.CommandCenterServiceTests.test_overview_compresses_truth",
    "tests.test_phase4_command_center.CommandCenterServerTests.test_health_and_static_ui_have_security_headers",
    "tests.test_phase4_command_center.CommandCenterServerTests.test_mutating_action_requires_action_token",
    "tests.test_phase5_ai_software_factory",
]


def main() -> int:
    count = sum(unittest.defaultTestLoader.loadTestsFromName(target).countTestCases() for target in TARGETS)
    for target in TARGETS:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "-q", target],
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode != 0:
            print(result.stdout, file=sys.stderr)
            print(f"Proof matrix failed in {target}.", file=sys.stderr)
            return result.returncode
    print(f"Basalt proof matrix: {count} critical tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
