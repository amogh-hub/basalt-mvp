# Changelog

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
