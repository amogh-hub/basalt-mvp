# Basalt 3.0.0rc4 Implementation Specification

## Purpose

Basalt 3.0.0rc4 is the Phase 7 hardening and truth-correction candidate created from defects discovered during 3.0.0rc3 acceptance.

RC4 must preserve every capability that passed in RC3 while correcting misleading state, incomplete governance detail, workspace continuity gaps, and evidence/provenance weaknesses.

RC4 is not the completion of Phase 7. It is the next hardened release candidate.

## Accepted RC3 Baseline

The protected baseline is:

- Version: 3.0.0rc3
- Automated tests: 210 passed
- Self-verification: VERIFIED, 98/100
- Governed workflow: proposal → approval → token → apply → proof → rollback
- Build Workspace browser acceptance completed
- Git tag: rc3-accepted-baseline

## Mandatory RC4 Corrections

### RC4-01 — Release identity and branding truth

Replace active product UI references that incorrectly describe RC3/RC4 as:

- basalt-v2.5-private-beta
- PRIVATE BETA
- Phase 6

Runtime product identity must come from one authoritative version and release-state source.

Historical release notes and historical documentation must not be rewritten.

### RC4-02 — Proof summary accuracy

Correct proof reporting so that:

- passed checks are counted as passed;
- failed checks are counted as failed;
- skipped or unavailable checks are not presented as failures;
- the displayed skipped count matches the detailed check cards;
- optional unconfigured checks use truthful language such as NOT_APPLICABLE or SKIPPED;
- the 98/100 score has an understandable breakdown.

### RC4-03 — Verification output containment

Default lint and verification commands must avoid scanning generated Basalt runtime state where appropriate, including:

- .basalt/
- virtual environments
- Python caches
- generated evidence and transaction artefacts

This must not hide real project-source findings.

### RC4-04 — Workspace refresh continuity

Browser refresh must restore, where valid:

- open file tabs;
- active file;
- cursor position;
- editor scroll position;
- repository search query and state;
- selected right-side panel;
- panel sizing.

Stale or missing files must be handled safely without crashing the workspace.

### RC4-05 — Diagnostic navigation precision

Selecting a diagnostic must navigate to:

- the correct file;
- the correct line;
- the reported column when available;
- a visible cursor or selection at the problem location.

### RC4-06 — Command availability consistency

Commands shown in the Command Palette must match actual runtime availability.

A command that has no configured implementation must either:

- be disabled with a reason; or
- be omitted.

The palette must not advertise Build as executable when Build is unavailable.

### RC4-07 — Approval decision context

High-risk approval views must show sufficient decision evidence:

- target file or files;
- complete proposed diff;
- changed-line count;
- policy reason;
- risk classification;
- base-state hash;
- expected impact;
- available proof context;
- proposer and creation time.

### RC4-08 — Impact-versus-patch terminology

Metrics such as Files, Tests and Features must distinguish between:

- directly changed patch scope; and
- calculated impact radius.

The interface must not label affected dependencies as though they were edited files.

### RC4-09 — Transaction state synchronisation

After approval, apply, verification, rejection or rollback:

- list state and detail state must agree;
- stale detail panels must refresh automatically;
- current state must not require closing and reopening the record;
- state transitions must be auditable.

### RC4-10 — Transaction provenance and rollback UX

Transaction details must expose:

- transaction identifier;
- base and resulting state hashes;
- proposer and approver;
- timestamps;
- linked proof result;
- linked evidence artefacts;
- affected files;
- rollback eligibility;
- rollback result and restored hash.

### RC4-11 — Evidence Vault depth

Evidence must be grouped by run or transaction and expose:

- artefact name;
- type or schema;
- origin;
- creation time;
- integrity hash;
- immutable or mutable status;
- associated proof, transaction and source state.

### RC4-12 — Agent-execution truth

Basalt must not describe deterministic template generation as real distributed or dependency-ordered agent execution.

Either:

- implement truthful dependency-ordered execution records; or
- change product language to accurately describe deterministic planning and artefact generation.

Timestamps and dependency relationships must not contradict each other.

### RC4-13 — Git Workspace validation

Run the complete Git browser acceptance workflow inside the RC4 Git repository:

- repository detection;
- branch display;
- changed-file display;
- diff inspection;
- clean-state reporting;
- safe handling of untracked files;
- no unintended commits, pushes or destructive operations.

## Required Regression Tests

Every correction must include automated regression coverage where technically possible.

The automated suite must remain fully passing and must increase beyond the RC3 baseline when new regression tests are added.

## Required Acceptance Gates

RC4 cannot be released until all applicable gates pass:

1. Full automated test suite.
2. New regression tests for every corrected defect.
3. Self-verification.
4. Proof matrix.
5. Temporary sandbox verification.
6. Docker verification where supported.
7. Governed approval/apply/prove/rollback workflow.
8. Full Build Workspace browser acceptance.
9. Git Workspace browser acceptance.
10. Version and branding audit.
11. Evidence and provenance audit.
12. Transaction state-synchronisation audit.
13. Clean working tree and reviewed release diff.

## Release Rules

- Do not modify the RC3 baseline commit or tag.
- Do not release RC4 before all mandatory corrections are verified.
- Do not call Phase 7 complete after RC4.
- Do not claim superiority over Cursor, Replit or Emergent without measured benchmark evidence.
- Do not push or publish a GitHub release during implementation.
