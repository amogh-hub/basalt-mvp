# Basalt v3 Production Candidate

**Version:** `3.0.0rc4`

**Phase:** 7 — Production Basalt v1

**Core promise:** **Verified software, not vibes.**

Basalt is a proof-first AI software factory and governed engineering workspace. It connects repository truth, architecture, planning, editing, verification, approvals, state transactions, rollback, evidence, release controls, and local operational visibility in one system.

RC4 is the hardened Phase 7 source candidate. It preserves the accepted RC3 workflow while correcting release identity, proof-count truth, workspace continuity, diagnostic precision, transaction synchronization, evidence provenance, factory rollback, and deterministic-agent language.

## Product surfaces

### Build Workspace

The browser workspace provides:

- repository explorer and contextual code search;
- multiple file tabs with unsaved-state tracking;
- line numbers, syntax rendering, cursor metadata, and bounded diagnostics;
- exact diagnostic navigation to file, line, and column;
- governed diff review before atomic saves;
- stale-state detection and explicit repository reload;
- configured-command-only Build console;
- Proof, Activity, and read-only Git engineering panels;
- Git branch, status, diff, untracked-file, and recent-history visibility;
- session restoration for tabs, active file, unsaved buffers, cursor, scroll, search, selected panel, and pane sizes;
- command-palette entries that match actually configured commands.

Arbitrary shell execution, browser commits, browser pushes, protected-directory editing, and silent stale writes remain disabled.

### Command Center

The Command Center provides:

- repository proof and score breakdown;
- Product Brain and governed factory planning;
- deterministic dependency-ordered specialist work records;
- architecture, API, database, and dependency canvases derived from source truth;
- Project Knowledge Graph and impact/context tools;
- safe same-origin static preview lifecycle controls;
- agent and factory transaction ledgers;
- approval decisions with complete patch, policy, hash, impact, and proof context;
- append-only state transitions and rollback controls;
- local users, teams, projects, durable jobs, providers, and deployment ledgers;
- local operations, incident, and recovery visibility;
- evidence grouped by proof, agent run, factory run, or control-plane origin with SHA-256 integrity metadata.

## Proof model

Basalt verification combines:

- configured install/build/lint/typecheck/test checks;
- security and policy scanning;
- mutation testing;
- AST-backed repository graph evidence;
- risk and human-approval gates;
- generated machine-readable and human-readable evidence.

Unconfigured optional checks are reported as `NOT_APPLICABLE` rather than failures. Proof summaries count only applicable checks in the passed denominator and show skipped checks separately.

The RC4 repository self-verifies as:

```text
VERIFIED
98/100
2/2 applicable checks passed
3 checks not applicable
1 mutation killed
0 high-severity findings
```

## Governed change lifecycle

The protected agent-assisted workflow is:

```text
repository truth
→ context compilation
→ patch proposal
→ policy decision
→ human approval when required
→ one-time approval token
→ controlled apply
→ post-change proof
→ committed transaction
→ evidence linkage
→ append-only rollback when requested
```

Patch scope and calculated impact radius are displayed separately. Affected files, tests, and features are never presented as though they were directly edited.

## Factory execution truth

RC4 does not label template materialization as remote autonomous agent execution. Factory records use `DETERMINISTIC_LOCAL`, respect declared dependencies in topological order, use non-contradictory timestamps, and identify the artifacts produced by each specialist contract.

Factory state rollback is exposed as an append-only state transition. Previous committed versions remain queryable; rollback does not rewrite ledger history.

## Architecture and preview

Architecture views are derived from repository source and the AST-backed Knowledge Graph. They are not manually drawn or model-invented diagrams.

Preview is deliberately bounded:

- static assets only;
- same-origin serving;
- no arbitrary project commands;
- no server-side project execution;
- protected-path enforcement;
- file-type and size limits;
- explicit start and stop lifecycle.

Projects requiring a backend runtime must use a configured governed runtime or external deployment connector; RC4 does not silently execute them.

## Local control plane

Preserved Phase 6 foundations include:

- persistent local users, teams, memberships, and projects;
- owner/admin/developer/reviewer/viewer roles;
- durable SQLite jobs with idempotency, leases, heartbeats, retries, cancellation, and lifecycle events;
- bounded isolated job workspaces;
- secret-safe provider inventory;
- proof-gated deployment packages, approvals, promotion, restore, and rollback records.

