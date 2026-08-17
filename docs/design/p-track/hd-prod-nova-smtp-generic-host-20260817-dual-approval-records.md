# NOVA-SMTP-GENERIC-HOST-20260817 — dual-approval records

**Recorded:** 2026-08-17T20:46:00Z  
**Dual accepted:** 2026-08-17T20:50:00Z  
**Source:** operator pasted exact TRACK-H H8c approve-text with `customer_approver: Micha Linne`  
**Approvers:** Micha Linne (customer, **approved**) · Mattias Liljenmalm (operator, **approved**)  
**Packet:** [HD-PROD-NOVA-SMTP-GENERIC-HOST.md](../production-go-decisions/HD-PROD-NOVA-SMTP-GENERIC-HOST.md)  
**Does not reuse:** [NOVA-SMTP-GENERIC-20260817](./hd-prod-nova-smtp-generic-20260817-dual-approval-records.md) (local only)

```yaml
approval_bundle_id: "NOVA-SMTP-GENERIC-HOST-DUAL-20260817"
request_id: "NOVA-SMTP-GENERIC-HOST-20260817"
decision_packet: "HD-PROD-NOVA-SMTP-GENERIC-HOST"
environment: "production"
tenant_slug: "formkok-ab"
entity_slug: null
resolved_tenant_id: 1
resolved_tenant_id_status: "last_known_host_must_re_resolve_before_execute"
product: "nova_website_prospecting"
host: "salesos-hel1"
public_base: "https://salesos.se"
channel: "email"
provider: "smtp_generic"
capabilities: ["prospecting.outbound_email"]
from_allowlist:
  - "martin@triplusmedia.com"
  - "micha@triplusmedia.com"
credentials_in_git: false
credentials_in_this_record: false
real_smtp_sms_wired: true
production_host_send: true
ai_outbound: false
paid_providers_default: false
kill_switch_ack: true
kill_switch_env: "PROSPECTING_REAL_EMAIL_ENABLED"
kill_switch_default: false
nova_demo_send: false
new_h1: false
human_approval_before_send: true
customer_approval_present: true
admin_approval_present: true
dual_valid: true
execution_status: "code_unlock_executed_host_env_pending"
code_unlock_status: "executed"
host_env_status: "not_applied"

approve_text: |
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

customer_approval:
  approval_id: "NOVA-SMTP-GENERIC-HOST-CA-MICHA-20260817"
  approval_type: "customer_approval"
  approver_name: "Micha Linne"
  approver_role: "Försäljningschef"
  approver_company: "Formkök Sverige AB"
  approval_scope: "formkok-ab production host Nova smtp_generic email from allowlisted Triplus mailboxes on salesos.se; kill switch; no /nova send; no new H1"
  approval_source: "operator_pasted_exact_track_h_h8c_text"
  approval_timestamp: "2026-08-17T20:50:00Z"
  decision: "approved"
  notes: >
    Customer gate recorded from exact H8c paste naming customer_approver Micha Linne.
    Does not authorize SMS, AI outbound, paid-by-default, passwords in git,
    or silent commercially_priceable. Host kill switch remains operator env apply.
  tenant_slug: "formkok-ab"
  entity_slug: null
  request_id: "NOVA-SMTP-GENERIC-HOST-CA-20260817"
  audit_event_key: "customer_approval.recorded"

admin_approval:
  approval_id: "NOVA-SMTP-GENERIC-HOST-OA-MATTIAS-20260817"
  approval_type: "admin_approval"
  approver_name: "Mattias Liljenmalm"
  approver_role: "SalesOS Admin / Operator Approver"
  approver_company: null
  approval_scope: "formkok-ab production host Nova smtp_generic email; code unlock after dual; host kill switch still env-gated"
  approval_source: "operator_pasted_exact_track_h_h8c_text"
  approval_timestamp: "2026-08-17T20:50:00Z"
  decision: "approved"
  notes: >
    Exact H8c paste. Code may allow smtp_generic in ENV=production when kill switch
    and host secrets are set. Host /etc/salesos/salesos.env apply and deploy are
    separate operator steps; passwords never in git.
  tenant_slug: "formkok-ab"
  entity_slug: null
  request_id: "NOVA-SMTP-GENERIC-HOST-OA-20260817"
  audit_event_key: "admin_approval.recorded"

dual_gate:
  customer_alone_sufficient: false
  admin_alone_sufficient: false
  both_required: true
  composite: "accepted"

explicitly_not_authorized:
  - SMS / Twilio / 46elks
  - paid email provider by default
  - Phase E AI outbound
  - /nova demo network send
  - credentials in git, tests, fixtures, or UI
  - silent commercially_priceable
  - Stolkar >2000
  - new H1 / entitlement Apply
  - other tenants
  - auto-send without human proposal approval
```

Host re-resolve @ 2026-08-17T20:50Z: SSH `salesos-hel1` OK, `salesos-api` active, `/opt/salesos` present. Unprivileged `salesos` OS user missing on this probe, so `formkok-ab` numeric id was **not** re-queried. Last-known remains `1` until operator re-resolves before first live send.

## After dual (remaining operator apply)

1. Dual is recorded `accepted` @ 2026-08-17T20:50:00Z.  
2. Re-resolve host `formkok-ab` tenant id on `salesos-hel1` before first live send.  
3. Code unlock: `smtp_generic` real send is allowed in `ENV=production` when kill switch + secrets + HTTPS public base are set. `/nova` stays isolated.  
4. Host secret only (`/etc/salesos/salesos.env`, never git) — **not applied in the paste session**:

```text
PROSPECTING_EMAIL_PROVIDER=smtp_generic
PROSPECTING_REAL_EMAIL_ENABLED=true
PROSPECTING_PUBLIC_BASE_URL=https://salesos.se
PROSPECTING_SMTP_HOST=mailcluster.loopia.se
PROSPECTING_SMTP_PORT=587
PROSPECTING_SMTP_STARTTLS=true
PROSPECTING_SMTP_MAILBOX_1_ADDRESS=martin@triplusmedia.com
PROSPECTING_SMTP_MAILBOX_1_PASSWORD=<not in git>
PROSPECTING_SMTP_MAILBOX_2_ADDRESS=micha@triplusmedia.com
PROSPECTING_SMTP_MAILBOX_2_PASSWORD=<not in git>
```

5. Deploy reviewed SHA. Restart API. Smoke via authenticated `/website-agent` only.
