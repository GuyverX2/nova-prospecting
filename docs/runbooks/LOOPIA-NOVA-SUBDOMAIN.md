# Nova på `nova.salesos.se`

Detta mappar den befintliga Nova/Pilot-SPA:n från `https://salesos.se/nova` till
`https://nova.salesos.se`. Koden kör fortfarande samma pilot-build; hostbytet är
DNS + Caddy-routing, inte en ny frontend-app eller en ny API-instans.

## Loopia DNS

Skapa följande post i DNS-zonen för `salesos.se`:

| Typ | Host/namn | Värde | TTL |
|---|---|---|---:|
| A | `nova` | `157.180.64.16` | 300 eller 3600 |

`157.180.64.16` är den dokumenterade SalesOS-hel1-adressen. Kontrollera den mot
aktuell hostinformation före ändring; använd inte den gamla Jarvis-adressen.

Gör också följande kontroller i Loopia:

1. Det får inte finnas en konkurrerande `CNAME` för `nova` när A-posten skapas.
2. Om en gammal wildcard-post `*.salesos.se` finns kvar, låt den ligga endast om
   den inte pekar till fel server; den explicita `nova`-posten ska vara den
   avsedda träffen.
3. Skapa ingen MX-, SPF-, DKIM- eller DMARC-post för `nova`. Nova använder
   befintlig mailkonfiguration; webbsidans subdomän ska inte bli en maildomän.
4. Om zonen har en begränsande CAA-policy måste den tillåta den ACME-utfärdare
   som Caddy använder, normalt `letsencrypt.org`.
5. Säkerställ att VPS-brandväggen och eventuell Loopia/host-forwarding släpper
   TCP 80 och 443 till `157.180.64.16`. Caddy behöver port 80 för HTTP-01-
   challenge och HTTP→HTTPS-redirect.

DNS-förändringen görs av operatören i Loopia. Den ska vara klar innan Caddy
reloadas på produktionsservern.

## Caddy och TLS

Produktionsmallarna har en separat site för `nova.salesos.se`:

- `/` redirectas till `/nova`.
- `/api/*` proxas till FastAPI på loopback.
- `/health*` proxas till FastAPI.
- övriga vägar serveras från `/opt/salesos/www/pilot` med SPA-fallback.
- Caddy utfärdar och förnyar HTTPS-certifikatet automatiskt när DNS pekar rätt
  och port 80/443 är nåbara.

Operatörssekvens på `salesos-hel1`:

```bash
# Efter DNS-propagation
getent hosts nova.salesos.se
curl -I http://nova.salesos.se/
curl -fsS https://nova.salesos.se/health/ready
curl -I https://nova.salesos.se/nova

# Kontrollera och ladda Caddy-konfigurationen enligt hostens runbook
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

Förväntat:

- HTTP svarar med redirect mot HTTPS eller mot den konfigurerade canonical URL:n.
- `https://nova.salesos.se/` redirectar till `/nova`.
- `https://nova.salesos.se/nova` svarar `200` från pilot-SPA:n.
- `https://nova.salesos.se/health/ready` svarar från API:t.
- certifikatet innehåller `nova.salesos.se` och webbläsaren visar ingen
  certifikatvarning.

## API/CORS och mail

API-anropen är same-origin när Nova öppnas på `nova.salesos.se`, så ingen separat
CORS-origin behövs för dessa `/api/*`-anrop. Om Nova eller en framtida separat
frontend börjar anropa API:t från ett annat origin måste originet läggas till i
`CORS_ORIGINS` i `/etc/salesos/salesos.env`; ändra inte produktionens env enbart
för detta hostbyte.

Mailposter och mailflöden påverkas inte av webbroutningen. Ändra inte MX,
SPF, DKIM eller DMARC för att publicera Nova som webbhost.

## Lokal kontroll

Lägg till följande i `/etc/hosts` för lokal prod-simulering:

```text
127.0.0.1 nova.salesos.localhost
```

Starta sedan `infra/prod/Caddyfile.local-prod.example` och kontrollera
`http://nova.salesos.localhost:5180/`.
