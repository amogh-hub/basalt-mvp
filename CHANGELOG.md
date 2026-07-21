## 3.0.0rc4 — Phase 7 Hardening and Product Truth

### Acceptance remediation

- Closed all 33 browser-acceptance defects across workspace truth, proof provenance, evidence viewing, planning/routing transparency, Factory-to-Control-Plane continuity, approvals, transactions, and rollback state.
- Added idempotent VERIFIED Factory registration and staging packaging with explicit approval, promote, and rollback gates.
- Replaced misleading compile-only lint semantics with a named syntax check and a dependency-free repository quality check.
- Added exact proof project-state identity, Git tracking disclosure, inspectable Activity events, chunked evidence, and reproducible context manifests.
- Added 8 dedicated acceptance-remediation tests; full suite now contains 232 tests and the critical matrix contains 103 tests.
- Preserved `3.0.0rc4`, the RC3 rollback baseline, local-only execution truth, and the no-tag/no-push release rule.

- Centralized active RC4 identity and corrected stale private-beta branding.
- Corrected applicable, skipped, and not-applicable proof counts and added score breakdown.
- Added workspace continuity, exact diagnostic navigation, command availability truth, and richer read-only Git review.
- Added complete approval context, patch-versus-impact labels, transaction synchronization, provenance, evidence grouping, and rollback UX.
- Added source-derived architecture/API/database canvases, safe static preview, local operations, and append-only factory rollback.
- Made factory specialist records explicitly deterministic, dependency-ordered, and non-contradictory.
- Added 14 original RC4 hardening tests plus 8 acceptance-remediation tests; full suite now passes 232 tests and the critical matrix passes 103 tests.
- Self-verification remains VERIFIED at 98/100.

## 3.0.0rc3 — Professional Engineering Workspace

- Adds multi-file tabs, line numbers, local syntax highlighting, cursor metadata, and keyboard shortcuts.
- Adds live bounded diagnostics and governed unified-diff review before atomic save.
- Adds stale repository conflict visibility and explicit repository reload.
- Adds contextual repository search, read-only Git visibility, command palette, and resizable panes.
- Adds integrated Build, Proof, Activity, and Git engineering panels.
- Preserves configured-command-only execution, action-token authorization, protected paths, and append-only evidence.
- Adds seven RC3 regression tests; expected complete suite is 210 tests.

## 3.0.0rc2 — Secure Workspace Foundation

- Adds the protected browser Build Workspace and configured command console.
- Adds optimistic saves, append-only workspace events, repository search, and contained viewport layout.
- Preserves Phase 0–6 behavior and establishes RC2 as the stable Phase 7 rollback baseline.

## 2.5.0b3 — Unified Factory Transaction Ledger Hotfix

- Wires committed factory state transactions into the Command Center transaction ledger.
- Displays factory transaction type, state transition, proof, target, and isolation boundary.
- Preserves agent patch transactions and their approval/apply/rollback actions.
- Adds regression coverage for the real factory state `0 → 1` acceptance path.
- Explicitly reports that factory state rollback is not exposed in Phase 6.

# Changelog

## 2.5.0b2 — Command Center Factory Build Hotfix

- Fixed governed **Build and prove** runs failing because the Command Center selected a generated-product target inside the Basalt source repository.
- Generated products now assemble into a persistent sibling `basalt-products/` directory with a run-specific target.
- Added regression coverage for Command Center factory execution.
- Factory errors now return their precise governed rejection message instead of a generic internal-error banner.

## 2.5.0b1 — Phase 6 Private Beta Full Build System

- Added persistent users, teams, memberships, projects, invitations, and activity history.
- Added owner/admin/developer/reviewer/viewer role enforcement.
- Added durable SQLite jobs with idempotency, worker leases, retries, cancellation, and lifecycle events.
- Added bounded isolated job workspaces and source immutability verification.
- Added secret-safe provider inventory and an optional OpenAI-compatible adapter.
- Expanded factory templates with `api-service`, `web-app`, and `saas-starter`.
- Added VERIFIED-only deployment packaging, SHA-256 integrity, approval gates, promote, restore, and rollback records.
- Added Private Beta Command Center APIs and project/job/provider/deployment views.
- Integrated the official Basalt wordmark and compact monochrome marks.
- Added 52 Phase 6 tests plus one Phase 2 graph-regression test, bringing the total to 187.
- Updated the critical self-proof matrix to 102 tests.

