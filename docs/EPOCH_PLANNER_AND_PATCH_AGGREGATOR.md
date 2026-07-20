# Dependency-Aware Epoch Planner and Patch Aggregator

Phase 5 schedules work into dependency-safe waves.

## Epochs

1. Shared Truth — product, architecture, contracts, schema, design rules
2. Implementation — frontend, backend, data, and supporting code
3. Verification — tests, security, and adversarial review
4. Hardening — quality, documentation, accessibility, and performance
5. Release — final proof, manifest, and assembly decision

The task graph is validated as a directed acyclic graph. Cycles are rejected.

## Patch aggregation

Patch proposals that intersect target files or contract locks are grouped into one atomic batch. This prevents repeated invalidation and unsafe partial commits around shared truth.
