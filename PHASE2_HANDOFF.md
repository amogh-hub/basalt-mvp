# Phase 2 Handoff

## Completed release

`v2.1.0-alpha.1`

## Main commands

```bash
basalt graph build .
basalt graph status .
basalt graph query . proof
basalt impact . basalt_proof/proof.py
basalt context . --task "Review proof scoring" --role CodeReviewAgent --target basalt_proof/proof.py
basalt verify .
```

## Phase 3 boundary

Phase 2 selects and explains context but does not authorize agents to edit project truth. Phase 3 must preserve this separation:

1. agents receive a fresh context pack;
2. agents produce a patch proposal;
3. the Policy Kernel checks scope and risk;
4. proof runs in the sandbox;
5. a human approves high-risk actions;
6. only then may the patch be applied.
