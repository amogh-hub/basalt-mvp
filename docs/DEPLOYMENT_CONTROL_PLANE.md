# Verified Deployment Control Plane

The Deployment Manager creates immutable release artifacts from generated products that already contain Basalt proof evidence.

## Packaging gate

A package is rejected unless:

- `proof-report.json` exists
- final status is `VERIFIED`
- proof score meets the minimum threshold
- the source product exists and is a directory

Basalt writes a compressed archive and SHA-256 digest to the deployment artifact store.

## Environment policy

| Environment | Policy |
|---|---|
| preview | May be promoted immediately after verification |
| staging | Human approval required |
| production | Human approval required |

## Integrity and rollback

- archives are checked against their stored digest
- extraction rejects unsafe paths
- deployment transitions are persisted
- previous promoted deployment records can be restored
- rollback is an explicit ledger event with actor and reason

This is a release-control plane, not a claim of live cloud deployment. Phase 7 will add real provider connectors, canary/shadow rollout, monitoring, and production incident recovery.
