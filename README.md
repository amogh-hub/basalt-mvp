# Basalt v2.2 Alpha Safe Fix Platform

**Version:** `2.2.0a1`

Basalt is a proof-first, prevention-first AI software platform. Phase 3 adds governed agent-assisted fixes: agents may propose patches, but Basalt owns policy review, human approval, atomic repository mutation, sandbox verification, proof comparison, and rollback.

> **Core promise:** Verified software, not vibes.

This is the official **Phase 3 — Agent-Assisted Safe Fixes** alpha. It is a governed single-fix transaction platform, not yet the full multi-agent AI Software Factory.

## What Phase 3 adds

- Unified-diff patch ingestion and deterministic patch parsing
- Safe patch preflight in an isolated repository copy
- Path traversal, binary patch, protected path, lockfile, and stale-context rejection
- Role-scoped capability permissions for implementation, frontend, backend, testing, database, DevOps, and documentation agents
- Read-only Security and Code Review agent roles
- Policy verdicts: `ALLOW`, `REQUIRE_HUMAN_APPROVAL`, and `BLOCK`
- Risk flags and contract-lock requirements for auth, payment, database, contract, deployment, and high-impact changes
- One-time human approval tokens whose plaintext is never persisted
- Compare-and-swap repository state coordination
- Atomic file backups and transaction manifests
- Full before/after Basalt proof execution in temp or Docker sandboxes
- Acceptance only when the resulting repository is `VERIFIED` without proof regression
- Automatic rollback when proof fails or regresses
- Manual rollback for verified transactions when repository state is still safe
- Loop Governor with bounded attempts and repeated-patch/oscillation detection
- Persistent run state, agent actions, policy evidence, verification deltas, and audit logs
- Built-in deterministic proof-hardening proposals for weak Python boundary tests
- All Phase 1 proof and Phase 2 graph/context capabilities

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

## Safe-fix workflow

### 1. Plan a governed patch

An external coding agent may produce a normal unified diff. Basalt does not let that agent write directly to the repository.

```bash
basalt agent plan /path/to/repo \
  --task "Fix the login redirect regression" \
  --role FrontendAgent \
  --target src/LoginPage.tsx \
  --patch /path/to/fix.patch
```

For a weak Python test discovered by Basalt mutation testing, omit `--patch` to request the built-in deterministic proof-hardening proposal:

```bash
basalt agent plan /path/to/repo \
  --task "Strengthen boundary proof" \
  --role TestingAgent \
  --target app.py
```

Planning performs repository-state capture, graph refresh, context compilation, before-proof execution, patch preflight, impact analysis, Policy Kernel review, and deterministic Testing/Security/Code Review actions.

### 2. Approve or reject

```bash
basalt agent approve /path/to/repo <run-id> \
  --by "Amogh RB" \
  --reason "Reviewed the patch, impact map, and policy evidence"
```

Basalt prints a one-time token. Only the token hash is stored.

```bash
basalt agent reject /path/to/repo <run-id> \
  --by "Amogh RB" \
  --reason "The proposed behavior is not approved"
```

### 3. Apply and verify

```bash
basalt agent apply /path/to/repo <run-id> \
  --token <one-time-token> \
  --sandbox auto
```

Basalt applies the patch atomically, runs the complete proof system, compares before and after evidence, refreshes the Project Knowledge Graph, and commits the state transaction only when the result is verified. Failed or regressive patches are restored automatically.

### 4. Audit or roll back

```bash
basalt agent status /path/to/repo
basalt agent status /path/to/repo <run-id>

basalt agent rollback /path/to/repo <run-id> \
  --by "Amogh RB" \
  --reason "Reverting the accepted transaction"
```

Manual rollback fails closed when unrelated repository changes make restoration unsafe.

### 5. Revise under the Loop Governor

```bash
basalt agent revise /path/to/repo <run-id> --patch /path/to/revised.patch
```

Revisions receive a fresh policy decision. Basalt stops repeated patch hashes, oscillation, and attempts beyond the configured limit.

## Policy configuration

```yaml
agents:
  enabled: true
  max_files: 8
  max_changed_lines: 400
  max_attempts: 3
  require_human_approval_for_source: true
  allow_test_only_auto_apply: false
  protected_paths: .github/workflows,.env,infra,deploy
  allowed_roles: ImplementationAgent,BuilderAgent,FrontendAgent,BackendAgent,DatabaseAgent,TestingAgent,DevOpsAgent,DocumentationAgent
```

Default safety behavior:

- source changes require explicit human approval;
- test-only auto-apply is disabled;
- review agents cannot author patches;
- Testing Agent cannot edit source files;
- Database Agent cannot perform destructive schema changes;
- protected paths and secret introduction are blocked;
- stale state cannot be applied;
- no patch is accepted without full proof.

## Existing platform commands

```bash
basalt doctor
basalt inspect .
basalt graph build .
basalt graph status .
basalt graph query . login
basalt impact . basalt_proof/agent_runtime.py
basalt context . --task "Review transaction safety" --role CodeReviewAgent --target basalt_proof/agent_runtime.py
basalt verify .
```

## Agent-run artifacts

Each run is stored under:

```text
.basalt/agent-runs/<run-id>/
```

Typical evidence includes:

```text
run.json
candidate.patch
candidate-patch.md
patch-proposal.json
policy-decision.json
policy-decision.md
approval.json
before-proof-report.json
after-proof-report.json
verification-delta.json
verification-delta.md
state-transaction.json
audit-log.json
backup/
```

The exact set depends on how far the transaction progressed.

## Validation

- `76` automated tests
- Phase 1 and Phase 2 regression suites preserved
- Safe source patch transaction tested
- Weak-proof test hardening tested from `WEAK_PROOF 78/100` to `VERIFIED 98/100`
- Proof-regressing patch tested with automatic rollback
- Stale repository state tested fail-closed
- Approval token hashing and one-time use tested
- Capability violations and destructive changes tested as blocked
- Loop attempt limits and repeated patch detection tested
- Temp sandbox self-verification: recorded in `docs/PHASE3_VALIDATION_REPORT.md`

## Current boundary

Phase 3 governs patches produced by external coding agents and includes a narrow deterministic proof-hardening generator. It does not yet call cloud LLMs, autonomously coordinate the final 12-agent system, deploy to production, or provide the full Command Center UI. Those capabilities belong to later roadmap phases.

See:

- `docs/AGENT_SAFE_FIXES.md`
- `docs/POLICY_KERNEL.md`
- `docs/STATE_TRANSACTIONS_AND_LOOP_GOVERNOR.md`
- `docs/PHASE3_COMPLETION.md`
- `docs/PHASE3_VALIDATION_REPORT.md`
- `PHASE3_HANDOFF.md`
