#!/usr/bin/env bash
# Print Nova fetch-only host env (no secrets, no real email). Operator pastes into /opt/salesos/.env.
set -euo pipefail

cat <<'EOF'
# Nova live path N0-2 — website fetch only
# Live workspace: https://salesos.se/nova
# Do NOT paste this together with PROSPECTING_REAL_EMAIL_ENABLED=true.
# SMTP/H8c is a separate step after one own-site analysis smoke.

PROSPECTING_FETCH_ENABLED=true
PROSPECTING_DISCOVERY_PROVIDER=disabled
PROSPECTING_PUBLIC_BASE_URL=https://salesos.se

# Leave email kill switch and mailbox secrets unchanged until fetch smoke passes.
# PROSPECTING_REAL_EMAIL_ENABLED must stay false until H8c host-apply.

# After edit: restart API, then:
#   curl -sf https://salesos.se/health/ready
#   GET /api/v1/prospecting/summary (authenticated) → website_fetch.enabled=true
# Smoke: /nova → Analysera URL → own public page → evidence packet present
# Rollback: PROSPECTING_FETCH_ENABLED=false + restart
EOF
