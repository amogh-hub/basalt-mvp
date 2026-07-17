# Basalt v2.0 Alpha Proof Platform

Phase 1 turns the original demo MVP into a repository-proof platform.

## Verification pipeline

```text
Repository
→ project and command detection
→ isolated workspace
→ Docker-preferred command execution
→ build/lint/type/test checks
→ security and dependency scan
→ AST graph preview
→ mutation testing
→ proof score and verdict
→ dashboard and PR evidence
```

## Verdict meanings

- `VERIFIED`: required checks passed, no policy blockers remain, mutations were killed, and the proof score meets the configured minimum.
- `WEAK_PROOF`: normal tests passed but one or more controlled mutations survived.
- `NOT_VERIFIED`: a configured command failed or required proof is missing.
- `NEEDS_HUMAN_REVIEW`: deterministic proof passed but risk or score policy still needs judgment.
- `BLOCKED_BY_POLICY`: a high-risk secret, unsafe workflow, destructive migration, or other blocking finding exists.

## Proof score

The report contains every score component. Low findings are informational. Medium and high findings reduce the score. Survived mutations reduce it heavily; killed mutations add a small strength bonus.

## Supported repository families

- Python packages and scripts
- FastAPI repositories
- Node.js repositories
- React repositories
- Vite/React repositories
- Next.js repositories

Commands can always be overridden in `basalt.yaml`.
