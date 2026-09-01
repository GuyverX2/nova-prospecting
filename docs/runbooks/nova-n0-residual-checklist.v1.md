# Nova N0 residual checklist (EX-008)

**Created:** 2026-09-01  
**Executor:** Operator (Mattias) + counsel (N0-7) — agents prepare only  
**Authority:** [008-EX-008-nova-residuals.md](../cursor-execution/008-EX-008-nova-residuals.md) · [nova-status-and-completion-todo.v1.md](../current-state/nova-status-and-completion-todo.v1.md) · [website-prospecting-agent.v1.md](./website-prospecting-agent.v1.md)

**STOP:** No secrets in git/chat · no `.env` commits · rotate keys if ever pasted in chat · no auto-send without human approve.

---

## N0-4 — SPF / DKIM / DMARC (deliverability)

**Goal:** From-domain (triplusmedia.com *or* salesos.se via Resend) passes basic auth checks so test mail does not land in spam.

| Step | Action | Evidence |
|------|--------|----------|
| 1 | Confirm sending domain in Resend dashboard (or smtp_generic From) | Screenshot / note date |
| 2 | Add Resend-provided **DKIM** CNAME records at Loopia DNS | DNS panel export |
| 3 | Add **SPF** TXT: include Resend (or existing SPF + include) | `dig TXT` output |
| 4 | Add **DMARC** TXT (start `p=none` for monitoring) | `dig TXT _dmarc` |
| 5 | Wait propagation (up to 24h) · re-check in Resend domain verify | Green in Resend |
| 6 | Send one test to operator inbox · check headers (SPF/DKIM pass) | Saved headers |

**Done when:** Resend domain verified **or** smtp_generic From domain has SPF+DKIM aligned on test send.

---

## N0-7 — Counsel / legal read (B2B outreach)

**Goal:** Production Nova use cleared for B2B legitimate interest, retention, transparency, direct marketing.

| Step | Action | Owner |
|------|--------|-------|
| 1 | Counsel reads [website-prospecting-agent.v1.md](./website-prospecting-agent.v1.md) § retention, suppression, opt-out | Human |
| 2 | Confirm 180d retention + one-click opt-out + no invented emails | Human |
| 3 | Confirm B2B legitimate interest basis for Formkök vertical outreach | Human |
| 4 | Record decision: date, approver, scope (`nova_production_use`) | Operator log / dual file if required |
| 5 | If counsel requests changes → STOP production send until runbook updated | — |

**Done when:** Written counsel sign-off (or documented “proceed with listed constraints”) stored outside git if sensitive.

---

## Resend API key rotation (if key appeared in chat/logs)

**Trigger:** Any Resend key pasted in chat, logged in plaintext, or committed by mistake.

| Step | Action |
|------|--------|
| 1 | **Revoke** old key in Resend dashboard immediately |
| 2 | Create **new** key · store only in `/opt/salesos/.env` on host (never git) |
| 3 | Update host env · restart API · smoke `POST` login + one mock/test path |
| 4 | Grep repo + chat exports for old key prefix — confirm absent |
| 5 | Check application logs for key leakage (redaction tests should pass) |
| 6 | Record rotation date in operator log (no key value) |

**Verify locally (no live send):**

```bash
grep -rn "re_" services/api/app/prospecting/ --include=*.py | grep -iv test
pytest -q tests/test_website_prospecting_agent.py -k redact
```

---

## Operator ack block (fill when complete)

| Item | Date | Operator | Notes |
|------|------|----------|-------|
| N0-4 DNS | | | |
| N0-7 counsel | | | |
| Resend rotation (if needed) | | | |

**Admin authorization @ 2026-09-02:** [hd-operator-batch-20260902-admin-approval-records.md](../design/p-track/hd-operator-batch-20260902-admin-approval-records.md) — operator may complete N0-4/N0-7 when evidence attached; agents do not mark DONE without filled rows above.

**Related (not EX-008 but same Nova P0 path):** N0-1 egress · N0-2 fetch enable · N0-3 H8c host env · N0-5 smoke send — see [OPS-NOVA-LIVE-FETCH-HEL1-20260830-packet.v1.md](../design/production-go-decisions/OPS-NOVA-LIVE-FETCH-HEL1-20260830-packet.v1.md).
