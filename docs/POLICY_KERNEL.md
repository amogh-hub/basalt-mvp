# Policy Kernel and Capability Permissions

The Policy Kernel is the Phase 3 constitution for patch proposals.

## Verdicts

- `ALLOW`: policy permits the proposal without a mandatory human gate under the configured rules.
- `REQUIRE_HUMAN_APPROVAL`: the proposal may continue only after explicit approval.
- `BLOCK`: the proposal cannot proceed.

Even an `ALLOW` decision does not bypass proof. Every applied transaction must still pass full verification.

## Capability boundaries

Representative defaults:

- Implementation, Builder, Backend, and Frontend agents may propose scoped source changes.
- Testing Agent may propose test changes but cannot modify source code.
- Documentation Agent is limited to documentation files.
- Database Agent may propose compatible database work but destructive SQL is blocked.
- DevOps Agent is restricted by protected infrastructure and deployment paths.
- Security Agent and Code Review Agent are review-only and cannot author patches.

## Mandatory controls

The kernel evaluates:

- file and changed-line ceilings;
- protected paths;
- path traversal and repository metadata paths;
- secret-like content;
- destructive SQL;
- unsafe auth downgrades;
- dangerous execution primitives;
- lockfile changes;
- auth, payment, contract, database, and deployment risk flags;
- Project Knowledge Graph impact risk;
- agent role and target compatibility;
- required architecture/contract locks;
- configured human-approval policy.

## Fail-closed behavior

Unknown roles, forbidden capabilities, missing required locks, destructive changes, and protected path edits do not receive a permissive fallback. They are blocked or escalated for explicit review.
