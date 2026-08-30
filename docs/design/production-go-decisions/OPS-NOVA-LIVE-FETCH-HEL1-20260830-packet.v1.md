# OPS-NOVA-LIVE-FETCH-HEL1-20260830 — fetch-only live path

**Datum:** 2026-08-30  
**Mål:** Nova kan analysera en *egen* publik URL på `https://salesos.se/nova`.  
**Inte i scope:** SMTP/H8c kill switch, Places, PageSpeed-nyckel, CRM-handoff, host SSH från Arena.

**STOP:** inga secrets i git/chat · `PROSPECTING_REAL_EMAIL_ENABLED` förblir **false** · ingen G4 · ingen silent `commercially_priceable`.

---

## Varför staged (fetch före mail)

`make print-nova-host-env` klistrar fetch **och** real email. Det är H8c-paketet. Live-analys kräver bara fetch. Kör N0-2 här först; H8c host-apply är nästa packet efter smoke.

## Förutsättning (N0-1, operator)

Host får göra DNS + HTTPS mot publika sajter. API:t blockerar redan loopback/RFC1918/metadata. Bekräfta egress **innan** flaggan sätts.

## Cursor / operator på hel1

1. `make print-nova-fetch-env` — stdout, inga secrets.
2. Pastas **endast** dessa nycklar in i `/opt/salesos/.env` (verifierad sökväg, inte `/etc/salesos/salesos.env`):
   - `PROSPECTING_FETCH_ENABLED=true`
   - `PROSPECTING_DISCOVERY_PROVIDER=disabled` (redan default)
   - `PROSPECTING_PUBLIC_BASE_URL=https://salesos.se`
3. Rör **inte** `PROSPECTING_REAL_EMAIL_ENABLED`, mailbox-lösenord, Resend-nyckel.
4. `systemctl restart salesos-api`
5. `curl -sf https://salesos.se/health/ready`
6. Inloggad `GET /api/v1/prospecting/summary` → `providers.website_fetch.enabled=true`
7. `/nova` → **Analysera URL** mot *egen* publik sida (t.ex. salesos.se eller formkok.salesos.se). Evidenspaket ska visas. Refresh ska **behålla** analysen (list_prospects inkluderar latest).
8. Rollback: `PROSPECTING_FETCH_ENABLED=false` + restart.

## Kod som måste vara ute innan smoke

Workspace-refresh visade tidigare tom analys (`include_latest=False` på listan). Fixad i `list_prospects`. UI stänger av **Ny sökning** när Places är av och **Analysera igen** när fetch är av.

## Inte gjort av Arena

- SSH / skriv host `.env`
- Dual-paste för H8c (redan `dual_valid`; env `not_applied`)
- Ett skarpt testmail (N0-5) — efter H8c apply

## Nästa efter PASS

N0-6 PageSpeed-nyckel (valfritt).  
N0-3 H8c: `make print-nova-host-env` + `make configure-nova-smtp ENV_FILE=/opt/salesos/.env` — kill switch **false** tills login-smoke, sedan ett test till operatörsadress.
