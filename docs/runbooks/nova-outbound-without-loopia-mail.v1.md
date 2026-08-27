# Nova outbound utan Loopia-mailinloggning (Resend)

**Status:** operator runbook · **ingen host-enable** utan H8c/G4 ack  
**När:** du saknar Loopia e-postkonto för `salesos.se` men vill köra relay  
**Kod:** `PROSPECTING_EMAIL_PROVIDER=resend` redan stödd i Nova (`prospecting/outbound.py`)

## Poäng

Relay ≠ Loopia-mail. Domänen stannar hos Loopia DNS. Utskick går via Resend (API-nyckel).  
H8c dual (`smtp_generic` + Triplus-mailboxar) är fortfarande giltig om ni har de lösenorden — Resend är alternativ när ni *inte* har dem.

## Steg (Resend)

1. Skapa konto hos Resend och lägg till domänen `salesos.se`.
2. I **Loopia DNS** (inte mail-panelen): lägg SPF/DKIM-TXT som Resend visar.
3. Verifiera domänen i Resend → skapa API-nyckel.
4. På host (efter operator-ack), i `/opt/salesos/.env` — **inga secrets i chat/git**:

```bash
PROSPECTING_EMAIL_PROVIDER=resend
PROSPECTING_REAL_EMAIL_ENABLED=false   # håll false tills smoke + ack
PROSPECTING_PUBLIC_BASE_URL=https://salesos.se
PROSPECTING_EMAIL_API_KEY=<host secret>
PROSPECTING_EMAIL_FROM=nova@salesos.se   # måste vara verifierad From i Resend
```

5. `systemctl restart salesos-api` → `/health/ready` OK.
6. Sätt `PROSPECTING_REAL_EMAIL_ENABLED=true` först när ni vill skicka skarpt (H8c host-apply evidence).
7. Smoke: `/nova` → en testleverans till operatörsadress.

## Alternativ: Triplus `smtp_generic` (H8c som skrivet)

Om ni *har* lösen till `martin@` / `micha@triplusmedia.com`:

```bash
make print-nova-host-env
make configure-nova-smtp ENV_FILE=/opt/salesos/.env
make smoke-nova-smtp ENV_FILE=/opt/salesos/.env
```

## CRM outbound (G4)

CRM-kanaler (`tenant_invite`, `lead_confirm`, …) använder **`SALESOS_OUTBOUND_EMAIL_*`** (`smtp_generic` i nuvarande dual).  
Kill switch default **off**. Resend för CRM är **inte** inkopplat ännu — behåll G4-paketet tills provider utökas med ny dual.

## STOP

- Ingen live-send utan H8c/G4 host-ack  
- Inga secrets i git/chat  
- Domän flyttas **inte** från Loopia  
- Egen Postfix på Hetzner behövs **inte**
