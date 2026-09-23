# Nova Gate C preparation

**Task:** `NOVA-GATE-C-PREP-001`
**Status:** complete — preparation only; Gate C execution remains separately gated
**Authority:** operator approval, 2026-09-23: “Godkänn Gate C-förberedelse”
**Non-goals:** no production database access, no data export/import, no traffic
cutover, no write-authority switch, and no legacy SalesOS removal.

## Deliverables

1. A standalone Nova migration chain, beginning with the six Nova-owned
   prospecting tables.
2. A fail-closed reconciliation format that compares row counts, stable IDs and
   tenant ownership without embedding row data or credentials in Git.
3. A runbook and evidence template for the later, separately approved Gate C
   execution.

## Identity conversion boundary

SalesOS currently stores `tenant_id` and user references as platform numeric
foreign keys. Nova stores opaque `tenant_id` strings and subject fields such as
`created_by_subject`. The eventual importer must receive an operator-controlled
mapping for each required legacy user reference. Missing or duplicate mappings
are a hard failure; it must never invent a user, use a default tenant, or retain
a cross-repository foreign key.

Validate the local, uncommitted mapping file before an import rehearsal:

```json
{
  "tenant_ids": {"7": "opaque-nova-tenant-id"},
  "user_subjects": {"12": "platform-subject-id"}
}
```

```sh
python -m scripts.gate_c.validate_mapping local-identifier-map.json
```

The validator emits only mapping counts, never the identifiers. The conversion
helper applies that map in memory and rejects an absent tenant/user mapping.

## Prepared schema

Run the migration against an empty, Nova-owned database only:

```sh
NOVA_DATABASE_URL=postgresql+psycopg://... python -m alembic -c alembic.ini upgrade head
```

The migration creates exactly these six tables: `prospecting_campaigns`,
`website_prospects`, `website_analyses`, `website_proposals`,
`prospecting_policies`, and `prospect_suppressions`. It creates no `tenants` or
`users` table and no foreign key to SalesOS.

## Reconciliation protocol

The controlled export and import jobs must each write a metadata-only manifest:

```json
{
  "schema_version": 1,
  "tables": {
    "website_prospects": {
      "count": 0,
      "id_sha256": "…",
      "tenant_ownership_sha256": "…"
    }
  }
}
```

All six tables are required. `id_sha256` is a deterministic digest of sorted
stable IDs. `tenant_ownership_sha256` is a deterministic digest of sorted
`(stable ID, opaque tenant ID)` pairs. Verify before a shadow read:

```sh
python -m scripts.gate_c.reconcile source-manifest.json target-manifest.json
```

Any count, ID or tenant-ownership mismatch fails the run.

Create either manifest with a **read-only** database credential. The tool reads
only `id` and `tenant_id`, emits hashes/counts only, refuses to overwrite a
manifest, and refuses a missing SQLite source rather than creating it:

```sh
python -m scripts.gate_c.write_manifest \
  --database-url "$NOVA_READ_ONLY_DATABASE_URL" \
  --output target-manifest.json
```

The database URL is supplied only through the shell environment; neither the
command output nor the manifest contains it.

## Gate C execution prerequisites — not approved by this document

- explicit irreversible execution approval;
- pinned SalesOS source revision and a read-only export credential;
- Nova database URL and backup/rollback location supplied outside Git;
- reviewed numeric-user-ID → Nova-subject mapping;
- successful empty-database migration verification;
- export/import reconciliation evidence;
- read-only shadow period with no dual-write;
- a separately recorded decision naming Nova as the only write authority.

Gate D (production routing/cutover) and Gate E (legacy removal) remain separate
operator approvals after Gate C reconciliation and soak evidence.

## Local verification — 2026-09-23

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest` | 8 passed |
| `python scripts/audit-coupling.py` | passed |
| `npm --prefix apps/nova run test:static` | passed |
| `npm --prefix apps/nova run build` | passed |
| `git diff --check` | passed |

The migration test applies `nc20260923a` to an empty SQLite database, verifies
that the six Nova-owned tables exist without SalesOS `tenants` or `users`
tables, and rolls the revision back to base. It also verifies that missing
tenant/user mappings fail before conversion. No production or shared database
was contacted.
