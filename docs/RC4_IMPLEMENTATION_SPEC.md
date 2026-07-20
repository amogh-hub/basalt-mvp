# Basalt 3.0.0rc4 Implementation Specification

## Purpose

Basalt 3.0.0rc4 is the Phase 7 hardening and truth-correction candidate created from defects discovered during 3.0.0rc3 acceptance.

RC4 must preserve every capability that passed in RC3 while correcting misleading state, incomplete governance detail, workspace continuity gaps, and evidence/provenance weaknesses.

RC4 also completes the remaining local Phase 7 product surfaces that can be implemented and tested without external cloud infrastructure.

RC4 is not Production Basalt v1 GA.

## Accepted RC3 baseline

- Version: 3.0.0rc3
- Automated tests: 210 passed
- Self-verification: VERIFIED, 98/100
- Governed workflow: proposal → approval → token → apply → proof → rollback
- Build Workspace browser acceptance completed
- Git baseline tag on the project Mac: `rc3-accepted-baseline`

## Mandatory RC4 corrections

### RC4-01 — Release identity and branding truth

Replace active product UI references that incorrectly describe RC3/RC4 as v2.5 private beta or Phase 6. Runtime product identity must come from one authoritative version and release-state source. Historical release notes remain historical.

### RC4-02 — Proof summary accuracy

- count passed, failed, warning, and skipped states accurately;
- exclude not-applicable checks from the applicable denominator;
- display skipped/not-applicable reasons;
- expose a deterministic proof-score breakdown.

### RC4-03 — Verification output containment

Default lint and verification inference must avoid generated Basalt state, environments, dependencies, caches, and evidence while still scanning actual project source.

### RC4-04 — Workspace refresh continuity

Restore valid open tabs, active file, unsaved buffers, cursor, scroll, search, selected panel, and pane sizes. Missing or stale files must fail safely.

### RC4-05 — Diagnostic navigation precision

Navigate to the correct file, line, and reported column, with the cursor visibly placed at the problem location.

### RC4-06 — Command availability consistency

The command palette and buttons must match configured runtime availability. Unavailable commands must be omitted or disabled with a reason.

### RC4-07 — Approval decision context

High-risk approval views must show target files, complete diff, changed-line count, policy reason, risk, base hash, impact, proof context, proposer, and creation time.

### RC4-08 — Impact-versus-patch terminology

Directly changed patch scope and calculated impact radius must be distinct.

### RC4-09 — Transaction state synchronization

List and detail state must agree after approval, apply, verification, rejection, or rollback without requiring close/reopen.

### RC4-10 — Transaction provenance and rollback UX

Expose identifiers, hashes, people, timestamps, proof, evidence, affected files, rollback eligibility, rollback result, and restored hash.

### RC4-11 — Evidence Vault depth

Group artifacts by run or transaction and expose type/schema, origin, timestamps, integrity hash, mutability, proof, transaction, and source-state linkage.

### RC4-12 — Agent-execution truth

Do not describe deterministic template materialization as remote or autonomous multi-agent execution. Dependency and timestamp records must not contradict one another.

### RC4-13 — Git Workspace validation

Support truthful read-only repository detection, branch, changes, diff, untracked files, conflicts, and recent history. Do not enable unintended commit, push, or destructive operations.

## Remaining local Phase 7 implementation gates

### P7-01 — Architecture, API, and database truth

Provide source-derived architecture layers, modules, route discovery, schema discovery, and dependency signals. Clearly identify static analysis as the source of truth.

### P7-02 — Safe preview lifecycle

Provide same-origin static preview with start/stop controls, no arbitrary shell or backend execution, protected paths, traversal protection, and file limits.

### P7-03 — Local control-plane visibility

Expose persistent local identities, teams, projects, durable jobs, providers, deployments, isolated workspaces, and honest capability boundaries.

### P7-04 — Operations and recovery truth

Synthesize local incidents from proof, graph, jobs, deployments, preview, approvals, and rollback readiness without claiming external uptime.

### P7-05 — Factory rollback

Expose append-only rollback that preserves prior state versions, quarantines generated output, records the restored hash, and does not erase ledger history.

### P7-06 — Accessibility foundations

Provide semantic navigation, skip link, status live region, keyboard controls, visible focus, and reduced-motion behavior.

## Required regression tests

Every correction and local Phase 7 gate requires automated coverage where technically possible. The complete suite must increase beyond the 210-test RC3 baseline and remain fully passing.

## Required acceptance gates

1. Full automated test suite.
2. RC4 regression suite.
3. Python and JavaScript syntax validation.
4. Self-verification.
5. Critical proof matrix.
6. Temporary sandbox verification.
7. Docker verification where supported.
8. Governed approval/apply/prove/rollback workflow.
9. Command Center browser acceptance.
10. Build Workspace browser acceptance.
11. Git Workspace browser acceptance.
12. Version and branding audit.
13. Evidence and provenance audit.
14. Transaction state-synchronization audit.
15. Clean working tree and reviewed release diff.
16. Reproducible release archive and checksum.

## Release rules

- Do not modify the RC3 baseline commit or tag.
- Do not release RC4 before mandatory corrections and applicable gates pass.
- Do not call Production Basalt v1 GA merely because local source gates pass.
- Do not claim superiority over Cursor, Replit, or Emergent without measured benchmark evidence.
- Do not represent unavailable external systems as live.
- Do not publish a GitHub release during implementation.

## External infrastructure boundary

Hosted multi-tenant identity, billing, remote workers, hardened microVMs, secret vaults, real cloud deployment execution, external telemetry, alerting, enterprise SSO, and compliance certification require actual providers and credentials. RC4 must provide truthful foundations and interfaces but must not fake production validation.
