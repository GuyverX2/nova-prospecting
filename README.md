# Nova — evidence-first website prospecting

Nova finds a company's public website, audits it against saved evidence, turns
the findings into a versioned proposal, and lets a human approve it before
anything is shared or sent. It is a standalone service: it owns its database,
has no login of its own, and talks to the SalesOS platform through exactly one
HTTP boundary.

```
console (React)  →  /api/v1  →  routes  →  service  →  Nova database
                                   │
                                   └─→  SalesOS CRM promote  (only outbound platform call)
```

## What it does

| Stage | Guarantee |
| --- | --- |
| Intake | Manual, CSV paste (≤50 rows) or Google Places. Contact emails are never imported as verified. |
| Analysis | A pasted HTML snapshot, or a fetch of an operator-confirmed public URL behind a kill switch. Private/reserved/metadata addresses, non-web ports and credentialed URLs are refused; robots.txt is honoured. Every finding carries evidence. |
| Proposal | Generated from one completed analysis, versioned per prospect. |
| Approval | Four explicit human checks (analysis, contact, content, legal basis). Approved proposals are immutable — a change means a new version. |
| Share | An opaque token; only its SHA-256 hash is stored. Public pages are `no-store`, `noindex`, and served under a strict CSP. |
| Delivery | Approval-gated, suppression-aware, once per proposal, inside a per-tenant daily limit, with an HMAC-signed one-click opt-out. Real sending stays off until an operator turns the kill switch on. |

## Requirements

- Python 3.11+
- Node 20+ (console)
- A database: SQLite locally, PostgreSQL for anything with concurrent workers

## Run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env          # defaults are safe: no fetching, no real email

make migrate                  # alembic upgrade head
make api                      # http://localhost:8000
```

In a second terminal, for console development with hot reload:

```bash
npm --prefix apps/nova ci
npm --prefix apps/nova run dev    # proxies /api to http://127.0.0.1:8000
```

For a production-shaped run, build the console and let the API serve it from the
same origin (no CORS needed):

```bash
make frontend-build
make api            # the console is now at http://localhost:8000/
```

Nova has no login. The platform issues an HS256 JWT with `sub`, `tenant_id`,
`roles`, `scopes` and an `aud` matching `NOVA_JWT_AUDIENCE`; paste it into the
console, or send it as `Authorization: Bearer …`. To mint one for local work:

```bash
python -c "import sys; sys.path.insert(0,'services/api'); \
from app.auth import create_access_token; \
print(create_access_token({'sub':'you@example','tenant_id':'tenant-demo','roles':['operator'],'scopes':['nova:write']}))"
```

## Configuration

Every variable is listed with its default in [`.env.example`](.env.example); a
test fails if that file and the code drift apart. Configuration is validated at
startup and the process refuses to boot on an unsafe combination (a default JWT
secret in production, real email without a configured provider, an unknown
provider name, `*` CORS in production). Non-fatal advisories — SQLite in
production, auto-created schema, a missing CRM URL — are logged at startup and
returned by `GET /health/ready`.

The two switches that matter:

- `PROSPECTING_FETCH_ENABLED` — may Nova fetch a public website at all.
- `PROSPECTING_REAL_EMAIL_ENABLED` — may email leave the building. With it
  off, `queue` and `mock` only record state.

## Database and migrations

Nova owns seven tables and nothing else: six prospecting tables plus
`audit_events`. It holds tenant ids as opaque strings and has no foreign key
into any platform table.

```bash
make migrate                       # apply everything (clean database or upgrade)
make migrate-down                  # roll back one revision
make revision m="add x"            # autogenerate from the models
```

Migrations are explicit DDL and are the only supported way to create the schema
in production (`NOVA_DB_AUTO_CREATE` defaults to false there). The container
runs `alembic upgrade head` on start.

## Operating it

| Endpoint | Purpose |
| --- | --- |
| `GET /health/live` | Process is up. Never touches the database. |
| `GET /health/ready` | Configuration valid + database reachable, plus advisories. |
| `GET /metrics` | Prometheus counters (method, route, status class only). |
| `GET /docs` | OpenAPI for the whole API. |

Every request carries an `X-Request-ID` (generated when absent) that is echoed
in the response, written to each structured log line, and stored on the audit
event for every mutation. Logs are one JSON object per line; secrets, tokens and
recipient addresses are never logged.

## Testing

```bash
make test          # pytest
make lint          # ruff
make typecheck     # mypy
make frontend-test # console guardrails
make verify        # everything CI runs
```

The suite covers the end-to-end flow, tenant isolation (foreign ids replayed on
every route), the JWT contract, delivery guardrails, configuration validation,
outbound HTTP resilience, the analyzer's SSRF defences and the migration chain
from a clean database.

## Container

```bash
make docker-build
docker run --rm -p 8000:8000 -v nova-data:/data \
  -e NOVA_JWT_SECRET=... -e PROSPECTING_PUBLIC_BASE_URL=https://nova.example \
  nova-prospecting:local
```

The image builds the console, runs as an unprivileged user, keeps its database
on the `/data` volume, applies migrations at start and declares a healthcheck
against `/health/ready`.

## Repository layout

```
services/api/app/        FastAPI service
  core/                  config, logging, errors, middleware, rate limiting
  prospecting/           models, schemas, routes, service, analyzer, outbound
  integrations/          shared bounded HTTP client
  crm/                   the single SalesOS boundary
  tenancy/               tenant context and audit trail
services/api/alembic/    migrations
apps/nova/               operator console (React + Vite)
scripts/                 coupling audit, Gate C data tooling, deploy helpers
docs/                    architecture, boundaries, runbooks
tests/                   pytest suite
```

## Boundaries

`scripts/audit-coupling.py` (run by `make audit` and CI) fails the build if Nova
imports SalesOS code. The only allowed platform call is
`POST {SALESOS_CRM_BASE_URL}/api/v1/nova/prospects/promote`, and a CRM failure
must leave Nova's own state untouched — there is a test for that.
