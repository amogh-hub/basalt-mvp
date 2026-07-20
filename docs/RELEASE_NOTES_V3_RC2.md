# Basalt v3.0.0 RC2

Workspace layout and truth-label correction release candidate.

## Fixed

- Build Control output is now constrained to the workspace viewport.
- The terminal receives an independent vertical and horizontal scroll area and no longer renders beneath the status footer.
- The shell, editor, file tree, and right rail use `minmax(0, 1fr)` and explicit overflow boundaries.
- The workspace header now identifies Basalt v3 Production Workspace and the active RC version.
- Generated `*.egg-info` directories are hidden from the normal repository tree and search results.
- Phase 6 is correctly marked COMPLETE in the README roadmap.

## Validation

- Full configured repository test command passed before this patch: 201 tests.
- RC2 adds regression coverage for terminal containment and generated-metadata exclusion.
