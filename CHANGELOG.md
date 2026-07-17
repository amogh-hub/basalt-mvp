# Changelog

## 2.0.0-alpha.1 — Phase 1 Alpha Proof Platform

### Added

- Docker-preferred automatic sandbox with safe fallback and fail-closed mode
- Install-only Docker network policy and resource limits
- Python/FastAPI/Node/React/Vite/Next.js project detection
- `basalt inspect` command
- Multi-candidate deterministic mutation testing
- Python and Node dependency hygiene scanning
- GitHub Actions workflow-permission checks
- Proof-score breakdown and minimum verified score
- Language counts in AST graph preview
- Expanded Command Center dashboard
- 30 unit and integration tests
- Python 3.11 and 3.13 CI matrix
- Alpha documentation and validation report

### Changed

- Package version upgraded from 1.5.1 to 2.0.0a1
- Default sandbox changed from `temp` to `auto`
- Low-severity findings are grouped into non-blocking cleanup suggestions
- Security scan exclusions support prefixes and glob patterns
- Explicit `null` commands now disable inferred commands
- Project detection now uses Python AST imports to avoid false FastAPI detection

### Preserved

- Repository verification
- Proof scoring and verdicts
- Security and policy blocking
- Auto proof-hardening fixes
- Before/after proof comparison
- PR packs and dashboard artifacts
