# Deterministic State Coordinator

The State Coordinator is the commit authority for factory project truth.

## Guarantees

- a monotonic state version
- a state hash for the current committed truth
- compare-and-swap transaction commits
- stale-base rejection
- exclusive contract locks
- transaction abort and lock cleanup
- persistent SQLite audit state

## Commit flow

```text
Read current state
→ begin transaction at base version
→ acquire required contract locks
→ build and verify in staging
→ compare current state to base version
→ commit new hash and increment version
→ release locks
```

Agents and model adapters never bypass this flow.
