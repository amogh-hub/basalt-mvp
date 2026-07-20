# Basalt v2.5.0 Beta 2

Phase 6 acceptance hotfix for governed product execution from the Command Center.

## Fixed

- `Build and prove` no longer targets a path inside the Basalt source repository.
- Factory products are written to a persistent sibling `basalt-products/` directory.
- Run-specific target names prevent unrelated factory runs from colliding.
- Governed factory errors are returned to the UI with their exact reason.
- A regression test verifies that Command Center builds remain outside the source repository.

## Validation target

- Full automated suite
- Critical proof matrix
- Command Center governed plan-to-build acceptance flow
- Temp and Docker verification
