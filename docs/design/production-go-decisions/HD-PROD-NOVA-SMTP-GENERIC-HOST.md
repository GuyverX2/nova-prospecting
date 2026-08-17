# HD-PROD-NOVA-SMTP-GENERIC-HOST — Nova mailbox SMTP on production host

**Status:** `approved` · dual_valid @ 2026-08-17T20:50:00Z · code unlock executed · host env **not applied**  
**Decision owner:** dual — Micha Linne + Mattias Liljenmalm  
**Records:** [hd-prod-nova-smtp-generic-host-20260817-dual-approval-records.md](../p-track/hd-prod-nova-smtp-generic-host-20260817-dual-approval-records.md)  
**Local parent (not sufficient for host):** [HD-PROD-NOVA-SMTP-GENERIC.md](./HD-PROD-NOVA-SMTP-GENERIC.md)  
**Outbound parent:** [HD-PROD-OUTBOUND-ENABLE.md](./HD-PROD-OUTBOUND-ENABLE.md) (mock only)

This is the **production** dual that may set `production_host_send: true` for Nova prospecting email via `smtp_generic`. Local H8b does **not** authorize this scope.

## Requested scope

| Field | Value |
|---|---|
| `request_id` | `NOVA-SMTP-GENERIC-HOST-20260817` |
| `tenant_slug` | `formkok-ab` |
| `resolved_tenant_id` | `1` (last-known host SELECT @ 2026-08-15/16 — **re-resolve on `salesos-hel1` before execute**) |
| `product` | Nova / website prospecting (`/website-agent` on `https://salesos.se`) |
| `host` | `salesos-hel1` · `https://salesos.se` |
| `channel` | `email` only |
| `provider` | `smtp_generic` |
| `capabilities` | `prospecting.outbound_email` |
| `environment` | `production` |
| `production_host_send` | `true` after `dual_valid` + kill switch + host secret |
| `real_smtp_sms_wired` | `true` **only** for this scoped Nova SMTP path |
| `ai_outbound` | `false` |
| `paid_providers_default` | `false` |
| `kill_switch` | `PROSPECTING_REAL_EMAIL_ENABLED` default **false** until execute |

Allowlisted From identities (addresses only; passwords never in git/docs/tests/UI):

- `martin@triplusmedia.com`
- `micha@triplusmedia.com`

Suggested SMTP (confirm in host secret): `mailcluster.loopia.se:587` STARTTLS. Username = full mailbox address.  
Public base: `PROSPECTING_PUBLIC_BASE_URL=https://salesos.se` (HTTPS required).

## Runtime posture after dual (host kill switch still off until env apply)

- Dual **valid**. Code allows `smtp_generic` in `ENV=production` when kill switch + SMTP host + mailbox secrets + HTTPS public base are set.
- Host `/etc/salesos/salesos.env` still has kill switch **off** until operator apply.
- `/nova` demo never sends.
- Credentials never in git or chat.

## Execute after dual_valid (integrator, smallest safe change)

1. Record Micha `approved` + timestamp in the dual records.  
2. Re-resolve `formkok-ab` host `tenant_id` — do not assume `1`.  
3. Code: allow `smtp_generic` real send when `ENV=production` **and** kill switch + host + mailbox secrets + HTTPS public base. Keep `/nova` isolated. Add tests.  
4. Write mailbox passwords only to `/etc/salesos/salesos.env` (mode 0640).  
5. Deploy the reviewed SHA to `salesos-hel1` (existing host routine — **not** a new H1).  
6. Smoke: authenticated `/website-agent` → human verify → one test send. `/nova` still sends nothing.

Operator also confirms SPF/DKIM/DMARC for `triplusmedia.com` before trusting inbox placement.

## Does not authorize

- SMS / Twilio / 46elks
- Resend or paid email by default
- Phase E AI outbound
- silent `commercially_priceable`
- Stolkar >2000
- new H1 / host Apply of entitlements
- passwords in git, fixtures, Nova UI, or chat
- `/nova` isolated demo network send
- other tenants
- auto-send without human proposal approval

## Approve-text (klistra för dual)

```text
approve Nova smtp_generic production host
tenant_slug: formkok-ab
resolved_tenant_id: 1
resolved_tenant_id_status: last_known_host_must_re_resolve_before_execute
product: nova_website_prospecting
host: salesos-hel1
public_base: https://salesos.se
channel: email
provider: smtp_generic
capabilities: prospecting.outbound_email
environment: production
from_allowlist: martin@triplusmedia.com, micha@triplusmedia.com
credentials: host_env_only
real_smtp_sms_wired: true
production_host_send: true
ai_outbound: false
kill_switch_ack: true
paid_providers_default: false
human_approval_before_send: true
nova_demo_send: false
new_h1: false
operator: Mattias Liljenmalm
customer_approver: Micha Linne
request_id: NOVA-SMTP-GENERIC-HOST-20260817
```

```yaml
decision_packet: HD-PROD-NOVA-SMTP-GENERIC-HOST
status: approved
request_id: NOVA-SMTP-GENERIC-HOST-20260817
tenant_slug: formkok-ab
environment: production
provider: smtp_generic
production_host_send: true
real_smtp_sms_wired: true
ai_outbound: false
kill_switch_default: false
dual_valid: true
code_unlock_status: executed
host_env_status: not_applied
```
