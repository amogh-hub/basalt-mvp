# Basalt v2.5.0 Beta 3

Transaction-ledger integration hotfix for the Phase 6 private beta.

## Fixed

- The Command Center Transactions page previously displayed only agent safe-fix transactions.
- Committed factory state transitions are now included in the governed transaction ledger.
- Factory transaction inspection now shows base state, committed state, product, task/epoch counts, proof, target, and timestamp.
- The UI explicitly states that factory state rollback is not exposed in Phase 6, while generated outputs remain isolated outside the Basalt source repository.

## Validation target

A verified factory build that commits project state `0 → 1` must appear as a `COMMITTED` Factory transaction.