## 2.4.0-alpha.1 — Phase 5 Alpha AI Software Factory

### Added

- Product Brain for structured blueprints, requirements, flows, assumptions, risks, and success criteria
- Prevention-First Engineering plan with contradiction checks, contract locks, test plans, and risk controls
- deterministic SQLite State Coordinator with monotonic versions, compare-and-swap commits, and contract locks
- dependency-aware five-epoch planner and intersecting patch aggregation
- provider-neutral heterogeneous Model Router with local deterministic profiles and optional OpenAI-compatible adapter
- governed specialist-agent task assignments and execution records
- proof-backed staging and VERIFIED-only atomic product assembly
- `python-service` and `fullstack-lite` alpha product templates
- `basalt factory plan`, `build`, `create`, `status`, `models`, and `design-system` commands
- Command Center factory, plan, agent, and model-routing views
- Command Center factory APIs and action-token protected build endpoints
- Basalt Obsidian design tokens and UI-governance audit
- Phase 5 GitHub Actions software-factory gate
- 37 Phase 5 tests, bringing the complete suite to 133 tests
- Phase 5 architecture, validation, completion, release, and handoff documentation

### Changed

- Package version upgraded from `2.3.0a1` to `2.4.0a1`
- Product identity updated to the Basalt v2.4 Alpha AI Software Factory
- Command Center redesigned from lime-accented Phase 4 styling to the stealth Basalt Obsidian design system
- Roadmap marks Phase 4 complete and Phase 5 active

### Safety

- target directories remain untouched until staged proof is VERIFIED
- contradictory plans, stale state, contract lock conflicts, and unsupported templates fail closed
- high-risk model work receives a separate review-family assignment
- remote model use remains disabled unless deliberately configured

## 2.3.0-alpha.1 — Phase 4 Command Center Platform

### Added

- Local browser-based Command Center Web App
- Truth-compression repository overview for intent, proof, risk, progress, approvals, and recent transactions
- Live proof checks, security findings, mutation evidence, and sandbox status
- Project Knowledge Graph metrics, freshness, language distribution, and state identity
- Interactive change-impact analysis and task-specific Context Compiler
- Governed agent transaction ledger and run detail explorer
- Human approval center for pending proposals
- Whitelisted evidence vault with safe inline artifact preview
- Versioned local JSON API under `/api/v1`
- Read-only mode by default and explicit `--allow-actions` mode
- Per-launch action token, same-origin enforcement, request size limits, and localhost-only binding
- CSP, frame denial, no-store, MIME sniffing protection, and referrer protection
- New `basalt command-center` CLI with browser, port, snapshot, and security options
- 20 Phase 4 tests, bringing the complete suite to 96 tests
- Phase 4 architecture, security, validation, completion, release, and handoff documentation

### Changed

- Package version upgraded from 2.2.0a1 to 2.3.0a1
- Product identity updated to the Basalt v2.3 Alpha Command Center Platform
- Static proof dashboard branding aligned with Phase 4
- GitHub Actions expanded with Command Center snapshot and HTTP API smoke tests

### Preserved

- All Phase 1 proof, sandbox, mutation, security, scoring, and CI capabilities
- All Phase 2 graph, freshness, impact-analysis, and Context Compiler capabilities
- All Phase 3 Policy Kernel, approval, state transaction, proof comparison, and rollback capabilities

## 2.2.0-alpha.1 — Phase 3 Safe Fix Platform

### Added

