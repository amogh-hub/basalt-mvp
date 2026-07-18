# Basalt v2.5 Private Beta Full Build System

**Version:** `2.5.0b3`
**Core promise:** **Verified software, not vibes.**

Basalt is a proof-first, prevention-first AI software factory. Phase 6 turns the bounded local alpha factory into a persistent private-beta control plane with projects, team roles, durable jobs, isolated workspaces, provider integrations, broader product templates, verified deployment artifacts, and an expanded Command Center.

Basalt still does not trust generated software because it looks plausible. Work moves forward only through explicit product truth, policy, isolated execution, proof, approvals, and auditable state transitions.

## Phase 6 capabilities

### Persistent users, teams, and projects

The private-beta registry stores:

- users and private teams
- owner, admin, developer, reviewer, and viewer roles
- project registration and status
- project privacy mode and default branch
- append-only activity history

Role checks are enforced before project, job, or deployment actions.

### Durable job execution

Long-running work is represented as persistent jobs rather than browser requests:

- `VERIFY_PROJECT`
- `FACTORY_PLAN`
- `FACTORY_CREATE`
- `PACKAGE_PREVIEW`

The SQLite job runtime provides idempotency keys, worker ownership, leases, heartbeats, cancellation, bounded retries, retry waiting, and lifecycle events.

### Isolated private-beta workspaces

Each job receives a bounded disposable workspace. The runtime:

- rejects symlinks
- excludes Git history, virtual environments, dependencies, caches, and Basalt state
- enforces file and byte ceilings
- copies only allowlisted environment values
- records a source-state hash
- verifies that the registered repository was not changed by isolated verification
- records network policy as denied by default

The current beta uses local workspace copies and the existing temp/Docker proof sandboxes. Warm copy-on-write pools and microVMs remain later infrastructure work.

### Secret-safe provider integrations

Basalt now has a persistent provider inventory and a minimal OpenAI-compatible adapter.

Built-in local profiles remain available for deterministic planning and template code generation. A remote compatible provider is enabled only when these variables are deliberately configured:

```text
BASALT_OPENAI_BASE_URL
BASALT_OPENAI_MODEL
BASALT_OPENAI_API_KEY
```

Credentials are read at execution time. Provider snapshots expose only whether credentials are configured, never their values.

### Broader private-beta product templates

The factory now accepts:

- `python-service`
- `api-service`
- `fullstack-lite`
- `web-app`
- `saas-starter`

`saas-starter` adds a dependency-free multi-tenant foundation with tenant isolation, role checks, subscription gates, tests, documentation, and embedded Basalt proof evidence. These are still governed starter systems, not arbitrary production applications.

### Verified deployment control plane

Basalt can package a product only when its proof report is `VERIFIED` with an acceptable score. It creates an immutable `.tar.gz` artifact with a SHA-256 digest and records it in a deployment ledger.

Supported control-plane environments:

- preview — may promote immediately after proof
- staging — requires explicit approval
- production — requires explicit approval

Promotion, artifact integrity checks, restore, and rollback records are implemented. Phase 6 does **not** claim live cloud-provider deployment; it establishes the private-beta release boundary that Phase 7 will connect to production infrastructure.

### Official Basalt brand integration

The Command Center now uses the official Basalt wordmark supplied by the founder:

- soft off-white wordmark on obsidian in dark mode
- near-black wordmark on a soft light surface
- preserved logo geometry through a reusable mask
- compact mark variants for app surfaces
- no lime, emoji UI, cartoon agents, neon effects, or external UI assets

The Basalt Obsidian design audit now validates both design tokens and required brand assets.

### Private Beta Command Center

The Command Center adds a dedicated private-beta control surface for:

- persistent projects
- durable jobs
- configured model providers
- deployment artifacts and status
- factory runs and proof-backed assembly
- existing proof, knowledge, transactions, approvals, and evidence

The existing security boundary remains: localhost by default, read-only by default, per-launch action token, same-origin validation, Host-header validation, restrictive CSP, and approved artifact access.

## Quick start

Install locally:

```bash
python -m pip install -e .
```

Bootstrap a private-beta workspace:

```bash
basalt beta bootstrap . \
  --email founder@example.com \
  --name "Basalt Founder" \
  --team "Basalt Private Beta"
```

Register a project:

```bash
basalt beta project-add . \
  --team-id TEAM_ID \
  --created-by USER_ID \
  --name "Core Product" \
  --project-repo /path/to/repository \
  --template saas-starter
```

