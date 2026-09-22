# Nova Architecture

## Authentication

Nova has no login endpoint. The platform supplies a signed bearer JWT containing required `sub`, `tenant_id`, `roles`, and `scopes` claims. `PlatformPrincipal` retains the raw token for downstream CRM authorization. Tenant isolation is claim-derived and fail-closed.

## CRM

The CRM boundary is `SalesOSCrmClient`, using `POST /api/v1/nova/prospects/promote`. Nova passes the caller bearer token and a stable `nova-prospect:<tenant>:<prospect>` idempotency key. A rejected or unavailable CRM leaves local prospect state unchanged.

## Database

Nova owns the six prospecting tables on the shared platform Postgres service,
configured by `NOVA_DATABASE_URL`, during the transition. Rows use opaque
string tenant IDs and subject ownership fields; there are no local platform
user or tenant tables and no foreign keys to either. Physical database split
and a Nova migration chain are explicitly deferred to Gate C.

## Observability

Prospecting mutations create tenant-scoped audit events with the platform subject, target, request ID, and a compact post-change payload. Operators should provide `X-Request-ID` and collect application stdout/stderr with their platform logging agent. Secrets and bearer tokens must never be logged.
