# Nova — status, luckor och completion-todo

**Datum:** 2026-08-30  
**Syfte:** Ärlig status för Nova (webbprospektering) + vad som krävs för att *färdigställa* den som användbar produkt, med motsvarande verktyg och samtliga relevanta förbättringar/optimeringar.  
**Kodbas:** `main` @ `e5332c44` (session-branch `arena/01a05376-salesos`)  
**Authority:** [website-prospecting-agent.v1.md](../runbooks/website-prospecting-agent.v1.md) · [HD-PROD-NOVA-SMTP-GENERIC-HOST.md](../design/production-go-decisions/HD-PROD-NOVA-SMTP-GENERIC-HOST.md) · [OPERATOR-NEXT.md](../design/production-go-decisions/OPERATOR-NEXT.md) · [competitive-landscape-and-improvements-2026-08-28.v1.md](../analysis/competitive-landscape-and-improvements-2026-08-28.v1.md) · [further-improvements-2026-08-30.v1.md](../analysis/further-improvements-2026-08-30.v1.md) · [competitive-benchmark-2026-08-29.md](../strategy/competitive-benchmark-2026-08-29.md)

**STOP (oförändrat):** inget host `.env`-skriv · inga secrets i git/chat · ingen tyst `commercially_priceable` · ingen G4/H8c enable utan dual + ack · ingen directory-skrapning · inga påhittade e-postadresser.

---

## 0. Verdict på en rad

Nova är **byggt som styrd produkt** (login, tenant-API, evidensanalys, mötesfilm, mänskligt mandat, kö/mock-leverans) och **live som UI på `https://salesos.se/nova` sedan M14**. Den är **inte färdig som säljande verktyg**: discovery, webbhämtning, PageSpeed och riktig e-post är **av på host**. Mot Clay/Apollo/HubSpot saknas enrichment, sequences, CRM-handoff och bakgrundskö. Unik moat — evidens + autogen kundmötesfilm + fail-closed GDPR — är redan i koden.

| Lager | Status | Kommentar |
|-------|--------|-----------|
| Produktfilm `/nova-video` | ✅ Live | ~2:10 SV, förinspelad MP3, stänger in i `/nova` |
| Live-arbetsyta `/nova` | ✅ Live UI, gatead runtime | Login, tom yta tills URL analyseras; ingen demo-seed |
| Prospecting-API | ✅ Kod komplett | 20+ routes, tenant-scope, public share/opt-out |
| SSRF-säker HTML-analys | ✅ Kod, 🔴 host fetch AV | `PROSPECTING_FETCH_ENABLED=false` default + prod-exempel |
| Google Places discovery | ✅ Adapter, 🔴 AV | `PROSPECTING_DISCOVERY_PROVIDER=disabled` |
| PageSpeed/Lighthouse | ✅ Adapter, 🔴 nyckel saknas | Optional enrichment |
| Mötesfilm (9 kapitel) | ✅ Live i preview | Ingen MP4, ingen remote asset, intern kalkyl lämnar aldrig fliken |
| Human approve + suppression | ✅ Live i kod | Krävs före leverans; one-click opt-out |
| Riktig e-post (H8c) | 🟡 Dual **valid**, kod unlocked, **host env inte applicerad** | Kill switch `PROSPECTING_REAL_EMAIL_ENABLED=false` |
| CRM outbound (G4) | 🟡 Kod (hooks) på main, **inte enabled** | Separat från Nova; `SALESOS_OUTBOUND_EMAIL_ENABLED=false` |
| CRM-handoff (prospect → lead/case) | 🟢 N1-1 API + N1-2 CRM-kort @ 2026-08-30 | Case-kort + promote-knapp kvar |
| Sequences / follow-up | 🔴 Medvetet STOP | Marknaden har detta dag 1 |
| Bakgrundsworker | 🔴 `AGENT_SCHEDULER_ENABLED=false` | Policy kan sparas; inget körs |
| E2E / i18n | 🔴 | Statiska UI-lås + 12 pytest; ingen Playwright; SV hårdkodat |

**Definition of done för “Nova är färdig att använda av Formkök”** = P0 + P1 nedan.  
**Definition of done för “Nova slår Clay/Apollo i nischen”** = P0–P3.