- Governed agent-assisted patch transaction runtime
- Safe unified-diff parsing, preflight application, exact-context validation, and patch statistics
- Role-scoped Policy Kernel with capability permissions and fail-closed verdicts
- Protected-path, secret, destructive SQL, auth downgrade, dangerous execution, lockfile, and atomic-size rules
- Impact-aware risk flags and architecture/contract lock requirements
- External patch ingestion and deterministic mutation-guided proof-hardening proposals
- Human approval records with one-time approval tokens; only token hashes are persisted
- Repository-state compare-and-swap before mutation
- Atomic byte backups, transaction manifests, and automatic restoration
- Full before/after proof comparison in temp or Docker sandboxes
- Automatic rollback for failed or regressive proof
- Manual rollback guarded by current-state safety checks
- Loop Governor with maximum attempts and repeated-patch/oscillation detection
- Persistent agent run, policy, approval, proof-delta, state-transaction, and audit artifacts
- New CLI commands under `basalt agent`: `plan`, `approve`, `apply`, `status`, `reject`, `revise`, and `rollback`
- GitHub Actions governed safe-fix transaction smoke test
- 25 Phase 3 tests, bringing the complete suite to 76 tests
- Phase 3 architecture, validation, completion, release, and handoff documentation

### Changed

- Package version upgraded from 2.1.0a1 to 2.2.0a1
- Product identity updated to the Basalt v2.2 Alpha Safe Fix Platform
- Feature graph extended with agent runtime, policy, state transaction, and Loop Governor mappings

### Preserved

- All Phase 1 proof, sandbox, mutation, security, scoring, dashboard, and CI capabilities
- All Phase 2 Project Knowledge Graph, freshness, impact-analysis, and Context Compiler capabilities

## 2.1.0-alpha.1 — Phase 2 Knowledge Platform

### Added

- Persistent SQLite-backed AST-Anchored Project Knowledge Graph
- Deterministic file hashes, parser versioning, and project state hashes
- Python AST extraction for functions, classes, signatures, calls, inheritance, and API routes
- JavaScript/TypeScript extraction for imports, functions, components, classes, interfaces, types, Express routes, and Next.js route handlers
- SQL schema and reference extraction
- File, symbol, dependency, route, schema, feature, and test-mapping graph entities
- Explicit feature maps through `basalt.features.json`
- Graph freshness detection for changed, new, removed, and reused files
- Automatic graph refresh and stale-graph fail-closed mode
- Reverse-dependency change-impact analysis
- Task-specific Context Compiler with role, task, target, feature, test, and dependency scoring
- Token-budgeted context packs with context precision metrics
- Versioned and latest context-pack JSON/Markdown artifacts
- New CLI commands: `basalt graph build`, `basalt graph status`, `basalt graph query`, `basalt impact`, and `basalt context`
- Knowledge graph artifacts in every proof run: SQLite database, graph manifest, JSON, and Markdown
- 21 Phase 2 tests, bringing the complete suite to 51 tests
- Phase 2 architecture, validation, completion, release, and handoff documentation

### Changed

- Package version upgraded from 2.0.0a1 to 2.1.0a1
- Basalt product identity updated to the v2.1 Alpha Knowledge Platform
- The former AST preview now uses the persistent Phase 2 graph engine
- Proof reports and the Command Center now include graph state, features, routes, schemas, and test mappings
- Mutation self-verification uses a targeted proof test while the normal proof gate still runs the full suite
- GitHub Actions now validates graph build, freshness, impact analysis, and context compilation

### Preserved

- All Phase 1 sandbox, security, dependency, mutation, scoring, CI, dashboard, and proof-artifact capabilities

## 2.0.0-alpha.1 — Phase 1 Alpha Proof Platform

### Added

- Docker-preferred automatic sandbox with safe fallback and fail-closed mode
- Install-only Docker network policy and resource limits
- Python/FastAPI/Node/React/Vite/Next.js project detection
- `basalt inspect` command
- Multi-candidate deterministic mutation testing
- Python and Node dependency hygiene scanning
- GitHub Actions workflow-permission checks
- Proof-score breakdown and minimum verified score
- Language counts in AST graph preview
- Expanded Command Center dashboard
- 30 unit and integration tests
- Python 3.11 and 3.13 CI matrix
- Alpha documentation and validation report

### Changed

- Package version upgraded from 1.5.1 to 2.0.0a1
- Default sandbox changed from `temp` to `auto`
- Low-severity findings are grouped into non-blocking cleanup suggestions
- Security scan exclusions support prefixes and glob patterns
- Explicit `null` commands now disable inferred commands
- Project detection now uses Python AST imports to avoid false FastAPI detection

### Preserved

- Repository verification
- Proof scoring and verdicts
- Security and policy blocking
- Auto proof-hardening fixes
- Before/after proof comparison
- PR packs and dashboard artifacts
