# Basalt Phase 1 Handoff

This repository is the completed **Basalt v2.0.0-alpha.1 Alpha Proof Platform** package.

## Validation completed in the build environment

- 30 automated tests passed.
- Python compilation passed.
- Editable package installation passed after installing current setuptools and wheel.
- Basalt self-verification returned `VERIFIED 98/100`.
- Built-in Python and Node weak-proof demos were detected and proof-hardened.
- The TaskVault repository was correctly rejected as `WEAK_PROOF` when mutations survived.
- GitHub Actions YAML parsed successfully.

## Final local validation

```bash
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
basalt verify .
```

A machine with Docker installed should show `Sandbox: docker` when `sandbox.mode` is `auto`. Without Docker, Basalt records `temp-fallback` in the report.

## Git steps after review

```bash
git add -A
git commit -m "feat: complete Basalt v2.0 alpha proof platform"
git push
```

Keep PR #1 open until the updated GitHub Actions workflow is green and the downloadable proof artifact appears.
