# Basalt v2.5.0 Beta 4

Private-beta deployment and Approval Center integration hotfix.

## Fixed

- `PACKAGE_PREVIEW` jobs with an empty payload now use the registered project repository instead of incorrectly resolving to the Basalt control repository.
- Preview and staging packaging now resolve the generated product's verified factory proof by default.
- Deployment proof enforcement remains fail-closed and still requires `VERIFIED` proof with a score of at least 80.
- Deployment records in `AWAITING_APPROVAL` now appear in the Command Center Approval Center.
- Approved staging and production deployments remain visible as pending promotion actions.
- Deployment approval and promotion use separate governed UI actions.
- Approval cards show the environment, project, proof score, artifact checksum, and linked durable job.
- The deployment action UI now routes through the existing protected private-beta deployment endpoints.

## Acceptance validation

The Venue Core private-beta lifecycle was validated end to end:

- persistent user, team, membership, and project registration
- durable and idempotent verification jobs
- isolated read-only workspace execution with network denied
- source and workspace integrity hashes
- verified preview packaging and immutable SHA-256 artifact records
- staging package held in `AWAITING_APPROVAL`
- explicit approval followed by explicit promotion
- rollback with preserved proof, approval, checksum, and provenance
- append-only event sequence:
  `PACKAGED → APPROVED → PROMOTED → ROLLED_BACK`

## Test coverage

- 191 repository tests passed.
- New regression coverage validates default preview proof resolution.
- New Command Center coverage validates deployment approval visibility.
- New API integration coverage validates approval and promotion actions.

## Boundary

This release provides local private-beta deployment packaging and governance.
It does not claim live cloud hosting or production cloud deployment infrastructure.