---

## 1. Vad som faktiskt finns (verifierat i kod)

### 1.1 Ytor

| Yta | Route | App |
|-----|-------|-----|
| Live workspace | `/nova` (alias `/website-agent`, `/webbagent` → redirect) | `apps/internal-pilot-ui` `WebsiteProspectAgent.tsx` (~1 229 rader) |
| Produktfilm | `/nova-video` | `NovaPresentation.tsx` + 8 MP3 |
| API | `/api/v1/prospecting/*` | `services/api/app/prospecting/` |
| Publik delning | `/api/v1/public/prospecting/proposals/{token}` + `/presentations/{token}` + opt-out | token SHA-256, no-store, CSP, noindex |
| Admin-hub | Startmeny-kort Platform/Kundzon/Sales Desk/**Nova**/film | `AdminStartHub.tsx` |

### 1.2 Kontrollerat flöde (redan implementerat)

1. Logga in (NovaLoginGate → `/auth/login`, token i `salesos.salesDeskToken`).
2. Skapa kampanj **eller** registrera publik URL manuellt (dedupe på normaliserad domän per tenant).
3. Avgränsad en-sida HTML-audit: robots.txt, inget JS, blockerar RFC1918/metadata/loopback, max 1,5 MB, 10 s, port 80/443.
4. Valfri PageSpeed-enrichment (Lighthouse + bounded screenshot).
5. Versionshanterat kundupplägg + e-postutkast + 9-kapitels mötesfilm (textning, valfri browser-röst, intern kalkyl osynlig för kund).
6. Mänsklig verifiering: analys · kontaktkälla · rättslig grund · innehåll · inte suppressed.
7. Approve låser versionen. Ny edit = ny version.
8. Tokeniserad share (plaintext token en gång) + kö/mock **eller** smtp_generic/resend när kill switch är på.
9. One-click opt-out + tenant-suppression. Audit lagrar **domän**, inte full adress.

### 1.3 Provider-gates (fail-closed)

Från `app/core/config.py` + `infra/prod/env.production.example`:

```
PROSPECTING_DISCOVERY_PROVIDER=disabled     # google_places | disabled
PROSPECTING_FETCH_ENABLED=false
PROSPECTING_EMAIL_PROVIDER=disabled         # disabled | mock | resend | smtp_generic
PROSPECTING_REAL_EMAIL_ENABLED=false        # true kräver HTTPS public base + konfigurerad provider
AGENT_SCHEDULER_ENABLED=false
```

`REAL_EMAIL_ENABLED=true` utan host/mailbox/HTTPS → **appen startar inte**.

### 1.4 Tester

| Svit | Omfattning |
|------|------------|
| `tests/test_website_prospecting_agent.py` | 12 tester: mount, HTML-analys, URL-guard, human review + opt-out, dedupe, PageSpeed bound, Resend idempotency, SMTP kill-switch, allowlist, log-redaction |
| `apps/internal-pilot-ui/scripts/test-website-prospect-agent.mjs` | Statiska lås: live-route, login-gate, legacy redirect |
| `test-nova-video.mjs` | Film vs `/nova` separation, 8 MP3 |

Ingen Playwright-spec för Nova. Inte CI merge-gate.

---

## 2. Produktionsposture (hel1 / salesos.se)

| Punkt | Status |
|-------|--------|
| `/nova` HTTP 200 | ✅ sedan M14 (2026-08-27) |
| Apex landing länkar Nova | ✅ |
| Fetch på host | 🔴 AV (explicit i remaining-todo: “håll AV tills egress + explicit enable”) |
| Discovery-nyckel | 🔴 Ingen `GOOGLE_PLACES_API_KEY` i prod-exempel |
| H8c dual | ✅ `dual_valid` @ 2026-08-17T20:50Z · `NOVA-SMTP-GENERIC-HOST-20260817` |
| H8c kod-unlock | ✅ smtp_generic tillåten i `ENV=production` när kill switch + secrets + HTTPS |
| H8c host env | 🔴 **not_applied** — kill switch fortfarande off. Register nämner `/etc/salesos/salesos.env`; verifierad sökväg är **`/opt/salesos/.env`** |
| Resend-alternativ | 📄 Runbook [nova-outbound-without-loopia-mail.v1.md](../runbooks/nova-outbound-without-loopia-mail.v1.md) — när Loopia-mail saknas |
| G4 CRM-mail | 🟡 Packet `ready_for_signature` · kod på main · **NOT enabled** |
| Nätverksegress-policy | 📄 Dokumenterad i runbook, inte verifierad som host-kontroll här |

