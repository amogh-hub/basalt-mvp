# Phase 7 Master Specification — Production Basalt v1

## Product contract

Phase 7 turns Basalt into a daily-use engineering product composed of two connected surfaces:

1. **Build Workspace** — repository truth, files, editing, configured execution, proof and governed changes.
2. **Command Center** — architecture, proof, transactions, approvals, releases, evidence and operational risk.

Basalt remains governed by proof before trust, repository truth over model memory, prevention before debugging, least-privilege execution, explicit human approval, and append-only evidence.

## Delivered in v3.0.0-rc.3 — Professional Engineering Workspace

### Daily coding surface

- multi-file tabs with active and unsaved-change states
- repository explorer with collapsible directories, file-type markers and generated-folder exclusion
- contextual repository search with file, line and source preview
- line-number gutter, cursor position, language and file metadata
- local syntax highlighting for the primary supported text formats
- editor keyboard handling and command shortcuts
- command palette for files, commands and engineering panels
- persistent resizable explorer and engineering-panel widths

### Governed editing

- optimistic concurrency hashes for every opened file
- live Python, JSON and TOML parse diagnostics plus bounded hygiene warnings
- governed unified-diff review before every save
- addition and deletion counts
- diagnostic-error save gate
- stale repository conflict detection
- explicit repository-version reload path
- atomic saves and append-only workspace evidence

### Engineering visibility

- integrated Build, Proof, Activity and Git panels
- configured lint, test, typecheck and build execution only
- contained internal console with copy and clear controls
- proof score, check counts and check-level detail
- append-only workspace event timeline
- read-only Git branch, commit, divergence and changed-file visibility

### Security invariants

- arbitrary shell remains disabled
- path traversal and absolute paths fail closed
- `.git`, `.basalt`, virtual environments, dependencies, caches and generated `*.egg-info` directories remain protected
- mutating browser actions retain same-origin, host and per-launch action-token enforcement
- diff, diagnostics, proof, activity and Git inspection are read-only

## Production acceptance gates

- no repository path escape
- no editing protected evidence or VCS internals
- stale writes fail closed
- all mutating browser actions require same-origin action authorization
- only configured or inferred commands may execute
- every write and command emits an append-only event
- diff review precedes every browser save
- parse errors are visible before persistence
- Build Control output remains contained inside the viewport
- all Phase 0–6 tests remain green
- all Phase 7 workspace tests remain green
- browser acceptance confirms tabs, search, diagnostics, diff review, conflicts, panel resizing and command execution
- repository self-verification remains VERIFIED

## Next implementation gates

RC3 is the professional workspace layer, not the whole Production Basalt v1 scope. Remaining Phase 7 work includes:

- agent conversation, planning, routing and live execution timeline
- governed agent patch review connected to files and proof
- live application preview and preview lifecycle controls
- architecture, API and database canvases
- richer Git diff, branch and review workflows
- hosted accounts, organizations and production identity
- managed distributed jobs and hardened remote sandboxes
- real deployment connectors, monitoring, incidents and recovery
- accessibility and usability validation across supported browsers

## Honest boundary

This source release candidate provides a strong local professional Build Workspace and governance surface. It does not claim live cloud hosting, enterprise SSO, managed distributed workers, billing, compliance certification, or provider-specific production deployment infrastructure.
