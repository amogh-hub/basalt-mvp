# Basalt Final MVP v1.5 Scope

Basalt MVP v1.5 is the final demo MVP. It proves the Basalt wedge: a repository is not trusted until the proof is strong.

## MVP acceptance criteria

1. Verify a repo and produce `VERIFIED`, `WEAK_PROOF`, `NOT_VERIFIED`, `NEEDS_HUMAN_REVIEW`, or `BLOCKED_BY_POLICY`.
2. Detect passing-but-weak tests using mutation testing.
3. Generate additive proof-hardening tests for safe Python and JavaScript boundary cases.
4. Apply the fix and rerun proof.
5. Produce before/after proof comparison.
6. Generate PR-ready Markdown, JSON, dashboard, patch plan, and GitHub PR pack.
7. Support real Python, FastAPI, Node, React/Vite, and Next.js repos through inference plus `basalt.yaml`.

## Non-goals

- No full autonomous 12-agent builder.
- No production deployment automation.
- No enterprise team workspace.
- No cloud-hosted Command Center yet.

Those belong after MVP.
