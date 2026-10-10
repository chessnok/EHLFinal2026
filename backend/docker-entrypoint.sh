#!/bin/sh
set -e

# Bring the schema up to date before serving (set RUN_MIGRATIONS=0 to skip).
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  alembic upgrade head
fi

exec "$@"
