# Phase 4 Handoff — Command Center Web App

## Release target

`v2.3.0-alpha.1`

## Completed scope

- Local Command Center server and static single-page web application
- Truth overview, proof, knowledge, transactions, approvals, and evidence views
- Interactive impact analysis and Context Compiler
- Read-only default and governed action mode
- Localhost-only default bind
- Per-launch action token and same-origin action enforcement
- Evidence allowlist and safe preview
- API and CLI contracts
- Phase 1–3 integration and regression coverage

## Primary commands

```bash
basalt command-center .
basalt command-center . --allow-actions
basalt command-center . --snapshot --json
```

## Merge gate

- complete test suite passes;
- Command Center HTTP smoke test passes;
- self-verification is `VERIFIED`;
- mutation survives: `0`;
- non-low findings: `0`;
- graph fresh;
- pull-request checks green.

## Next phase

Phase 5 begins the Alpha AI Software Factory. It should add bounded orchestration and real agent execution on top of the proven Command Center, not bypass the Policy Kernel or proof transaction model.
