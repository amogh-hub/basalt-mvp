# Basalt MVP Scope

## MVP name
Basalt Proof-to-PR MVP

## MVP promise
Give Basalt a repository. Basalt proves whether the repo is verified, weakly proven, not verified, or blocked by policy. It produces a proof report, dashboard, and PR-ready patch plan.

## Why this MVP is the right wedge
The final Basalt vision is a full AI software factory. But the most defensible first product is not another code generator. The first product is the trust layer: proof that software is actually safe, tested, and ready to improve.

## Included systems
- Proof Layer
- Basic Policy Kernel
- Capability-inspired command allowlist
- Safe temp workspace sandbox
- Optional Docker sandbox
- Security scanner
- Mutation testing sample
- AST-anchored graph preview
- Command Center dashboard
- Proof-to-PR patch plan

## Excluded from MVP
- 12 specialized autonomous agents
- Full Product Brain
- Full app generation
- Production deployment automation
- Full enterprise connector layer
- Long-term maintenance mode

## Acceptance criteria
- Good demo returns VERIFIED.
- Weak demo returns WEAK_PROOF.
- Policy violation demo returns BLOCKED_BY_POLICY.
- Reports are generated in JSON and Markdown.
- Dashboard opens in browser.
- Patch plan gives actionable PR remediation.
