# Basalt v2.0.0-alpha.1 Release Notes

Basalt v2.0.0-alpha.1 is the first complete Phase 1 proof-platform release.

It upgrades the original Proof-to-PR demo into a sandboxed repository verification system with richer project detection, deterministic multi-mutation testing, dependency and workflow security checks, transparent scoring, an improved dashboard, CI matrices, and downloadable proof evidence.

## Release title

`Basalt v2.0.0-alpha.1 — Alpha Proof Platform`

## Release message

Basalt verifies repositories, detects weak proof through mutation testing, scans security and dependency risks, runs checks in an isolated sandbox, and produces PR-ready evidence. This release completes the official Phase 1 foundation for the longer-term Basalt AI Software Factory.

## Known alpha limitations

- Live Docker execution must be confirmed on a machine with Docker installed.
- Monorepos should be verified package by package.
- Static findings can require human review.
- Auto-fix deliberately supports only narrow, safe additive-test cases.
- Full codebase knowledge graphs and context compilation belong to Phase 2.
