# Durable Job Runtime

The Phase 6 job queue replaces request-bound execution with persistent job state.

## State model

```text
PENDING → CLAIMED → RUNNING → SUCCEEDED
                         ↘ RETRY_WAIT → CLAIMED
                         ↘ FAILED
PENDING / RETRY_WAIT → CANCELLED
```

## Guarantees

- SQLite-backed persistence
- optional idempotency keys
- deterministic claim order
- worker ownership enforcement
- expiring leases and heartbeat renewal
- bounded attempts
- retryable versus terminal failures
- cancellation rules
- lifecycle event history

Supported private-beta job types are `VERIFY_PROJECT`, `FACTORY_PLAN`, `FACTORY_CREATE`, and `PACKAGE_PREVIEW`.

The local queue is not presented as a distributed scheduler. Its contracts are the foundation for a PostgreSQL plus Temporal/Redis worker implementation in Phase 7.
