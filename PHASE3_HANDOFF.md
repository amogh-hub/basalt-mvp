# Phase 3 Handoff

## Version

`2.2.0a1`

## Branch

`phase-3-safe-fixes`

## Primary modules

- `basalt_proof/agent_runtime.py`
- `basalt_proof/patch_engine.py`
- `basalt_proof/policy_kernel.py`
- `basalt_proof/models.py`
- `basalt_proof/cli.py`

## Main commands

```bash
basalt agent plan <repo> --task <task> --role <role> [--target <path>] [--patch <diff>]
basalt agent approve <repo> <run-id> --by <name> --reason <reason>
basalt agent apply <repo> <run-id> --token <token> [--sandbox auto]
basalt agent status <repo> [run-id]
basalt agent reject <repo> <run-id> --by <name> --reason <reason>
basalt agent revise <repo> <run-id> --patch <diff>
basalt agent rollback <repo> <run-id> --by <name> --reason <reason>
```

## Phase 4 boundary

Do not add the full web application inside this phase. Phase 4 should expose already-proven Phase 1–3 truth through the Command Center rather than replacing CLI/runtime truth with UI-only state.