**Viktig distinktion:** `/nova` **skickar aldrig** i isolerad demo. Live-session kan köa. Riktig SMTP sker bara från autentiserad workspace när kill switch är on. Det är avsikt, inte bugg.

---

## 3. Motsvarande projekt — vad de säljer vs Nova

Nova sitter i **K5 (prospektering/data)** med en fot i **K2 (AI Sales OS)**. Den ska *inte* bli en global kontaktgraf.

| Produkt | Vad de är bäst på | Vad Nova redan har | Vad de har som Nova saknar | Lärdom — äg / integrera / avstå |
|---------|-------------------|--------------------|----------------------------|----------------------------------|
| **Clay** ($149–800/mån) | Waterfall-enrichment, Claygent research, credits, unlimited seats | Evidens-first audit, human review, suppression | Multi-source enrichment, spreadsheet-UX, 50+ providers, credit-metering | **Integrera** “bring your own data” bakom evidenslager. Bygg inte Clay. |
| **Apollo.io** ($49–119/säte) | 275M+ kontakter, sequences, dialer, intent | Kampanj + manuell URL + score | Kontaktgraf, e-postsekvenser, telefoni, buying-intent | **Avstå** egen databas. Sequences först efter G4/H8c + klagomålsmätning. |
| **Instantly / Lemlist / Smartlead** | Unbegränsad inbox-rotation, warmup, deliverability | List-Unsubscribe, allowlist From, idempotency | Warmup, bounce webhooks, A/B, volym | **Avstå** massutskick. Låna bounce/complaint-hantering i liten skala. |
| **HubSpot Sales Hub** | Prospecting workspace + CRM + sequences i samma affär | Fristående Nova-yta | Deal-objekt, aktivitetstidslinje, sequences inifrån CRM | **Äg** handoff Nova → kanonisk Affär/Lead. Det är P1. |
| **Copy.ai / Regie.ai “Sales OS”** | AI-workflows ovanpå *andras* CRM | Vertikal plattform + film | Call capture, CRM-hygien-agenter | **Äg** “AI assisterar, människa skickar”. Kopiera inte autonoma SDR. |
| **11x / Artisan (AI-SDR)** | Autonom outreach | Fail-closed, inget auto-send | Volym-SDR | **Avstå.** Strider mot Nova-mandat och GDPR-posture. |
| **ZoomInfo** | Intent + org chart | Policy-/evidenslager | Global identitetsdata | **Integrera** som källa med laglig grund + färskhet + review. |
| **Hunter / Lusha / Dropcontact** | E-postfinder | “Never invent an email” | Catch-all verify | **Integrera** bakom verifieringskälla. Aldrig gissa adress. |
| **Calendly / HubSpot meetings** | Booking i CTA | Mötes-CTA i copy | Riktig kalender | **P0-4 i landskapsrapporten** — efter H8c. |

**Nova:s unika kombination (ingen av ovan har den):**  
SSRF-säker evidensaudit → versionshanterat förslag → **självkörande kundmötesfilm** → mänskligt mandat → tokeniserad share + opt-out. Det är säljargumentet. Fyll luckorna *runt* den loopen, ersätt den inte.

---

## 4. Completion-todo

Insats: **S** = dagar · **M** = 1–2 v · **L** = 3+ v (agent-drivet).  
Ägare: **ops** = Mattias/host · **dual** = Micha+Mattias · **dev** = kod.

### P0 — Färdigställ *befintlig* Nova så Formkök kan köra ett skarpt case

Detta är “färdig” i runbookens mening. Ingen ny produktkategori.

