# Phase 7 Handoff — Basalt v3 Production Candidate RC4

Version: `3.0.0rc4`

## Handoff status

RC4 is the hardened Phase 7 local source candidate. It preserves the accepted RC3 baseline and implements the RC4 correction ledger plus the remaining local Phase 7 product surfaces: architecture/API/database truth, safe static preview, richer read-only Git review, local control-plane visibility, operations/recovery state, evidence provenance, dependency-truthful factory records, and append-only factory rollback.

## Automated acceptance

- full suite: **224 tests passed**
- critical proof matrix: **103 tests passed**
- repository self-verification: **VERIFIED, 98/100**
- Python compilation: **PASS**
- Command Center JavaScript syntax: **PASS**
- Workspace JavaScript syntax: **PASS**
- HTTP/API authorization and lifecycle tests: **PASS**

Docker was unavailable in the delivery environment. Headless Chromium navigation was blocked by the environment administrator, so final visual browser revalidation must run on the project Mac before publishing RC4.

## Run

```bash
python -m pip install -e .
python -m unittest discover -s tests -p 'test_*.py'
python tests/run_proof_matrix.py
basalt verify . --sandbox temp
basalt command-center . --allow-actions
```

Open `/` for Command Center and `/workspace` for Build Workspace.

## Release rule

Do not publish or tag the GitHub prerelease until:

1. the installer has passed on the project Mac;
2. the complete browser acceptance checklist passes in the RC4 Git repository;
3. Git status and the release diff are reviewed;
4. the RC4 archive checksum is recorded.

The accepted RC3 tag remains the rollback baseline.
