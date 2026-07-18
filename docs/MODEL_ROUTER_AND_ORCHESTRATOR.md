# Model Router and Specialist-Agent Orchestrator

## Provider-neutral routing

The Model Router selects the cheapest available profile that satisfies task capability and privacy requirements.

The built-in alpha profiles are deterministic local planner and template-code-generation engines. An optional OpenAI-compatible adapter can be configured through environment variables. It is unavailable by default.

## Diversity rule

High-risk code generation receives a review assignment from a different model family. Model output remains a proposal; deterministic proof defines acceptance.

## Specialist roles

Phase 5 plans accountable roles for product, architecture, UI design, frontend, backend, database, testing, security, review, documentation, performance, and DevOps work.

Each record includes task, dependencies, risk, locks, model assignment, expected artifact, and completion evidence.
