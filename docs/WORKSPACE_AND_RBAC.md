# Workspace Registry and RBAC

`WorkspaceRegistry` persists private-beta identity and project ownership in SQLite.

## Roles

| Role | Intended authority |
|---|---|
| OWNER | Team ownership and all administrative actions |
| ADMIN | Membership, project, and deployment administration |
| DEVELOPER | Register projects and submit build/verification jobs |
| REVIEWER | Review proof, transactions, and approvals |
| VIEWER | Read-only project truth |

Role checks use an explicit rank model. A job cannot be submitted without developer authority, and status-changing project operations require administrative authority.

## Persistent entities

- users
- teams
- memberships
- projects
- invitations
- append-only activity events

Email and project/team slugs are normalized. Duplicate users are idempotent by email; duplicate project slugs inside a team are rejected.
