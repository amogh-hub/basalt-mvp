# Basalt v2.0 Alpha Proof Platform

**Version:** `2.0.0a1`

Basalt is a proof-first, prevention-first AI software platform. The Phase 1 alpha verifies real repositories, challenges test suites with mutation testing, scans security and dependency risk, runs checks in an isolated sandbox, and produces PR-ready evidence.

> **Core promise:** Verified software, not vibes.

This is the official **Phase 1 — Alpha Proof Platform**. It is not yet the full autonomous AI Software Factory described in the Founder Vision.

## What Phase 1 includes

- Automatic project detection for Python, FastAPI, Node, React, Vite, and Next.js
- `basalt inspect` for detected commands and sandbox policy
- Docker-preferred `auto` sandbox with safe temporary-workspace fallback
- Install-only network policy for dependency installation; checks run with network disabled
- Command allowlist and fail-closed Docker option
- Build, lint, type-check, and test execution
- Multi-candidate deterministic mutation testing
- Secret, auth-risk, destructive SQL, workflow-permission, dependency, and maintainability scanning
- AST-anchored source, symbol, import, test-file, and language preview
- Transparent proof-score breakdown
- `VERIFIED`, `WEAK_PROOF`, `NOT_VERIFIED`, `NEEDS_HUMAN_REVIEW`, and `BLOCKED_BY_POLICY` verdicts
- Auto proof-hardening fixes for supported Python and JavaScript boundary cases
- Markdown, JSON, dashboard, patch-plan, and PR-description artifacts
- GitHub Actions proof gate with downloadable evidence
- Python 3.11 and 3.13 CI coverage

## Install

```bash
cd basalt-mvp-v1.5-full
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

## First run

```bash
basalt doctor
basalt inspect .
basalt verify .
open .basalt/basalt-dashboard.html
```

When Docker is installed and running, `sandbox.mode: auto` uses Docker. When Docker is unavailable and `fallback_to_temp: true`, Basalt uses an isolated temporary copy and records the fallback in the proof report.

## Core commands

```bash
basalt init /path/to/repo
basalt inspect /path/to/repo
basalt verify /path/to/repo
basalt fix /path/to/repo --apply --rerun
basalt pr /path/to/repo
basalt explain /path/to/repo/.basalt/proof-report.json
basalt demo
```

## Proof artifacts

Each run can generate:

```text
.basalt/proof-report.json
.basalt/proof-report.md
.basalt/basalt-dashboard.html
.basalt/basalt-patch-plan.md
.basalt/github-pr-description.md
```

## GitHub Actions

The included workflow:

- runs unit tests on Python 3.11 and 3.13;
- runs Basalt verification;
- enforces a `VERIFIED` verdict;
- writes a GitHub job summary;
- uploads the full `.basalt/` evidence directory.

## Built-in alpha demo

```bash
basalt demo
```

Expected proof story:

- `demo_good` → `VERIFIED`
- `demo_weak` → `WEAK_PROOF`
- auto proof-hardening → `VERIFIED`
- `demo_node_weak` → `WEAK_PROOF`, then `VERIFIED`
- `demo_policy_violation` → `BLOCKED_BY_POLICY`

## Configuration

Create a starter configuration:

```bash
basalt init . --force
```

Important sandbox settings:

```yaml
sandbox:
  mode: auto
  docker_image: python:3.13-slim
  network: install-only
  fallback_to_temp: true
```

Use `fallback_to_temp: false` when Docker isolation is mandatory and verification must fail closed if Docker is unavailable.

## Current boundary

Phase 1 is a serious alpha proof platform. It does not yet include the Product Brain, full Project Knowledge Graph, Context Compiler, governed multi-agent engineering, deployment orchestration, or continuous maintenance system. Those belong to later official Basalt phases.

See:

- `docs/ALPHA_V2.md`
- `docs/REAL_REPO_GUIDE.md`
- `docs/SECURITY_AND_SANDBOX.md`
- `docs/VALIDATION_REPORT.md`
- `docs/PHASE1_COMPLETION.md`