| ID | Åtgärd | Varför | Insats | Ägare | Beroende / STOP |
|----|--------|--------|--------|-------|-----------------|
| **N0-1** | **Host egress-policy** för prospecting-fetch: tillåt DNS + godkända HTTPS; neka metadata/RFC1918/loopback | Runbook kräver det innan `PROSPECTING_FETCH_ENABLED=true` | S | ops | Ingen dual; ingen `.env` i chat |
| **N0-2** | Sätt `PROSPECTING_FETCH_ENABLED=true` på hel1 efter N0-1 + smoke mot en *egen* publik sida | Utan fetch är “Analysera URL” ett skal. Packet: [OPS-NOVA-LIVE-FETCH-HEL1-20260830-packet.v1.md](../design/production-go-decisions/OPS-NOVA-LIVE-FETCH-HEL1-20260830-packet.v1.md) · `make print-nova-fetch-env` | S | ops | Evidence-rad i OPERATOR-NEXT. Kod 2026-08-30: list latest + UI honesty. Host flagga **inte** applicerad. |
| **N0-3** | **H8c host-apply**: mailbox (Triplus `smtp_generic` *eller* Resend per [utan-Loopia-runbook](../runbooks/nova-outbound-without-loopia-mail.v1.md)) i `/opt/salesos/.env`; `PROSPECTING_PUBLIC_BASE_URL=https://salesos.se`; kill switch **false** tills smoke | Dual redan valid — bara env + ack | S | ops + dual ack | Passwords aldrig i git/UI. `/nova` skickar fortfarande inte i demo. |
| **N0-4** | SPF/DKIM/DMARC för From-domänen (triplusmedia.com *eller* salesos.se via Resend) | Annars landar mail i skräp — Instantly/Apollo vinner på deliverability | S | ops | DNS hos Loopia, domän flyttas inte |
| **N0-5** | Smoke: inloggad `/nova` → manuell URL → analys → förslag → approve → **ett** test-send till operatörsadress · `/nova` demo still silent | Stänger H8c `host_env_status: not_applied` | S | ops | Test får bara gå till autentiserad operatörs e-post |
| **N0-6** | PageSpeed-nyckel (valfritt men rekommenderat) så metrics inte bara är HTML-heuristik | Filmen och score blir trovärdiga; analyzer säger själv att CWV kräver Lighthouse | S | ops | Nyckel i host env |
| **N0-7** | Juridik: counsel validerar B2B legitimate interest, retention 180d, transparency, direktmarknadsföring | Runbook kräver det före production use | S | human | Inte agent |

**P0 klar =** ett Formkök-case kan analyseras live och ett godkänt mail kan gå ut. Fortfarande ingen Places-volym, ingen CRM-sync.

### P1 — Gör Nova till *säljverktyg* (mot HubSpot/Clay, inte mot Instantly)

