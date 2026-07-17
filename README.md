# Basalt v2.3 Alpha Command Center Platform

**Version:** `2.3.0a1`

Basalt is a proof-first, prevention-first AI software platform. Phase 4 turns the verified CLI engine into a local **Command Center Web App** that compresses repository truth into a clear operating surface for proof, risk, knowledge, impact, agent transactions, approvals, and audit evidence.

> **Core promise:** Verified software, not vibes.

This is the official **Phase 4 — Command Center Web App** alpha. It is a secure local control plane over the Phase 1 proof system, Phase 2 knowledge system, and Phase 3 governed safe-fix system. It is not yet the full multi-agent AI Software Factory.

## What Phase 4 adds

- Local browser-based Command Center with no external web dependency
- Truth-compression overview for intent, progress, proof, risk, decisions, and drift signals
- Live proof score, verdict, check, mutation, finding, and sandbox views
- Project Knowledge Graph metrics and freshness status
- Interactive impact analysis for files, symbols, routes, and features
- Interactive task-specific Context Compiler
- Governed state transaction ledger and run detail explorer
- Human approval center for pending agent proposals
- Evidence vault for proof, graph, context, impact, dashboard, and agent-run artifacts
- Read-only mode by default
- Explicit `--allow-actions` mode for verify, approve, reject, apply, and rollback
- Per-launch action token and same-origin request enforcement
- Localhost-only binding by default with explicit unsafe-bind override
- Strict browser security headers and no cross-origin API access
- Stable versioned JSON API under `/api/v1`
- Zero runtime Python dependencies beyond the standard library
- Complete Phase 1–3 compatibility

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

## Launch the Command Center

Read-only mode is the safe default:

```bash
basalt command-center /path/to/repo
```

Basalt binds to `127.0.0.1:7337`, opens the browser, and exposes repository truth without allowing source-changing actions.

Use a different local port:

```bash
basalt command-center /path/to/repo --port 7444
```

Start without opening the browser:

```bash
basalt command-center /path/to/repo --no-open
```

Enable governed actions:

```bash
basalt command-center /path/to/repo --allow-actions
```

When actions are enabled, the browser receives a per-launch action token through the same-origin bootstrap endpoint. Mutating API calls require that token and are rejected when actions are disabled.

Generate a machine-readable snapshot without starting the server:

```bash
basalt command-center /path/to/repo --snapshot --json
```

## Command Center surfaces

### Overview

Shows:

- current intent;
- final proof verdict and score;
- risk level;
- graph freshness;
- checks passed;
- mutation strength;
- pending human decisions;
- roadmap progress;
- recent state transactions.

### Proof

Shows configured checks, sandbox execution, findings, mutations, and proof timing. Raw evidence remains available but is not the default experience.

### Knowledge

Shows files, symbols, edges, mapped features, routes, schemas, tests, and languages. It also exposes interactive impact analysis and Context Compiler workflows.

### Transactions

Shows governed agent runs, policy status, risk, state transitions, proof deltas, and rollback state.

### Approvals

Shows only decisions that require human judgment. Approve and reject controls remain disabled unless the server starts with `--allow-actions`.

### Evidence

Shows whitelisted Basalt artifacts from `.basalt/` and allows safe inline preview. Arbitrary repository files and path traversal are not exposed.

## Local API

Read endpoints:

```text
GET  /api/v1/health
GET  /api/v1/bootstrap
GET  /api/v1/overview
GET  /api/v1/proof
GET  /api/v1/runs
GET  /api/v1/runs/<run-id>
GET  /api/v1/artifacts
GET  /api/v1/artifacts/content/<artifact-id>
GET  /api/v1/graph/query?term=<term>
```

Analysis endpoints:

```text
POST /api/v1/impact
POST /api/v1/context
```

Governed action endpoints, disabled by default:

```text
POST /api/v1/verify
POST /api/v1/runs/<run-id>/approve
POST /api/v1/runs/<run-id>/reject
POST /api/v1/runs/<run-id>/apply
POST /api/v1/runs/<run-id>/rollback
```

Action requests require `X-Basalt-Action-Token` and same-origin validation.

## Security model

- The server binds only to loopback by default.
- Non-loopback binding requires `--unsafe-bind`.
- Source-changing actions are disabled by default.
- Action capability is scoped to a random per-launch token.
- Cross-origin POST requests are rejected.
- No permissive CORS headers are emitted.
- Browser responses use CSP, frame denial, referrer denial, MIME sniffing protection, and no-store caching.
- Request bodies are size-limited.
- Artifact preview is restricted to a known evidence allowlist.
- Existing Policy Kernel, approval, state-hash, proof, and rollback rules remain authoritative.

## Existing platform commands

```bash
basalt doctor
basalt inspect .
basalt graph build .
basalt graph status .
basalt graph query . login
basalt impact . basalt_proof/agent_runtime.py
basalt context . --task "Review transaction safety" --role CodeReviewAgent --target basalt_proof/agent_runtime.py
basalt agent status .
basalt verify .
```

## Validation

- `96` automated tests
- `19` Phase 4 service, API, UI delivery, security, and CLI tests
- Phase 1–3 regression suites preserved
- Local truth snapshot validated
- Static UI and security headers validated
- Read-only action blocking validated
- Per-launch action-token enforcement validated
- Cross-origin request rejection validated
- Impact and Context Compiler API workflows validated
- Approval API and one-time token handling validated
- Temp and Docker self-verification recorded in `docs/PHASE4_VALIDATION_REPORT.md`

## Current boundary

Phase 4 is a local single-repository Command Center. It does not yet provide cloud accounts, team tenancy, remote repository hosting, durable production services, autonomous multi-agent feature delivery, deployment orchestration, or the final software-factory experience. Those belong to Phases 5–8.

See:

- `docs/COMMAND_CENTER.md`
- `docs/COMMAND_CENTER_SECURITY.md`
- `docs/PHASE4_COMPLETION.md`
- `docs/PHASE4_VALIDATION_REPORT.md`
- `docs/RELEASE_NOTES_V2_3_ALPHA.md`
- `PHASE4_HANDOFF.md`
