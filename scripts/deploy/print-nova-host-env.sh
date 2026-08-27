#!/usr/bin/env bash
# Print H8c Nova prospecting host env (no secrets). Operator pastes into host env file.
set -euo pipefail

cat <<'EOF'
# Nova website prospecting — H8c (dual_valid NOVA-SMTP-GENERIC-HOST-20260817)
# Live workspace: https://salesos.se/nova
# Legacy /website-agent redirects to /nova in the SPA bootstrap.

PROSPECTING_FETCH_ENABLED=true
PROSPECTING_DISCOVERY_PROVIDER=disabled
PROSPECTING_EMAIL_PROVIDER=smtp_generic
PROSPECTING_REAL_EMAIL_ENABLED=true
PROSPECTING_PUBLIC_BASE_URL=https://salesos.se
PROSPECTING_SMTP_HOST=mailcluster.loopia.se
PROSPECTING_SMTP_PORT=587
PROSPECTING_SMTP_STARTTLS=true
PROSPECTING_SMTP_MAILBOX_1_ADDRESS=martin@triplusmedia.com
PROSPECTING_SMTP_MAILBOX_1_PASSWORD=<host secret — never git/chat>
PROSPECTING_SMTP_MAILBOX_2_ADDRESS=micha@triplusmedia.com
PROSPECTING_SMTP_MAILBOX_2_PASSWORD=<host secret — never git/chat>

# Interactive helper (local or SSH on host):
#   make configure-nova-smtp ENV_FILE=/opt/salesos/.env
# Smoke (login only):
#   make smoke-nova-smtp ENV_FILE=/opt/salesos/.env

# --- Alternativ: Resend (ingen Loopia-mailinloggning krävs) ---
# Domän verifieras via DNS-TXT hos Loopia. Se:
#   docs/runbooks/nova-outbound-without-loopia-mail.v1.md
#
# PROSPECTING_EMAIL_PROVIDER=resend
# PROSPECTING_REAL_EMAIL_ENABLED=false
# PROSPECTING_PUBLIC_BASE_URL=https://salesos.se
# PROSPECTING_EMAIL_API_KEY=<host secret>
# PROSPECTING_EMAIL_FROM=nova@salesos.se

# After edit: restart API, then verify:
#   curl -sf https://salesos.se/health/ready
#   GET /api/v1/prospecting/summary (authenticated) → email.real_send_enabled=true
# Smoke: /nova → analyze URL → approve → one test send to operator email
EOF
