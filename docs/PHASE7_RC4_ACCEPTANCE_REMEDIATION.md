# Phase 7 RC4 Acceptance Remediation

> Release candidate: `3.0.0rc4`  
> Scope: all defects discovered during browser acceptance, governed workspace testing, Factory execution, transaction inspection, and rollback validation.

## Release position

This remediation closes the complete 33-item acceptance ledger in source and adds regression coverage. The repaired source is eligible for the final installation/browser smoke gate; no tag or push is performed automatically.

## Defect closure matrix

| ID | Severity | Finding | Remediation | Verification |
|---|---:|---|---|---|
| VA-001 | MEDIUM | Preview mode label overflows its metric card | Responsive metric wrapping and overflow-safe preview labels. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-002 | LOW | Low-severity documentation findings dominate Proof risk evidence | Proof UI groups low documentation-quality signals separately from security/risk blockers. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-003 | MEDIUM | Oversized evidence artifact has no governed viewing alternative | Evidence service supports bounded chunked previews with size, offset, remaining bytes, load-more, and copy controls. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-004 | LOW | Active Control Plane empty states still use “private-beta” wording | Removed active private-beta wording; Phase 6 and Control Plane use persistent/local terminology. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-005 | LOW | Operations rollback empty state is ambiguous | Operations reports “No eligible transaction” instead of ambiguous rollback unavailability. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-006 | MEDIUM | Factory plan action does not disclose output target or mutation scope | Factory planning now discloses output location, mutation boundary, execution mode, and no-deployment scope before action. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-007 | LOW | Plan page lacks an explicit empty-state explanation | Plan displays an explicit no-plan state and directs the user to Factory. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-008 | MEDIUM | Agents page conflates deterministic local profiles with models/agents | Agents separates deterministic engines from model-backed providers and labels execution truth explicitly. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-009 | MEDIUM | Knowledge forms rely on detached native browser validation | Knowledge and Factory forms use inline application validation with focused error messages. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-010 | MEDIUM | Impact Explorer renders raw graph payloads instead of structured impact evidence | Impact Explorer renders structured files, tests, features, risk, and reason paths instead of raw JSON. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-011 | HIGH | Context Compiler exposes only opaque summary metrics | Context packs expose selected files/tests, reasons, token allocation, omissions, saturation/truncation, precision explanation, rule version, and manifest hash. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-012 | LOW | Build Workspace no-file state exposes an apparently active Save action | No-document workspace state disables file actions and clears line/language/encoding metadata. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-013 | MEDIUM | Git ahead/behind counters show zero without a configured upstream | Git ahead/behind is N/A unless an upstream exists. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-014 | MEDIUM | Proof status terminology is inconsistent across Command Center and Workspace | Proof uses canonical NOT_APPLICABLE terminology and counts on all surfaces. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-015 | MEDIUM | Workspace Proof panel lacks freshness and evidence provenance | Proof reports now persist exact project-state hash, timestamps, sandbox/fallback, mutation/security summaries, current workspace fingerprint, and an Evidence Vault link. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-016 | LOW | Command palette exposes file actions when no file is selected | Command palette includes reload/diff/save only when a file is open and relevant. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-017 | MEDIUM | Install command availability contradicts proof configuration | Command metadata distinguishes proof checks from workspace setup utilities. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-018 | LOW | Save remains active for an unchanged clean file | Save is enabled only for a dirty active buffer. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-019 | LOW | Editor line-count and cursor metadata disagree | Editor line counts use the same trailing-newline model as cursor positions. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-020 | MEDIUM | Diagnostic navigation is unreliable on first activation | Diagnostic navigation waits for modal closure and focuses the exact location on first activation. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-021 | HIGH | `Lint` is semantically misclassified because it runs Python byte-compilation | compileall is labelled Syntax check; the repository proof config uses the new dependency-free quality checker. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-022 | LOW | Configured console clips long command provenance | Configured console wraps complete command, output, exit code, duration, purpose, and repository fingerprint. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-023 | MEDIUM | Activity events have no inspectable detail view | Activity events open a detail dialog with event ID, actor, command, exit code, hashes, Git truth, state fingerprint, and output. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-024 | HIGH | Workspace does not disclose Git tracking/ignore state for editable files | Editor and status bar disclose tracked, ignored, untracked, or Git-unavailable state and the matching ignore rule. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-025 | MEDIUM | Dependency-safe plan does not expose dependency edges or blocking reasons | Plan surfaces task dependencies, expected outputs, epoch placement, and run-level state. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-026 | MEDIUM | Planned routing cannot be inspected before execution | Agents exposes planned task-by-task deterministic/model route, capability scope, privacy, dependencies, and fallback before execution. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-027 | MEDIUM | Materialized agent records lack complete execution provenance | Materialized work cards expose task ID, route, dependencies, output artifacts, timestamps/duration, state transition, and evidence/proof provenance. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-028 | MEDIUM | Transaction status is inconsistent between summary and detail | Transactions separate transaction state from proof result in list and detail views. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-029 | MEDIUM | Factory evidence artifacts are not visibly tied to a specific run | Factory artifact cards and previews expose run, product, output state, target, proof, and transaction provenance. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-030 | LOW | Opening an evidence artifact does not navigate the user to its preview | Opening evidence scrolls/focuses the preview and preserves selection; chunk navigation remains governed. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-031 | HIGH | Verified Factory output is not discoverable or registrable in Control Plane | VERIFIED Factory output can be idempotently registered as a persistent project and packaged for staging approval from Factory; Control Plane and Approvals synchronize. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-032 | MEDIUM | Rolled-back Factory detail does not expose restored/quarantine state clearly | Rolled-back Factory detail exposes restored state, quarantine path, rollback transaction, historical proof, and inactive target. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |
| VA-033 | MEDIUM | Plan remains `MATERIALIZED` after rollback without current-state context | Plan preserves historical MATERIALIZED execution while adding ROLLED_BACK/current-output/quarantine context. | `tests/test_phase7_rc4_acceptance_remediation.py` plus full-suite regression |

## New governed lifecycle

1. A VERIFIED Factory run can be registered idempotently in the persistent local Control Plane.
2. The registered output can be packaged once for a staging approval; duplicate clicks return the existing deployment.
3. Approval requires an identified reviewer and reason.
4. Promotion requires an approved deployment and identified actor.
5. Rollback requires an identified actor and reason and remains append-only.
6. Factory, Control Plane, Approvals, deployment ledger, transactions, Operations, and Evidence share provenance.

## Validation gates

- Remediation regression tests: 8 tests.
- Existing RC4/workspace targeted tests: 33 tests.
- Full automated suite: 232 tests expected after remediation.
- Critical proof matrix: 103 tests.
- Static checks: Python compile, JavaScript syntax, Git whitespace validation.
- Quality check: errors are blocking; long-line signals are informational and grouped.
- Self-verification: Basalt proof must finish `VERIFIED 98/100` or better on the final state.
- Docker: run when available; otherwise record unavailability and use the configured safe temporary sandbox.

## Release rule

Phase 7 is complete only after the remediated source is installed on the target repository, the automated gates pass there, the browser smoke confirms the repaired surfaces, Git is clean, and the final proof is tied to the installed state. No release tag or remote push is created without explicit approval.
