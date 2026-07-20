# Phase 7 Master Specification — Production Basalt v1

## Product contract

Phase 7 creates one connected proof-first engineering product:

1. **Build Workspace** — repository files, search, editing, configured execution, diagnostics, diff review, proof, activity, and Git truth.
2. **Command Center** — product planning, governed factory work, architecture, proof, transactions, approvals, local control-plane state, operations, and evidence.

Repository truth overrides model memory. Prevention precedes debugging. Mutations require explicit authority. Evidence must be attributable. Rollback must preserve history.

## RC4 delivered source scope

### Daily engineering continuity

- multi-file tabs and unsaved-state tracking;
- line-number and syntax-layer synchronization;
- exact file/line/column diagnostic navigation;
- session restoration of tabs, active file, unsaved buffers, cursor, scroll, search, panel selection, and pane dimensions;
- command palette filtered to available commands;
- bounded console and responsive contained layout.

### Governed editing and stale protection

- optimistic repository hashes;
- diff-before-save;
- parse-error save gate;
- stale source conflict detection;
- explicit reload and discard confirmation;
- atomic source replacement;
- append-only workspace events.

### Proof truth

- applicable, failed, warning, and not-applicable check counts;
- truthful skipped-check labels;
- deterministic score breakdown;
- mutation evidence;
- security and policy findings;
- graph freshness and state hashes;
- bounded lint inference that avoids generated Basalt state.

### Approval and transaction truth

- complete patch preview and directly changed scope;
- separate calculated impact radius;
- policy verdict, reasons, flags, locks, and required approvals;
- base and current state hashes;
- proposer, approver, timestamps, proof links, evidence, and rollback state;
- automatic list/detail synchronization after state transitions;
- append-only agent and factory rollback evidence.

### Factory execution truth

- stable topological task ordering;
- cycle and unresolved-dependency rejection;
- `DETERMINISTIC_LOCAL` execution mode;
- non-contradictory timestamps;
- explicit materialized artifacts;
- no false claim of remote autonomous execution.

### Product intelligence surfaces

- source-derived architecture layers and modules;
- API route discovery;
- SQLite/table/schema discovery;
- cross-module dependency signals;
- AST-backed Project Knowledge Graph;
- impact and context compilation tools.

### Preview

- same-origin static preview;
- explicit start and stop controls;
- no arbitrary shell or server-side project execution;
- protected-path, file-type, traversal, symlink, and size enforcement.

### Git review

- repository detection;
- branch, upstream, divergence, remote-name, and clean/dirty truth;
- staged, unstaged, untracked, and conflict summaries;
- read-only file diffs and recent commit history;
- browser commit, push, and branch mutation disabled.

### Local control plane and operations

- persistent local users, teams, memberships, projects, jobs, providers, and deployments;
- lease-based durable job semantics and isolated workspaces;
- proof-gated deployment packaging and rollback records;
- local incident synthesis from proof, graph, jobs, deployments, preview, approvals, and rollback readiness;
- explicit statement that external uptime is not observed.

### Evidence provenance

- grouping by repository proof, agent run, factory run, or control plane;
- content schema and MIME type;
- origin, timestamps, size, and relative evidence path;
- SHA-256 integrity;
- honest mutable-local-evidence classification;
- content retrieval even when evidence storage is outside the repository.

### Accessibility foundations

- semantic section headings and navigation;
- skip link;
- status live region;
- keyboard-compatible controls;
- visible focus treatment;
- reduced-motion support.

## Security invariants

- arbitrary shell is disabled in the browser;
- only configured or bounded inferred commands execute;
- path escape and protected-directory access fail closed;
- symlinks fail closed in isolated workspaces;
- browser mutations require same-origin, host validation, action mode, and the launch token;
- one-time approval tokens are hash-stored and single-use;
- stale writes cannot silently overwrite source;
- state rollback appends evidence instead of deleting history.

## Release acceptance gates

1. Python compilation.
2. JavaScript syntax validation.
3. Full automated suite.
4. RC4 regression suite.
5. Critical proof matrix.
6. Temp-sandbox self-verification.
7. Docker verification where Docker is available.
8. Governed proposal/approval/token/apply/proof/rollback workflow.
9. Full Command Center browser acceptance.
10. Full Build Workspace browser acceptance in a real Git repository.
11. Identity and branding audit.
12. Evidence and provenance audit.
13. Transaction synchronization and rollback audit.
14. Clean reviewed Git diff and reproducible archive checksum.

## Honest infrastructure boundary

The RC4 source contains the local production product and governed integration foundations. Hosted identity, billing, remote workers, microVM isolation, cloud secret management, real provider deployment execution, external monitoring, paging, enterprise SSO, and compliance certification require external systems and credentials. They are not represented as live merely because interfaces or local ledgers exist.

## Phase 7 completion interpretation

The **Phase 7 local source implementation** is complete in RC4. The **Phase 7 release** remains a candidate until project-Mac browser acceptance and environment-dependent gates pass. Production GA is not claimed by this document.
