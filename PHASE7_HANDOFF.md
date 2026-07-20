# Phase 7 Handoff — Production Basalt v1 Release Candidate 3

Version: `3.0.0rc3`

RC3 preserves the accepted RC2 security boundary while adding a professional multi-file workspace, diagnostics, governed diff review, Git visibility, proof/activity panels, command palette and resizable contained layout.

Run:

```bash
python -m pip install -e .
basalt command-center . --allow-actions
```

Open `/workspace` for the Build Workspace and `/` for the Command Center.

Acceptance target:

1. `python -m unittest discover -s tests -p 'test_*.py' -q` → **210 tests, OK**
2. browser acceptance for tabs, search, diagnostics, diff/save, stale conflict, resizing and engineering panels
3. Basalt self-verification

RC2 remains the stable rollback baseline until all RC3 gates pass.
