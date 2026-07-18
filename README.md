# Basalt v2.4 Alpha AI Software Factory

**Version:** `2.4.0a1`  
**Core promise:** **Verified software, not vibes.**

Basalt is a proof-first, prevention-first AI software factory. Phase 5 connects product intent, locked engineering truth, dependency-safe planning, governed specialist roles, model routing, staged implementation, adversarial proof, and atomic assembly into one alpha factory loop.

Basalt does not treat generated code as complete because it looks plausible. A factory build is assembled into its target only after the staged product receives a `VERIFIED` proof verdict.

## Phase 5 capabilities

### Product Brain

A product prompt is converted into a structured Product Blueprint containing:

- product summary and target users
- features and requirement IDs
- user flows and acceptance criteria
- non-functional requirements
- explicit assumptions and risks
- constraints, success criteria, and architecture hints

### Prevention-First Engineering

Before implementation, Basalt produces a locked Engineering Plan with:

- contradiction detection
- architecture decisions
- requirement-linked test plans
- risk controls
- API, schema, authentication, payment, product, and design-system contract locks

A contradictory plan is blocked before build work begins.

### Deterministic state coordination

Factory runs use a persistent SQLite State Coordinator for:

- monotonic project state versions
- compare-and-swap transaction commits
- stale-state rejection
- exclusive contract locks
- transaction abort and lock release
- auditable state snapshots

### Epoch Planner and Patch Aggregator

Work is scheduled into five dependency-safe waves:

1. Shared Truth
2. Implementation
3. Verification
4. Hardening
5. Release

Related proposals that intersect files or shared contracts can be grouped into atomic batches instead of being committed independently.

### Specialist-agent orchestration

Phase 5 models accountable roles such as:

- Product Agent
- Architecture Agent
- UI Design Agent
- Frontend Agent
- Backend Agent
- Database Agent
- Testing Agent
- Security Agent
- Code Review Agent
- Documentation Agent
- Performance Agent
- DevOps Agent

Agents receive defined tasks, dependencies, locks, risk levels, expected artifacts, and provider-neutral model assignments. They do not own commit authority.

### Heterogeneous Model Router

The router selects the cheapest available model profile capable of a task while respecting privacy mode. The alpha ships with deterministic local planning and template-code-generation profiles, plus an optional OpenAI-compatible adapter configured through environment variables. High-risk generation requests a separate review family.

### Proof-backed assembly

The factory workflow is:

```text
Intent
→ Product Blueprint
→ Prevention Locks
→ Dependency-Safe Task Graph
→ Model Assignments
→ Staged Specialist Execution
→ Basalt Proof Layer
→ VERIFIED-only Atomic Assembly
→ State Commit and Evidence
```

The target directory is not created or changed before proof succeeds. Failed or stale work is rejected and the state transaction is aborted.

### Basalt Obsidian design system

The Command Center now uses the locked Basalt identity:

- near-black, graphite, obsidian, and steel surfaces
- restrained steel-blue accents
- status colours only for meaningful state
- no lime accent
- no emojis or cartoon agents
- no decorative neon or fake AI activity
- progressive disclosure of technical evidence

The design-system audit checks interface source for legacy lime, emojis, external UI assets, and token drift.

## Supported alpha product templates

Phase 5 deliberately supports two bounded templates:

- `python-service`
- `fullstack-lite`

Both produce dependency-free Python service foundations. `fullstack-lite` also produces a responsive static web surface using the Basalt Obsidian design language. This is an alpha proof of the governed factory loop, not yet arbitrary production application generation.

## Quick start

Install in editable mode:

```bash
python -m pip install -e .
```

Plan a product:

```bash
basalt factory plan . \
  --prompt "Build an authenticated booking platform with a dashboard and notifications." \
  --name "Arena" \
  --template fullstack-lite
```

Plan, build, verify, and assemble:

```bash
basalt factory create . \
  --prompt "Build an authenticated booking platform with a dashboard and notifications." \
  --name "Arena" \
  --template fullstack-lite \
  --privacy local \
  --sandbox temp \
  --target ../arena-product
```

Inspect factory state:

```bash
basalt factory status .
basalt factory models .
basalt factory design-system .
```

Launch the Command Center:

```bash
basalt command-center .
```

Enable governed actions deliberately:

```bash
basalt command-center . --allow-actions
```

## Existing platform capabilities retained

Phase 5 builds on all earlier layers:

- repository verification and proof scoring
- `VERIFIED`, `WEAK_PROOF`, and blocked outcomes
- temp and Docker sandbox execution
- mutation testing and weak-test detection
- security, secret, dependency, workflow, auth-risk, SQL-risk, and quality checks
- GitHub Actions proof gates and evidence artifacts
- persistent AST-anchored Project Knowledge Graph
- Python, JavaScript, TypeScript, TSX, and SQL parsing
- graph freshness and impact analysis
- task-specific Context Compiler
- governed safe-fix transactions
- Policy Kernel and role permissions
- human approval, atomic patching, and automatic rollback
- local Command Center UI and API

## Command Center factory endpoints

Read-only factory state:

```text
GET /api/v1/factory
GET /api/v1/factory/runs
GET /api/v1/factory/runs/<run-id>
```

Governed actions, available only when the server is launched with `--allow-actions` and a valid per-launch token is supplied:

```text
POST /api/v1/factory/plan
POST /api/v1/factory/runs/<run-id>/build
```

## Evidence

Each factory run writes durable artifacts under `.basalt/factory-runs/<run-id>/`, including:

- Product Blueprint JSON and Markdown
- Engineering Plan JSON and Markdown
- task graph and epoch plan
- model assignments
- Basalt design tokens and design audit
- factory manifest
- specialist execution records
- proof reports
- transaction and state evidence

## Security and trust boundaries

- Read-only Command Center by default
- localhost binding by default
- per-launch action token
- same-origin and Host-header enforcement
- restrictive Content Security Policy
- controlled artifact vault
- target untouched until verified
- contract locks before build
- stale-state fail-closed behavior
- proof regression cannot be assembled
- external model adapter disabled unless explicitly configured

## Current maturity and non-goals

Basalt v2.4 is an **alpha software-factory loop**. It proves that structured intent can be converted into a governed, staged, verified product foundation.

It is not yet:

- arbitrary full-stack product generation
- a cloud multi-tenant service
- a team collaboration platform
- a durable distributed workflow system
- warm snapshot or microVM infrastructure
- production deployment and monitoring automation
- the final Basalt vision

Those are intentionally reserved for Phases 6–8.

## Roadmap

```text
Phase 0 — Vision + Grant/Demo MVP                 COMPLETE
Phase 1 — Alpha Proof Platform                    COMPLETE
Phase 2 — Knowledge Graph + Context Compiler      COMPLETE
Phase 3 — Agent-Assisted Safe Fixes               COMPLETE
Phase 4 — Command Center Web App                  COMPLETE
Phase 5 — Alpha AI Software Factory               ACTIVE
Phase 6 — Private Beta Full Build System          UPCOMING
Phase 7 — Production Basalt v1                    UPCOMING
Phase 8 — Full Basalt Final Vision                UPCOMING
```

## License

Basalt is proprietary software. See `LICENSE`.
