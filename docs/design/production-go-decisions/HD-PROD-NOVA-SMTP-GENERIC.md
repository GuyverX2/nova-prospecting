# HD-PROD-NOVA-SMTP-GENERIC — Nova mailbox SMTP (scoped)

**Status:** `pending_customer_approval` @ 2026-08-17  
**Decision owner:** dual — Micha Linne + Mattias Liljenmalm  
**Records:** [hd-prod-nova-smtp-generic-20260817-dual-approval-records.md](../p-track/hd-prod-nova-smtp-generic-20260817-dual-approval-records.md)  
**Parent:** [HD-PROD-OUTBOUND-ENABLE.md](./HD-PROD-OUTBOUND-ENABLE.md) (mock only; `real_smtp_sms_wired: false`)  
**This packet is the second dual** that names `smtp_generic` and may set `real_smtp_sms_wired: true` **only** inside the scope below.

## Requested scope

| Field | Value |
|---|---|
| `request_id` | `NOVA-SMTP-GENERIC-20260817` |
| `tenant_slug` | `formkok-ab` |
| `product` | Nova / website prospecting (`/website-agent`) |
| `channel` | `email` only |
| `provider` | `smtp_generic` |
| `capabilities` | `prospecting.outbound_email` |
| `environment` | `local_development` |
| `real_smtp_sms_wired` | `true` **after dual_valid** and env kill switch |
| `ai_outbound` | `false` |
| `paid_providers_default` | `false` |
| `kill_switch` | `PROSPECTING_REAL_EMAIL_ENABLED` default **false** |

Allowlisted From identities (addresses only; passwords never in git/docs/tests/UI):

- `martin@triplusmedia.com`
- `micha@triplusmedia.com`

Suggested SMTP (Loopia cluster; operator confirms in secret store): `mailcluster.loopia.se:587` STARTTLS. Username = full mailbox address.

## Runtime posture until dual is valid

Adapter may exist in code. Defaults stay:

- `PROSPECTING_EMAIL_PROVIDER=disabled`
- `PROSPECTING_REAL_EMAIL_ENABLED=false`
- no SMTP network from tests or `/nova` demo
- credentials only in gitignored `.env` / host secret

Human proposal approval, suppression, daily limit, and audit remain required on every send.

## Does not authorize

- production / staging host send — use [HD-PROD-NOVA-SMTP-GENERIC-HOST.md](./HD-PROD-NOVA-SMTP-GENERIC-HOST.md) (H8c)
- SMS / Twilio / 46elks
- Resend or other paid email by default
- Phase E AI outbound / Tool Gateway send
- silent `commercially_priceable`
- Stolkar >2000
- new H1 / host Apply
- passwords in git, fixtures, Nova UI, or chat
- `/nova` isolated demo network send

## Approve-text (klistra för dual)

```text
approve Nova smtp_generic local
tenant_slug: formkok-ab
product: nova_website_prospecting
channel: email
provider: smtp_generic
capabilities: prospecting.outbound_email
environment: local_development
from_allowlist: martin@triplusmedia.com, micha@triplusmedia.com
credentials: gitignored_env_only
real_smtp_sms_wired: true
ai_outbound: false
kill_switch_ack: true
paid_providers_default: false
human_approval_before_send: true
production_host_send: false
operator: Mattias Liljenmalm
customer_approver: Micha Linne
request_id: NOVA-SMTP-GENERIC-20260817
```

```yaml
decision_packet: HD-PROD-NOVA-SMTP-GENERIC
status: pending_customer_approval
request_id: NOVA-SMTP-GENERIC-20260817
tenant_slug: formkok-ab
environment: local_development
provider: smtp_generic
real_smtp_sms_wired: true
ai_outbound: false
kill_switch_default: false
dual_valid: false
```
