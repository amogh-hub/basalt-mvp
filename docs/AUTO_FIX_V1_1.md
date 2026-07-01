# Basalt Auto Fix Patch Generator v1.1

v1.1 upgrades the MVP from proof reporting into proof hardening.

## Goal

When Basalt finds weak proof, it should not stop at advice. It should generate a reviewable, PR-ready patch that strengthens the proof.

## Safety rule

v1.1 only generates additive tests. It does not rewrite production code.

## Current supported auto-fix

Python mutation-survival cases:

- `GtE -> Gt`
- `Gt -> GtE`
- `LtE -> Lt`
- `Lt -> LtE`
- `Add -> Sub`
- `Sub -> Add`

For a survived boundary mutation like:

```python
def is_adult(age: int) -> bool:
    return age >= 18
```

Basalt generates tests like:

```python
self.assertTrue(is_adult(18))
self.assertFalse(is_adult(17))
self.assertTrue(is_adult(19))
```

This kills the survived mutation and can move a repo from `WEAK_PROOF` to `VERIFIED`.

## Commands

Generate patch only:

```bash
basalt fix examples/demo_weak
```

Apply and rerun:

```bash
basalt fix examples/demo_weak --apply --rerun
```

## Artifacts

```text
.basalt/fix.patch
.basalt/generated-tests.md
.basalt/fix-summary.json
```