| ID | Åtgärd | Varför | Insats | Ägare | STOP |
|----|--------|--------|--------|-------|------|
| **N1-1** | **Handoff Nova → CRM:** `POST …/prospects/{id}/promote` skapar SalesDesk/CRM-lead + case under samma tenant/profile, med evidenslänk, utan att kopiera e-post till seed | HubSpot vinner för att prospecting *är* CRM. Nova är silo idag (ingen `prospect`-referens utanför `app/prospecting/`) | M | dev | Ingen auto-send. Ingen PII i fixtures. **API+tests @ 2026-08-30** (PR #185) |
| **N1-2** | Visa Nova-kort på Kundzon-lead och Internal Pilot lead (“öppna i Nova”) | Säljaren ska inte byta app | S–M | dev | Read-only först. **Lead-kort @ 2026-08-30** (`guyverx2/nova-crm-card-n1-2`); case-kort deferred |
| **N1-3** | **CSV/manual bulk intake** (UI + API, ≤ N rader, same dedupe) — Places kan vänta | Clay/Apollo startar med lista; Places-nyckel är betald och operator-gated | S | dev | Ingen directory-scrape. **API+UI @ 2026-08-30** (`guyverx2/nova-csv-intake-n1-3`); max 50; ingen e-post från CSV |
| **N1-4** | Google Places enable *efter* N0-2: nyckel på host, `PROSPECTING_DISCOVERY_PROVIDER=google_places`, kampanj-limit, kostnadstelemetri (A-6-mönster) | Kampanjknappen är död utan provider (409 `DISCOVERY_PROVIDER_DISABLED`) | S | ops + dual om betald | Fail-closed om nyckel saknas |
| **N1-5** | **Kontakt-enrichment adapter** (Hunter/Dropcontact/Clay webhook): input = domän + roll, output = kandidat + källa + confidence; UI kräver “verifiera källa” innan `contact_verified=true` | Marknaden säljer e-postfinder; Nova får **aldrig** inferera adress (runbook) | M | dev | Ingen auto-verify. Laglig grund per rad. |
| **N1-6** | Kalender-CTA i förslag/film: länk till befintlig slot-provider (Cal.com/Calendly) *eller* P0-4 mötesbokning när G4 är on | Köksförsäljning = hembesök; copy lovar “tisdag eller torsdag” utan system | M | dev | Beror på G4 för bekräftelsemail |
| **N1-7** | Playwright smoke: login → tom yta → manuell URL (fixture HTML via mock) → proposal preview → approve disabled utan checks | FE-BLK-E2E residual; Nova saknas helt i `tests/e2e` | S | dev | Ingen prod-host; synthetic only |
| **N1-8** | G4 enable (CRM invite/reset/quote_share) — *parallellt, inte Nova-blockerande* | Inbjudan till Nova-användare är manuell idag (M2) | M | dual + ops | Packet redan `ready_for_signature`. Ingen `lead_confirm` förrän N4. |

### P2 — Differentiering och “Claygent-lite” (P2-2 i landskapsrapporten)

| ID | Åtgärd | Varför | Insats | STOP |
|----|--------|--------|--------|------|
| **N2-1** | **Research-agent ovanpå evidens** (ACP/Ollama först): extra publika källor (om-oss, Google Business-text som *redan hämtats*) → sammanfattning med citations. Human-verify kvar | Clay tar $149+ för research; Nova har SSRF-fetch + film som fundament ([P2-2](../analysis/competitive-landscape-and-improvements-2026-08-28.v1.md)) | M | Ingen JS-crawl, ingen LinkedIn-scrape, ingen Phase E-expand utan dual |
| **N2-2** | Multi-page *allowlist-crawl*: operator kryssar max N sidor från same-origin länkar (kontakt, tjänster) | En-sida är ärlig men tunn mot “hela sajten” | M | robots.txt per URL; samma SSRF-guard; default 1 sida |
| **N2-3** | Bakgrundskö för analys + film-HTML (E-8: arq/RQ; `platform_operator_jobs` som posture) | Fetch+PageSpeed på request-tråd timeoutar; Instantly/Clay kör async | M | `AGENT_SCHEDULER_ENABLED` fortfarande operator. Ingen auto-send från worker. |
| **N2-4** | Bounce/complaint ingest (Resend webhook *eller* SMTP DSN) → suppression `reason=bounce\|complaint` | Schema har redan `bounce`/`complaint`; ingen webhook | S–M | Ingen pixel/open-tracking (integritet) |
| **N2-5** | Nova → win/loss: när CRM-lead stängs, skriv tillbaka till prospect (`won`/`lost` + orsak). Matar A-4 scoring | D-2 win/loss finns i CRM (`BE-QUICK-WINS`); Nova tar inte del | S | Ingen prediktiv etikett |
| **N2-6** | AI-kostnad per analys/förslag/film i `ai_cost_events` (A-6 redan live för orchestrator) | PageSpeed + ev. LLM får inte bli tyst räkning | S | Simulated-flag default |
| **N2-7** | Offentlig “Köksförsäljningsbarometer”-stub från *anonymiserad* prospecting-aggregat (B-3) | Inbound till Nova; datavallgrav | S per utgåva | Ingen PII, ingen tenant-läcka |

### P3 — Optimering, kvalitet, SaaS-hygiene

| ID | Åtgärd | Varför | Insats | STOP |
|----|--------|--------|--------|------|
| **N3-1** | i18n-katalog för Nova UI (G-1) — EN parallellt med SV; idag hårdkodat i `WebsiteProspectAgent.tsx` | Kundzon har SV/EN-våg; Nova hamnade utanför | M | Inga PII i catalogs |
| **N3-2** | WCAG på login-gate, tabell, review-checkboxes (G-2) | Offentlig sektor / större dealers | S–M | |
| **N3-3** | Performance: analys-cache på `snapshot_sha256` (samma URL+hash → ingen re-fetch); Postgres index redan via tenant+domain | P2-4 teknisk optimering | S | Cache får inte skippa robots/re-verify |
| **N3-4** | Rate-limit `POST /analyses` och `/discover` per tenant (landing-leads-mönster) | Places + fetch kan bli dyrt | S | |
| **N3-5** | Observability: prospecting-span i E-1 (fetch_ms, findings_count, delivery_status); koppla 5xx till error-events (E-2 redan inne) | Drift är värderingsrisk | S–M | Inga recipient-adresser i spans |
| **N3-6** | Deliverability dashboard: queued / sent / suppressed / bounced / daily_limit — operator-only | Instantly säljer detta; vi har datan i audit | S | |
| **N3-7** | Film: valfri svensk *server*-narration redan finns som produktfilm; mötesfilmen använder browser TTS — erbjud tyst default + “spela upp” | Honesty: captions är auktoritativa | S | Ingen remote TTS-vendor default |
| **N3-8** | White-label film/förslag mot tenant brand (H-1 — brand-profiler finns) | Formkök vs Småkök vs Mattex | S–M | Ingen silent commercial i paketpriser |
| **N3-9** | CSV-export av evidenspaket (print-PDF finns via browser; server-PDF medvetet avstått) | Säljare vill bifoga i CRM | S | Samma redaction som public HTML |
| **N3-10** | Staging-klon för prospecting-send (E-4) så H8c inte testas i prod mot riktiga bolag | “Testa i prod” tills det inte går | S–M | Synthetic mottagare |

---

## 5. Förbättringar från syskonrapporter — mappade till Nova

Endast poster som faktiskt rör Nova/prospektering/outbound. Resten (Gate B, Stolkar, Fortnox, 3D) lämnas utanför.

| Källa | ID | Relevans för Nova | Rekommendation |
|-------|----|-------------------|----------------|
| Landscape 08-28 | **P0-1** G4 e-post | CRM-kanaler, inte Nova — men samma SMTP-mönster | Kör N1-8 parallellt med N0-3 |
| Landscape 08-28 | **P0-4** mötesbokning | Nova-CTA är tom | N1-6 |
| Landscape 08-28 | **P2-2** Claygent-lik research | Direkt Nova-roadmap | N2-1 |
| Landscape 08-28 | **P2-4** kö + cache + Lighthouse-budget | Fetch/film på request-tråd | N2-3, N3-3 |
| Further 08-30 | **A-4** lead scoring på utfall | Kräver N1-1 + N2-5 först | Efter P1 |
| Further 08-30 | **A-6** AI-kostnad | PageSpeed/LLM | N2-6 |
| Further 08-30 | **B-3** marknadsinsikt som leadmagnet | Anonymiserad prospecting | N2-7 |
| Further 08-30 | **E-8** generell bakgrundskö | Analys/film | N2-3 |
| Further 08-30 | **G-1/G-2** i18n + a11y | Nova UI | N3-1, N3-2 |
| Benchmark 08-29 | ZoomInfo-rad | BYO data provider bakom evidens | N1-5 |
| Benchmark 08-29 | **P2 kontrollerad outbound** | Preview, allowlist, suppression, rate limit, idempotens | Redan i Nova-kod; saknar host enable (N0-3) och bounce (N2-4) |
| Remaining-todo | “Prospecting providers på prod — håll AV” | Fortfarande korrekt tills N0-1 | Inte tyst enable |

---

## 6. Medvetet *inte* i Nova-completion

| Avstå | Skäl |
|-------|------|
| Egen global kontaktgraf / Apollo-klon | ZoomInfo/Clay-territorium; juridik + kostnad |
| Autonom AI-SDR (11x) | Strider mot “människan beslutar” och H8 AI-outbound=false |
| Directory HTML-scrape (allabolag, hitta.se, …) | Explicit förbjudet i runbook |
| Open-/click-pixel | Integritet; List-Unsubscribe räcker i P0 |
| JS-exekvering / headless Chrome i API-processen | SSRF/RCE-yta; PageSpeed är den tillåtna lab-vägen |
| LinkedIn-automation | ToS + ny dual; inte beachhead |
| Mass sequences / warmup-farm | Instantly-territorium; G4-packet förbjuder bulk/marketing |
| Server-side PDF-renderer | Browser print är medveten design |
| `/nova` demo-nätverkssend | Dual säger `nova_demo_send: false` |

---

## 7. Föreslagen ordning (90 dagar, Nova-spår)

```
Vecka 1     N0-1 egress → N0-2 fetch enable → N0-6 PageSpeed
            N0-4 DNS (SPF/DKIM) parallellt
Vecka 1–2   N0-3 H8c env (kill switch false) → N0-5 ett testmail → kill switch true
            N0-7 counsel (human, kan löpa längre)
Vecka 2–3   N1-3 CSV intake · N1-7 Playwright · N1-1/N1-2 CRM-handoff
Vecka 3–4   N1-4 Places om nyckel finns · N1-5 enrichment-adapter (verify-only)
            N1-8 G4 om dual pastas (oberoende)
Vecka 5–8   N2-1 research-agent shadow · N2-3 worker · N2-4 bounce · N2-6 cost
Vecka 9–13  N1-6 booking · N2-2 multi-page allowlist · N3-1 i18n · N3-6 deliverability UI
```

**Första värdet som syns för Micha:** N0-5 — ett riktigt, godkänt mail med länk till film, mot ett valt bolag. Allt före det är scaffolding.

---

## 8. Klarmått

| Mått | P0 (användbar) | P1 (säljverktyg) | P2 (nisch-ledare) |
|------|----------------|------------------|-------------------|
| Live analys på host | ≥1 egen sajt | ≥10 tenant-URL:er | Worker-kö, p95 < 15 s |
| Riktig leverans | 1 test → operatör | 1 kund efter dual+approve | Bounce-rate loggad, <2 % |
| CRM | — | Prospect syns som lead/case | Win/loss återkopplad |
| Discovery | Manuell URL | CSV och/eller Places | Enrichment + research citations |
| Film | Preview + public token | Öppnad av minst 1 mottagare | Brandad per tenant |
| Styrning | Kill switch bevisad av/på | Daily limit + suppression UI | Cost + deliverability dashboard |

Obehörig extern sändning = **noll** i alla faser.

---

## 9. Relaterade filer

| Fil | Roll |
|-----|------|
| [website-prospecting-agent.v1.md](../runbooks/website-prospecting-agent.v1.md) | Operator runbook (flöde, privacy, verify) |
| [HD-PROD-NOVA-SMTP-GENERIC-HOST.md](../design/production-go-decisions/HD-PROD-NOVA-SMTP-GENERIC-HOST.md) | H8c dual — host send |
| [nova-outbound-without-loopia-mail.v1.md](../runbooks/nova-outbound-without-loopia-mail.v1.md) | Resend när Loopia-mail saknas |
| [OPS-G4-REAL-OUTBOUND-20260827-dual-packet.v1.md](../design/production-go-decisions/OPS-G4-REAL-OUTBOUND-20260827-dual-packet.v1.md) | CRM-mail, inte Nova |
| [nova-film-sv.md](../demo/nova-film-sv.md) | Filmmanus |
| `services/api/app/prospecting/` | Analyzer, discovery, outbound, presentation, API |
| `apps/internal-pilot-ui/src/WebsiteProspectAgent.tsx` | Live UI |

---

*Upprättad 2026-08-30. Status verifierad mot kod (`prospecting/*`, `WebsiteProspectAgent.tsx`, `config.py`, prod env-exempel), OPERATOR-NEXT (M14 `/nova` 200, H8c not_applied, G4 ready_for_signature) och de tre analysrapporterna 2026-08-28–30. Ingen gate, host-env eller outbound har ändrats av detta dokument.*
