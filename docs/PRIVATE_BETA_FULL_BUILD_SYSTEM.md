# Private Beta Full Build System

Basalt Phase 6 introduces a persistent private-beta control plane around the Phase 5 software factory.

## Control-plane layers

1. **Workspace Registry** — users, teams, memberships, projects, roles, and activity.
2. **Durable Job Queue** — persistent build/verify/package work with worker leases and retries.
3. **Workspace Runtime** — bounded disposable source copies with safe environment policy.
4. **Provider Registry** — local and explicitly configured OpenAI-compatible model providers.
5. **Software Factory** — Product Brain, prevention locks, epochs, specialist tasks, and proof-backed assembly.
6. **Deployment Manager** — immutable verified packages, approvals, promotions, restores, and rollbacks.
7. **Command Center** — human-readable projects, jobs, providers, deployments, proof, and decisions.

## Private-beta job flow

```text
Registered project
→ authorised job submission
→ durable queue
→ worker claim and lease
→ isolated workspace or factory target
→ proof and policy
→ durable result and activity event
→ optional verified deployment package
```

## Failure rules

- stale or unauthorised actions fail closed
- source repositories are not used as generated-product targets
- symlinks and excessive workspace size are rejected
- credentials are never written to provider snapshots
- unverified products cannot be packaged
- staging and production records require explicit approval
- deployment archives are verified before restore

## Production boundary

The Phase 6 runtime is a local private-beta reference implementation. The databases and job semantics are intentionally designed so PostgreSQL, Redis/Temporal, object storage, secret vaults, and cloud deployment adapters can replace the local backends in Phase 7 without changing Basalt's governance model.
