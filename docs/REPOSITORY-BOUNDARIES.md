# Repository Boundaries

Nova owns `services/api/app/prospecting`, its local database schema, `apps/nova`, and its deployment artifacts. It must not import code from SalesOS or reference `/repos/salesos`.

SalesOS is an external CRM service. Nova calls its versioned HTTP endpoint and passes the caller's verified platform bearer token. SalesOS source, ORM models, migrations, and login flows are out of scope.

`scripts/audit-coupling.py` enforces the source-level boundary in CI.
