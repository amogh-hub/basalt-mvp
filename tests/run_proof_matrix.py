from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
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
    "tests.test_phase5_ai_software_factory.DesignSystemTests",
    "tests.test_phase5_ai_software_factory.EpochPlannerTests",
    "tests.test_phase5_ai_software_factory.ProductBrainTests",
    "tests.test_phase5_ai_software_factory.PreventionFirstTests",
    "tests.test_phase5_ai_software_factory.StateCoordinatorTests",
    "tests.test_phase5_ai_software_factory.SoftwareFactoryTests",
    "tests.test_phase6_private_beta.WorkspaceRegistryTests",
    "tests.test_phase6_private_beta.DurableJobQueueTests",
    "tests.test_phase6_private_beta.ProviderRegistryTests.test_local_provider_inventory_is_available",
    "tests.test_phase6_private_beta.ProviderRegistryTests.test_local_privacy_selects_local_provider",
    "tests.test_phase6_private_beta.ProviderRegistryTests.test_environment_remote_profile_is_configured",
    "tests.test_phase6_private_beta.ProviderRegistryTests.test_remote_profile_without_key_is_not_configured",
    "tests.test_phase6_private_beta.ProviderRegistryTests.test_unconfigured_provider_fails_closed",
    "tests.test_phase6_private_beta.WorkspaceRuntimeTests",
    "tests.test_phase6_private_beta.DeploymentManagerTests",
    "tests.test_phase6_private_beta.PrivateBetaPlatformTests",
]


def main() -> int:
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite(loader.loadTestsFromName(target) for target in TARGETS)
    count = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        return 1
    print(f"Basalt proof matrix: {count} critical tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
