# Basalt MVP v1.5 — Final Proof-to-PR Demo MVP

**Polished package version:** `1.5.1`

Basalt is a proof-first, prevention-first AI software factory. This MVP is the final demo-ready core engine: it verifies repositories, detects weak proof, generates additive fix patches, reruns proof, produces before/after evidence, and creates PR-ready artifacts.

This is **not** the full autonomous Basalt product yet. It is the final MVP of the core wedge: **verified software, not vibes.**

## What v1.5 includes

- `basalt verify <repo>` — proof check runner
- `basalt fix <repo> --apply --rerun` — auto-generates additive tests, applies them, reruns proof, and writes before/after proof comparison
- `basalt pr <repo>` — GitHub PR-ready pack with branch commands and PR body
- `basalt demo` — one-command final demo flow
- Temp workspace sandbox by default
- Docker sandbox option: `--sandbox docker`
- Policy Kernel command allowlist
- Security, secret, auth-risk, destructive SQL, dependency hygiene, and quality scanning
- Mutation testing for weak-test detection
- AST-Anchored Project Graph preview
- Premium Command Center HTML dashboard with configured-check clarity (`2/2 passed · 3 skipped`, not misleading `2/5`)
- Markdown + JSON proof reports
- Patch plan, fix patch, generated tests, GitHub PR pack

## Install locally

```bash
cd basalt-mvp-v1.5-full
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -e .
```

Python 3.10+ works. Python 3.14 works on macOS.

## Run the final demo

```bash
basalt demo
open basalt-demo-run/demo_weak/.basalt/basalt-dashboard.html
open basalt-demo-run/demo_weak/.basalt/before-after-proof.md
```

The demo shows:

- `demo_good` → `VERIFIED`
- `demo_weak` → `WEAK_PROOF`
- Basalt auto-generates proof-hardening tests
- `demo_weak` after fix → `VERIFIED`
- `demo_policy_violation` → `BLOCKED_BY_POLICY`
- `demo_node_weak` → JavaScript/Node weak-proof detection

## Core commands

```bash
basalt verify examples/demo_good
basalt verify examples/demo_weak
basalt fix examples/demo_weak --apply --rerun
basalt pr examples/demo_weak
basalt doctor
```

## Test on your own repo

```bash
cd /path/to/your/repo
basalt init . --force
basalt verify .
basalt fix . --apply --rerun
basalt pr .
```

For real projects, edit `basalt.yaml` so Basalt runs your actual build/test commands.

## Why this MVP matters

Most coding tools stop at generated code or passing tests. Basalt tests the proof itself with mutation testing, policy checks, AST-backed evidence, and before/after verification. It is designed to answer the question: **can this software be trusted?**

## Final MVP scope

Included in MVP:

- Proof Layer
- Weak-proof detection
- Auto-fix for safe additive tests
- Dashboard
- PR-ready artifacts
- Real repo verification path

Post-MVP:

- Full Product Brain
- 12 autonomous specialist agents
- Full app generation
- Deployment automation
- Enterprise workspace
- Long-term maintenance agent
