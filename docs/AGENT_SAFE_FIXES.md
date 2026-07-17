# Agent-Assisted Safe Fixes

Phase 3 introduces a governed transaction boundary between an agent proposal and repository mutation.

## Trust boundary

An agent may:

1. receive a task-specific Context Compiler pack;
2. inspect deterministic Project Knowledge Graph truth;
3. propose a unified diff;
4. explain intent and targets.

An agent may not directly commit an accepted change. Basalt owns policy review, approval, application, verification, rollback, and audit evidence.

## Transaction flow

```text
PLAN
  capture repository state
  refresh graph
  compile context
  run before proof
  ingest or generate candidate patch

PREFLIGHT
  parse unified diff
  reject unsafe paths/binary patches
  apply in isolated copy
  compute patch size and impact

POLICY
  check role capabilities
  enforce protected paths and risk rules
  require locks/review where needed
  return ALLOW / REQUIRE_HUMAN_APPROVAL / BLOCK

APPROVAL
  human records identity and reason
  Basalt emits a one-time token
  only the token hash is persisted

APPLY
  compare current state with proposal base state
  create atomic backup
  apply patch

VERIFY
  run complete Basalt proof in sandbox
  compare before and after verdicts, scores, mutations, and findings

COMMIT OR ROLLBACK
  accept only VERIFIED non-regression
  otherwise restore original bytes automatically
  persist transaction and audit evidence
```

## Proposal sources

Phase 3 supports:

- **External unified diffs:** produced by a human, local model, IDE agent, or future Basalt model router.
- **Built-in proof hardening:** a narrow deterministic generator that strengthens selected Python boundary tests using mutation evidence.

The built-in generator is intentionally limited. Full model orchestration is not claimed in Phase 3.

## Acceptance rule

A patch is never accepted because it looks reasonable. It must:

- still match the repository state against which it was planned;
- pass patch preflight;
- pass Policy Kernel review;
- satisfy required human approval;
- preserve or improve proof;
- finish as `VERIFIED`;
- introduce no proof regression.

## Agent court

The run records deterministic review actions from Testing, Security, and Code Review roles. These actions summarize evidence and policy conclusions. They are auditable role outputs, not a claim that multiple autonomous LLMs are already running.
