# Basalt v3.0.0 RC3 — Professional Engineering Workspace

RC3 advances the secure Phase 7 workspace foundation into a professional daily coding surface.

## Added

- multi-file tabs with unsaved indicators
- line numbers, cursor position and file metadata
- local syntax highlighting for supported text formats
- live Python, JSON and TOML diagnostics
- governed unified-diff review before atomic save
- stale repository conflict detection and reload
- contextual repository search with line previews
- read-only Git branch, commit and changed-file visibility
- Build, Proof, Activity and Git panels
- command palette and keyboard shortcuts
- persistent resizable explorer and engineering panels
- contained console controls and improved workspace hierarchy

## Security

- arbitrary shell execution remains disabled
- configured commands only
- protected paths and repository boundary checks remain fail-closed
- mutating browser actions continue to require the per-launch action token
- diff and diagnostics are read-only inspection operations

## Validation

- 19 Phase 7 workspace tests pass
- 185 non-Phase-3 repository tests pass in the delivery container
- Python compilation passes
- workspace JavaScript syntax passes
- expected complete Mac suite: 210 tests

## Boundary

RC3 does not yet include agent execution, live application preview, architecture canvases, hosted identity, distributed production workers, cloud deployment connectors, monitoring or final production acceptance.
