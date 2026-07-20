# Alpha AI Software Factory

Phase 5 is Basalt's first end-to-end factory loop.

## Workflow

```text
Product intent
→ Product Brain
→ Prevention-First Engineering
→ State and contract locks
→ Epoch task graph
→ Model routing
→ Specialist execution in staging
→ Basalt verification
→ VERIFIED-only target assembly
→ State commit and evidence
```

## Supported output

The alpha generates bounded Python service foundations, with an optional dependency-free static web surface. It is intentionally narrower than the final architecture so the orchestration and trust loop can be proven before expanding breadth.

## Atomic assembly

The target must not exist before a build starts. Work is generated in a staging directory. Only a verified result is copied to the target. Failure aborts the state transaction and removes the staging workspace.
