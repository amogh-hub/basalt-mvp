# Basalt v2.0 Alpha Validation Report

## Automated suite

- 30 unit and integration tests passed.
- Python source and tests compile successfully.
- Coverage includes project detection, sandbox resolution, command policy, dependency scanning, workflow permissions, mutation generation, AST graph output, and end-to-end verdicts.

## Basalt self-verification

- Verdict: `VERIFIED`
- Score: `98/100`
- Mutation: killed
- Blocking findings: none
- Environment used for packaged validation: isolated temporary fallback because Docker was unavailable in the build environment.

## Built-in demo validation

- Good Python repository: `VERIFIED 100/100`
- Weak Python repository: `WEAK_PROOF 78/100`
- Weak Python repository after proof hardening: `VERIFIED 98/100`
- Weak Node repository: `WEAK_PROOF 78/100`
- Weak Node repository after proof hardening: `VERIFIED 98/100`
- Policy-violation repository: `BLOCKED_BY_POLICY 16/100`

## Additional repository validation

The TaskVault repository was correctly classified as `WEAK_PROOF 60/100` because two controlled mutations survived its uploaded test suite. This demonstrates that the alpha does not convert ordinary passing tests into a false verified verdict.

## Docker note

Docker command construction, network policy, resource limits, fallback, and fail-closed behavior are covered by automated tests. A live Docker daemon was not available in the packaging environment, so the final user should confirm one live Docker run after installing Docker Desktop.
