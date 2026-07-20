# Real Repository Guide

## 1. Inspect detection

```bash
basalt inspect /path/to/repo
```

Review the detected project type, install command, checks, Docker image, and sandbox policy.

## 2. Create configuration

```bash
basalt init /path/to/repo
```

Edit `basalt.yaml` so Basalt uses the repository's real CI commands.

## 3. Verify

```bash
basalt verify /path/to/repo
```

Open the dashboard and review the proof report before accepting the verdict.

## 4. Harden weak proof

```bash
basalt fix /path/to/repo --apply --rerun
```

Auto-fix is intentionally limited to safe additive tests that Basalt can infer confidently. Unsupported cases receive a patch plan rather than speculative code changes.

## Repository-specific notes

### Python and FastAPI

Basalt recognizes unittest and pytest. Dependency installation uses a workspace-local `.basalt-deps` target so packages remain available across isolated Docker commands.

### Node, React, Vite, and Next.js

Basalt prefers lockfile-aware installation: `npm ci`, frozen pnpm, or frozen Yarn installation. It reads package scripts for build, lint, type-check, and test commands.

### Monorepos

The current alpha should be run from the package or service root with its own `basalt.yaml`. Full workspace-aware graph orchestration belongs to Phase 2.
