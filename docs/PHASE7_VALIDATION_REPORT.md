# Phase 7 Validation Report — Basalt 3.0.0rc4

## Validation result

RC4 is a passing local source candidate with one environment-dependent release gate remaining: final browser revalidation on the project Mac. Docker verification is conditional on Docker availability.

## Automated test results

| Gate | Result |
|---|---:|
| Python compilation | PASS |
| Command Center JavaScript syntax | PASS |
| Build Workspace JavaScript syntax | PASS |
| Full automated suite | **224 PASS** |
| RC4 hardening regression tests | **14 PASS** |
| Critical proof matrix | **103 PASS** |
| Temp-sandbox self-verification | **VERIFIED 98/100** |
| High-severity self-scan findings | **0** |
| Mutation sample | **1 killed, 0 survived** |
| HTTP/API authorization and lifecycle contracts | PASS |

Full-suite execution completed in 99.462 seconds in the delivery environment.

## RC4 correction coverage

- RC4-01 release identity and active branding: PASS
- RC4-02 proof applicable/skipped summary: PASS
- RC4-03 generated-output/lint containment: PASS
- RC4-04 workspace refresh continuity implementation and regression contract: PASS
- RC4-05 exact diagnostic column navigation: PASS
- RC4-06 command availability consistency: PASS
- RC4-07 approval decision context: PASS
- RC4-08 patch scope versus impact terminology: PASS
- RC4-09 transaction list/detail synchronization: PASS
- RC4-10 provenance and rollback UX: PASS
- RC4-11 Evidence Vault depth and content addressing: PASS
- RC4-12 deterministic agent-execution truth: PASS
- RC4-13 Git read-only browser workflow foundation: PASS

## Additional Phase 7 source gates

- architecture/API/database/dependency canvas: PASS
- safe static preview lifecycle: PASS
- local identity/organization/project/job/provider/deployment surface: PASS
- local operations, incidents, and recovery surface: PASS
- append-only factory rollback: PASS
- accessibility foundations: PASS

## Self-verification evidence

```text
Final Status: VERIFIED
Proof Score: 98/100
Sandbox: temp
Checks: lint PASS, test PASS, install/build/typecheck NOT_APPLICABLE
Mutation: python_ast_compare_flip KILLED
High findings: 0
Basalt version: 3.0.0rc4
```

## Browser validation note

Service-level APIs, authorization, static UI contracts, lifecycle endpoints, Git APIs, preview serving, and browser-facing regression contracts pass. The delivery container includes Chromium, but administrator policy blocks all Chromium navigation with `ERR_BLOCKED_BY_ADMINISTRATOR`, including localhost, file, and data URLs. Therefore a truthful visual/browser execution result cannot be claimed from this environment.

The accepted RC3 browser workflow already proved the underlying tabs, editing, save, stale conflict, search, console, Proof, Activity, and large-file scroll flows. RC4 changed those flows and must be visually revalidated once on the project Mac before publishing.

## Docker validation note

The Docker command is not installed in the delivery environment. Docker verification was not run and is not reported as passing. Temp-sandbox verification passed.

## Release status

`3.0.0rc4` is ready for project-Mac installation and final browser acceptance. It is not yet a published GitHub prerelease and is not Production Basalt v1 GA.
