# Basalt Command Center

The Command Center is a truth-compression interface over Basalt's proof, repository knowledge, and governed agent transaction systems.

## Design rule

The interface shows what is being verified, what is proven, what is risky, what needs human judgment, and where evidence lives. It does not expose every internal heartbeat or raw planner detail by default.

## Architecture

```text
Browser UI
    ↓ same-origin HTTP
Command Center Server
    ↓
CommandCenterService
    ├── Proof reports
    ├── Project Knowledge Graph
    ├── Impact analysis
    ├── Context Compiler
    ├── Agent transaction runtime
    ├── Approval and rollback operations
    └── Evidence vault
```

The server uses Python's standard-library threaded HTTP server. The UI is packaged with Basalt and does not require Node.js, a CDN, or an external web service.

## Operating modes

### Read-only

Default. Provides truth, analysis, and evidence. Source-changing actions are rejected.

### Governed actions

Enabled with `--allow-actions`. Verify, approve, reject, apply, and rollback requests require the per-launch action token. Underlying Policy Kernel, one-time approval, state-hash, proof, and rollback rules remain authoritative.

## Truth snapshot

`basalt command-center . --snapshot --json` produces the same compact model used by the web app:

- project identity and current state hash;
- proof verdict and score;
- risk and graph freshness;
- check, finding, and mutation counts;
- graph metrics;
- pending approvals;
- recent transactions;
- evidence artifacts;
- roadmap state.

## UI surfaces

- Overview
- Proof
- Knowledge
- Transactions
- Approvals
- Evidence

## API stability

Phase 4 APIs are namespaced under `/api/v1`. The API is local and repository-scoped. It is not an internet-facing multi-tenant contract.
