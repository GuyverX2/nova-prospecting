# NOVA-SMTP-GENERIC-20260817 — dual-approval records

**Recorded:** 2026-08-17T13:31:00Z  
**Source:** operator chat asked to create the approval packet and wire Nova mailbox SMTP  
**Approvers:** Micha Linne (customer, **pending**) · Mattias Liljenmalm (operator, requested/accepted packet)  
**Packet:** [HD-PROD-NOVA-SMTP-GENERIC.md](../production-go-decisions/HD-PROD-NOVA-SMTP-GENERIC.md)

Dual is **not valid** until Micha's customer record is `approved` with the same scope. Adapter ships fail-closed. Kill switch stays off. Passwords are not stored in this file.

```yaml
approval_bundle_id: "NOVA-SMTP-GENERIC-DUAL-20260817"
request_id: "NOVA-SMTP-GENERIC-20260817"
decision_packet: "HD-PROD-NOVA-SMTP-GENERIC"
environment: "local_development"
tenant_slug: "formkok-ab"
entity_slug: null
product: "nova_website_prospecting"
channel: "email"
provider: "smtp_generic"
capabilities: ["prospecting.outbound_email"]
from_allowlist:
  - "martin@triplusmedia.com"
  - "micha@triplusmedia.com"
credentials_in_git: false
credentials_in_this_record: false
real_smtp_sms_wired: true
ai_outbound: false
paid_providers_default: false
kill_switch_ack: true
kill_switch_env: "PROSPECTING_REAL_EMAIL_ENABLED"
kill_switch_default: false
production_host_send: false
human_approval_before_send: true
customer_approval_present: false
admin_approval_present: true
dual_valid: false
execution_status: "adapter_shipped_kill_switch_off"

approve_text: |
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

customer_approval:
  approval_id: "NOVA-SMTP-GENERIC-CA-MICHA-20260817"
  approval_type: "customer_approval"
  approver_name: "Micha Linne"
  approver_role: "Försäljningschef"
  approver_company: "Formkök Sverige AB"
  approval_scope: "formkok-ab local_development Nova smtp_generic email from allowlisted Triplus mailboxes; kill switch; no production host send"
  approval_source: "pending_chat_paste"
  approval_timestamp: null
  decision: "pending"
  notes: >
    Customer gate not yet recorded. Paste the packet approve-text to complete dual.
    Does not authorize production host SMTP, SMS, AI outbound, paid-by-default,
    or passwords in git.
  tenant_slug: "formkok-ab"
  entity_slug: null
  request_id: "NOVA-SMTP-GENERIC-CA-20260817"
  audit_event_key: "customer_approval.recorded"

admin_approval:
  approval_id: "NOVA-SMTP-GENERIC-OA-MATTIAS-20260817"
  approval_type: "admin_approval"
  approver_name: "Mattias Liljenmalm"
  approver_role: "SalesOS Admin / Operator Approver"
  approver_company: null
  approval_scope: "formkok-ab local_development Nova smtp_generic adapter + dual packet; kill switch off until customer approval"
  approval_source: "operator_chat_create_packet_and_wire_adapter"
  approval_timestamp: "2026-08-17T13:31:00Z"
  decision: "approved"
  notes: >
    Operator requested the packet and the fail-closed adapter. Dual remains
    invalid until Micha approves. Secrets stay in gitignored env only.
  tenant_slug: "formkok-ab"
  entity_slug: null
  request_id: "NOVA-SMTP-GENERIC-OA-20260817"
  audit_event_key: "admin_approval.recorded"

dual_gate:
  customer_alone_sufficient: false
  admin_alone_sufficient: false
  both_required: true
  composite: "pending"

explicitly_not_authorized:
  - production / staging host SMTP
  - SMS / Twilio / 46elks
  - paid email provider by default
  - Phase E AI outbound
  - /nova demo network send
  - credentials in git, tests, fixtures, or UI
  - silent commercially_priceable
  - Stolkar >2000
  - new H1 / host Apply
```

## After Micha approves

1. Set `customer_approval.decision: approved` and timestamp in this file.  
2. Operator fills gitignored `services/api/.env` (never commit):

```text
PROSPECTING_EMAIL_PROVIDER=smtp_generic
PROSPECTING_REAL_EMAIL_ENABLED=true
PROSPECTING_PUBLIC_BASE_URL=https://<local-https-or-approved-host>
PROSPECTING_SMTP_HOST=mailcluster.loopia.se
PROSPECTING_SMTP_PORT=587
PROSPECTING_SMTP_STARTTLS=true
PROSPECTING_SMTP_MAILBOX_1_ADDRESS=martin@triplusmedia.com
PROSPECTING_SMTP_MAILBOX_1_PASSWORD=<not in git>
PROSPECTING_SMTP_MAILBOX_2_ADDRESS=micha@triplusmedia.com
PROSPECTING_SMTP_MAILBOX_2_PASSWORD=<not in git>
```

3. Restart API. `/website-agent` (authenticated) may send only after human verify. `/nova` stays isolated.  
4. Production host send still needs a **new** dual.
