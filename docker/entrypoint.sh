#!/bin/sh
# Bring the schema up to date before serving, then exec the server so it keeps
# PID 1 and receives stop signals directly.
set -eu

if [ "${NOVA_RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "nova: applying database migrations"
  alembic -c /app/alembic.ini upgrade head
fi

exec "$@"
