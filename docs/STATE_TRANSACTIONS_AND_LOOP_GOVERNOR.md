# State Transactions and Loop Governor

## State Coordinator

Every proposal is anchored to a deterministic repository state hash. Before application, Basalt recomputes the current state and performs a compare-and-swap check.

```text
proposal.base_state == repository.current_state
```

When the values differ, the run becomes `STALE_STATE`; the patch is not applied and must be planned again against current truth.

## Atomic mutation

Before mutation, Basalt records original file bytes and a backup manifest. Patch application is exact-context based. Added, modified, and deleted files are covered. If any step or proof check fails, the original bytes are restored.

## Proof transaction

A successful run records:

```text
base state → candidate patch → policy decision → approval → proof delta → new state
```

The Project Knowledge Graph is refreshed only after the verified repository state is established.

## Loop Governor

Revisions are bounded by policy:

- maximum attempts per run;
- repeated patch-hash detection;
- oscillation prevention;
- fresh policy evaluation for every revision;
- `STUCK` status instead of unbounded retries.

The governor does not hide failure. It stops unsafe or non-converging loops and leaves human-readable evidence.

## Manual rollback

A verified transaction may be manually rolled back only when the current repository still matches the state produced by that transaction. This prevents restoration from overwriting unrelated later work.
