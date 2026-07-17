# Basalt v2.1 Alpha Knowledge Platform

**Version:** `2.1.0a1`

Basalt is a proof-first, prevention-first AI software platform. Phase 2 adds a persistent AST-anchored Project Knowledge Graph and a Context Compiler that selects the smallest useful context for a task instead of sending an entire repository to an AI model.

> **Core promise:** Verified software, not vibes.

This is the official **Phase 2 — Project Knowledge Graph + Context Compiler** alpha. Basalt now understands repository structure and can compile focused engineering context, but it is not yet the full autonomous AI Software Factory.

## Phase 2 capabilities

- Persistent SQLite Project Knowledge Graph
- File hashes and project-state fingerprints
- Python AST extraction for functions, classes, signatures, decorators, calls, inheritance, and API routes
- Deterministic JavaScript/TypeScript extraction for functions, components, classes, imports, and routes
- SQL table, view, and foreign-reference extraction
- Resolved local import graph
- Symbol-level call and containment graph
- File-to-test mappings using imports and naming evidence
- Explicit and inferred feature-to-file maps
- Change-impact analysis across files, symbols, tests, features, routes, and schemas
- Graph freshness checks for changed, new, and removed files
- Automatic stale-graph refresh before context compilation
- Task classification and role-aware context selection
- Token-budgeted context packs with source snippets and selection reasons
- Context precision score
- JSON, Markdown, SQLite, manifest, dashboard, and PR-ready proof artifacts
- All Phase 1 proof, mutation, security, dependency, sandbox, and CI capabilities

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

## Core workflow

```bash
basalt doctor
basalt inspect .
basalt graph build .
basalt graph status .
basalt graph query . login
basalt impact . basalt_proof/knowledge_graph.py
basalt context . \
  --task "Fix stale graph detection" \
  --role CodeReviewAgent \
  --target basalt_proof/knowledge_graph.py
basalt verify .
```

## Project Knowledge Graph commands

```bash
# Build or refresh the persistent graph
basalt graph build /path/to/repo

# Check whether the stored graph matches current file hashes
basalt graph status /path/to/repo

# Search files, symbols, and features
basalt graph query /path/to/repo auth
basalt graph query /path/to/repo login_user --kind function

# Analyze downstream change impact
basalt impact /path/to/repo app/auth.py
basalt impact /path/to/repo login_user --depth 4
```

## Context Compiler

```bash
basalt context /path/to/repo \
  --task "Fix the login redirect bug" \
  --role FrontendAgent \
  --target src/LoginPage.tsx \
  --budget 12000
```

The generated context pack contains:

- project state hash and freshness proof;
- selected files and source snippets;
- relevant symbols and signatures;
- mapped tests and features;
- routes, schemas, and dependencies;
- policy constraints;
- deterministic selection reasons;
- estimated token usage and context precision.

## Explicit feature mapping

Basalt can infer features from paths and symbol names. For stronger product truth, add `basalt.features.json`:

```json
{
  "features": [
    {
      "id": "login",
      "name": "Login",
      "description": "User authentication and session creation",
      "keywords": ["auth", "login", "session"],
      "files": ["app/auth.py", "frontend/LoginPage.tsx"],
      "tests": ["tests/test_auth.py"]
    }
  ]
}
```

## Configuration

```yaml
knowledge_graph:
  auto_refresh: true
  exclude: examples,dist,build

context:
  token_budget: 12000
```

`auto_refresh: true` prevents agents from receiving stale code truth. With automatic refresh disabled, context compilation fails closed until the graph is rebuilt.

## Generated artifacts

```text
.basalt/knowledge-graph.sqlite3
.basalt/project-graph.json
.basalt/project-graph.md
.basalt/graph-manifest.json
.basalt/impact-analysis.json
.basalt/impact-analysis.md
.basalt/context-pack.json
.basalt/context-pack.md
.basalt/context-packs/<context-id>.json
.basalt/context-packs/<context-id>.md
.basalt/proof-report.json
.basalt/proof-report.md
.basalt/basalt-dashboard.html
.basalt/basalt-patch-plan.md
.basalt/github-pr-description.md
```

## Validation

- `51` automated tests
- Self-verification: `VERIFIED 98/100`
- Mutation: killed
- Non-low self-findings: none
- Persistent graph verified through SQLite table assertions
- Freshness tested for changed, new, and removed files
- Python, JavaScript/TypeScript, and SQL graph extraction tested
- Context budgets and role prioritization tested
- Impact and CLI integration tested

## Current boundary

Phase 2 gives Basalt deterministic codebase understanding and focused context. It does not yet allow autonomous agents to apply production-code fixes. That belongs to **Phase 3 — Agent-Assisted Safe Fixes**, where Testing, Security, Review, and limited implementation agents will propose governed patches through the Policy Kernel and human approval gates.

See:

- `docs/PROJECT_KNOWLEDGE_GRAPH.md`
- `docs/CONTEXT_COMPILER.md`
- `docs/PHASE2_COMPLETION.md`
- `docs/PHASE2_VALIDATION_REPORT.md`
- `PHASE2_HANDOFF.md`
