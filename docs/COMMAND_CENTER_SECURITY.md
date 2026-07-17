# Command Center Security

## Trust boundary

The Phase 4 Command Center is a local developer control plane, not a public web service.

## Default protections

- Loopback-only bind
- Read-only mode
- No permissive CORS
- Same-origin POST enforcement
- Per-launch action token for governed actions
- Request body size limit
- Evidence allowlist
- Path containment checks
- Content Security Policy
- Frame denial
- Referrer denial
- MIME sniffing protection
- No-store response caching

## Unsafe bind

`--unsafe-bind` permits a non-loopback host. It must be used only inside a trusted network and does not convert the alpha server into a production internet service.

## Action token

The action token scopes browser capability to the current server process. It is not a user account credential and is regenerated for each launch unless explicitly supplied by an embedding test or host process.

## Existing governance remains authoritative

The web layer cannot bypass:

- Policy Kernel verdicts;
- agent role capabilities;
- human approval requirements;
- one-time patch approval tokens;
- repository state compare-and-swap;
- proof gates;
- automatic rollback;
- manual rollback safety checks.
