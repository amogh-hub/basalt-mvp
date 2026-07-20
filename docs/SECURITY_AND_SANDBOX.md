# Security and Sandbox Model

## Automatic sandbox

`sandbox.mode: auto` prefers Docker. Docker runs receive:

- memory, CPU, and process limits;
- `no-new-privileges`;
- a mounted temporary copy of the repository;
- network disabled for proof checks;
- network enabled only for the install step when `network: install-only`.

If Docker is missing or its daemon is unavailable, Basalt can use a temporary-workspace fallback. The fallback is visible in the proof report. Set `fallback_to_temp: false` to fail closed.

## Command policy

Basalt accepts a restricted family of Python and Node build/test commands and blocks dangerous shell patterns. The alpha does not claim that string filtering alone is a complete security boundary; Docker isolation and human review remain required for untrusted repositories.

## Static scanning

The alpha detects:

- likely API keys, tokens, private keys, JWTs, and provider secrets;
- destructive SQL patterns;
- auth bypass and TLS-disable patterns;
- risky GitHub Actions permissions;
- dangerous package scripts;
- missing lockfiles and non-deterministic dependencies;
- maintainability warnings.

These are conservative signals, not a substitute for professional security review.