The Operations surface reports only observed local proof, graph, job, deployment, preview, approval, and rollback state. It does not claim external uptime monitoring.

## Quick start

```bash
cd /path/to/basalt-mvp-v1.5-full
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
python -m unittest discover -s tests -p 'test_*.py'
basalt verify . --sandbox temp
basalt command-center . --allow-actions
```

Open:

```text
Command Center: http://127.0.0.1:7337/
Build Workspace: http://127.0.0.1:7337/workspace
```

The launch output includes a per-process action token. Do not share that token.

## Main CLI

```text
basalt verify <repo>
basalt inspect <repo>
basalt graph build|status|query <repo>
basalt impact <repo> <target>
basalt context <repo> <task>
basalt agent plan|status|approve|reject|apply|rollback
basalt factory plan|build|create|status|models|design-system
basalt beta bootstrap|status|project|job|provider|deployment
basalt command-center <repo> --allow-actions
```

Run `basalt <command> --help` for exact arguments.

## Evidence locations

Repository evidence defaults to `.basalt/`:

- proof reports and score breakdown;
- graph, impact, and context artifacts;
- agent proposals, policy decisions, approvals, transactions, proof deltas, backups, and rollback records;
- factory blueprints, plans, task graphs, manifests, proof, state transactions, and rollback evidence;
- architecture and operations snapshots;
- workspace activity evidence;
- private control-plane databases and deployment packages.

The Evidence Vault reports origin, schema, creation and modification time, SHA-256, group, and honest mutability state. Local evidence is hash-tracked but is not falsely described as immutable storage.

## Security invariants

- loopback binding is enforced by default;
- non-loopback binding requires explicit unsafe mode;
- same-origin, host, and action-token checks protect browser mutations;
- one-time approval tokens are stored only as hashes;
- protected paths include `.git`, `.basalt`, environments, dependencies, caches, and generated internals;
- symlinks and path traversal fail closed in bounded workspaces;
- dangerous commands are rejected;
- only configured or safely inferred commands can execute;
- source writes use optimistic hashes and atomic replacement;
- rollback creates new ledger evidence rather than erasing history.

## Honest production boundary

RC4 completes the Phase 7 **local product source candidate** and production-control foundations. The following require real external infrastructure and credentials before they can be claimed as production-validated:

- hosted multi-tenant identity and billing;
- managed distributed workers and remote hardened sandboxes;
- production secret vault integration;
- provider-specific AWS, GCP, Azure, Vercel, or similar deployment execution;
- external uptime, telemetry, alerting, and incident paging;
- enterprise SSO and compliance certification.

Basalt exposes truthful local foundations and governed integration boundaries for these systems; it does not simulate them as live production services.

## Validation status

RC4 validation performed in the delivery environment:

- Python compilation: PASS;
- JavaScript syntax: PASS;
- full automated suite: **232 tests PASS**;
- critical proof matrix: **103 tests PASS**;
- self-verification: **VERIFIED 98/100**;
- HTTP/API authorization and lifecycle contracts: PASS;
- Docker verification: not run because Docker is unavailable in the delivery environment;
- final browser revalidation on the project Mac: required before publishing the GitHub prerelease.

See:

- `docs/PHASE7_MASTER_SPEC.md`
- `docs/PHASE7_VALIDATION_REPORT.md`
- `docs/RELEASE_NOTES_V3_RC4.md`
- `docs/RC4_IMPLEMENTATION_SPEC.md`

## Roadmap

```text
Phase 0 — Vision + Grant/Demo MVP                 COMPLETE
Phase 1 — Alpha Proof Platform                    COMPLETE
Phase 2 — Knowledge Graph + Context Compiler      COMPLETE
Phase 3 — Agent-Assisted Safe Fixes               COMPLETE
Phase 4 — Command Center Web App                  COMPLETE
Phase 5 — Alpha AI Software Factory               COMPLETE
Phase 6 — Private Beta Full Build System          COMPLETE
Phase 7 — Production Basalt v1                    RC4 SOURCE CANDIDATE COMPLETE; RELEASE ACCEPTANCE ACTIVE
Phase 8 — Full Basalt Final Vision                UPCOMING
```

## License

Basalt is proprietary software. See `LICENSE`.
