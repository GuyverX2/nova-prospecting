# Gate C rehearsal evidence — 2026-09-24

**Task:** `NOVA-GATE-C-REHEARSAL-001`
**Scope approved by the operator (chat, 2026-09-24):** Full controlled rehearsal:
source pins + read-only manifests against production SalesOS, an empty Nova
rehearsal database, controlled import with in-memory identifier conversion and
reconciled target evidence — **without** switching write authority, touching
traffic, or retiring any SalesOS runtime path.

## Pinned revisions

| Component | Revision |
| --- | --- |
| SalesOS source checkout (`/home/deploy/salesos`) | `7119f7e823524f790ff1b5a331bc7e33df62dd92` |
| Nova executed tooling (`/repos/nova-prospecting` @ origin/main via merge `30c39d287d1793ba8d167c24765f985a5a958839`) | `30c39d287d1793ba8d167c24765f985a5a958839` |
| Manifest-path coercion hotfix (`3a4144d552111e7b22a506915d1064bc4133ec34`) | `3a4144d552111e7b22a506915d1064bc4133ec34` |
| Executed target schema (fresh, empty, Nova-owned) | `nc20260923a` |
| Rehearsal DB | `nova_gatec_rehearsal` ( PostgreSQL 18.6, 127.0.0.1 on `salesos-hel1`) |

## Read-only credentials

* `gate_c_ro` (SELECT-only on the six source tables in `salesos_prod`),
  grant for host `salesos-hel1` uses TLS-less local loopback inside the host.
* `nova_gatec_ro` (SELECT-only on the six imported Nova rehearsal tables).
* Write credentials for the rehearsal import were supplied **outside Git** via
  `~/.agent-infra/gate-c-rehearsal/*.env` (mode 600); no credential value is
  printed here or in the repo.

## Rehearsal-only mapping

Generated from the live production source (read-only via `gate_c_ro`) by
`gate-c-rehearsal/generate-mapping.py`:

* legacy tenant identifiers found: **1**
* legacy user/subject identifiers found: **2**

Mapping values are rehearsal placeholders of the shape
`rehearsal-tenant-<n>` / `rehearsal-subject-<n>`. The production Gate C mapping
is still a separately-gated operator decision; no production user or tenant was
ever renamed by this rehearsal.

## Reconciled evidence

`scripts/gate_c.reconcile` output (counts differ per row identity only):

```json
{"result": "ok", "tables": {"prospect_suppressions": 0, "prospecting_campaigns": 0,
 "prospecting_policies": 1, "website_analyses": 18, "website_proposals": 1,
 "website_prospects": 2}}
```

* Source manifest (mapped, read-only credential): `salesos-source-manifest-mapped.json`.
* Target manifest (post-import): `nova-target-manifest.json`.
* Both manifests compared equal through `scripts.gate_c.reconcile` — every
  count, stable-ID digest and tenant-ownership digest matched.

Reconciliation is deterministic, metadata-only and contained **no** row data
in the repo; the evidence above lives only on `salesos-hel1` under
`~/.agent-infra/gate-c-rehearsal/`.

## Production mapping progress (2026-09-24)

`prod-mapping.json` currently contains the read-only Keycloak↔SalesOS correlations:

* legacy tenant identifiers: **2** (each mapped to the SalesOS tenant slug as opaque id).
* numeric user ids matched to Keycloak UUID subjects: **1**
* explicitly-unmapped legacy users: **3**

Per `ADR-0008` these 3 are **hard failures** — they are marked explicitly
unmapped in the template and must be supplied by an operator before any Gate C
write-authority switch. No subject was invented, and the current prod mapping
therefore remains fail-closed partial, not production-authoritative.

The remaining operators-gated steps are unchanged:

1. Final operator-approved numeric-user-ID → Nova-subject mapping.
2. Gate C **production** execution: switching write authority from SalesOS to
   Nova (irreversible, dual approval required).
3. Gate D: production routing/cutover (`nova.salesos.se`).
4. Gate E: SalesOS prospecting runtime retirement.

## Verification command performed live

```sh
python3 -m scripts.gate_c.export_import \
  --source-url "$NOVA_READ_ONLY_DATABASE_URL" \
  --target-url "$NOVA_DATABASE_URL" \
  --mapping rehearsal-mapping.json \
  --output-manifest nova-target-manifest.json
# Script returned {"result": "ok", ...}; all six tables reconciled equal.
```