Submit and process durable work:

```bash
basalt beta job-submit . \
  --project-id PROJECT_ID \
  --created-by USER_ID \
  --type VERIFY_PROJECT

basalt beta job-run . JOB_ID
basalt beta jobs .
```

Inspect providers and deployments:

```bash
basalt beta providers .
basalt beta deployments .
```

Launch the Command Center:

```bash
basalt command-center .
```

Enable governed actions deliberately:

```bash
basalt command-center . --allow-actions
```

Create a verified SaaS starter directly through the factory:

```bash
basalt factory create . \
  --prompt "Build a multi-tenant operations platform with roles, subscriptions, an API, and a dashboard." \
  --name "Obsidian Ops" \
  --template saas-starter \
  --privacy local \
  --sandbox temp \
  --target ../obsidian-ops
```

## Existing platform capabilities retained

Phase 6 preserves every completed lower layer:

- proof verdicts and scoring
- temp and Docker sandbox execution
- mutation testing and weak-proof detection
- security, secrets, dependency, workflow, auth, SQL, and quality checks
- GitHub Actions proof gates and evidence artifacts
- AST-anchored Project Knowledge Graph
- graph freshness, feature/test mapping, and impact analysis
- task-specific Context Compiler
- governed agent patch transactions
- Policy Kernel and role capabilities
- human approvals and automatic rollback
- Product Brain and prevention-first engineering
- deterministic State Coordinator
- dependency-safe Epoch Planner and Patch Aggregator
- provider-neutral Model Router
- specialist-agent task orchestration
- VERIFIED-only factory assembly
- Basalt Obsidian Command Center

## Private Beta API

Read-only state:

```text
GET /api/v1/beta
GET /api/v1/beta/projects
GET /api/v1/beta/jobs
GET /api/v1/beta/jobs/<job-id>
GET /api/v1/beta/providers
GET /api/v1/beta/deployments
GET /api/v1/beta/deployments/<deployment-id>
```

Governed actions require `--allow-actions` and the per-launch token:

```text
POST /api/v1/beta/bootstrap
POST /api/v1/beta/projects
POST /api/v1/beta/jobs
POST /api/v1/beta/jobs/<job-id>/run
POST /api/v1/beta/jobs/<job-id>/cancel
POST /api/v1/beta/jobs/<job-id>/retry
POST /api/v1/beta/deployments/<deployment-id>/approve
POST /api/v1/beta/deployments/<deployment-id>/promote
POST /api/v1/beta/deployments/<deployment-id>/rollback
```

## Evidence and storage

Private-beta state is stored under `.basalt/private-beta/` by default:

- workspace and RBAC database
- durable job database and events
- isolated workspace manifests
- provider configuration references
- factory and job artifacts
- deployment ledger
- immutable deployment packages
- private-beta snapshots

Project and proof evidence remain under `.basalt/` and generated product targets.

## Current maturity and honest boundaries

Basalt v2.5 is a **private-beta full build system**, not yet the production Basalt v1 release.

Implemented now:

- persistent local teams and projects
- durable job semantics
- isolated job workspaces
- optional real OpenAI-compatible model calls
- broader governed starter generation
- verified release artifacts and approval gates
- private-beta Command Center experience

Not yet claimed:

- hosted multi-tenant cloud accounts
- production identity provider and billing
- Redis/Temporal distributed workers
- remote secret vault
- warm snapshot pools or microVM isolation
- real AWS/GCP/Azure/Vercel deployment connectors
- production monitoring and incident response
- enterprise compliance certification

Those are Phase 7 production responsibilities and Phase 8 final-vision work.

## Roadmap

```text
Phase 0 — Vision + Grant/Demo MVP                 COMPLETE
Phase 1 — Alpha Proof Platform                    COMPLETE
Phase 2 — Knowledge Graph + Context Compiler      COMPLETE
Phase 3 — Agent-Assisted Safe Fixes               COMPLETE
Phase 4 — Command Center Web App                  COMPLETE
Phase 5 — Alpha AI Software Factory               COMPLETE
Phase 6 — Private Beta Full Build System          ACTIVE
Phase 7 — Production Basalt v1                    UPCOMING
Phase 8 — Full Basalt Final Vision                UPCOMING
```

## License

Basalt is proprietary software. See `LICENSE`.
