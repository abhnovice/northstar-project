#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

RENDER_PORT="${PORT:-10000}"

if [[ -z "${DATABASE_URL:-}" && -z "${DB_CRED:-}" ]]; then
  echo "Configure DATABASE_URL or DB_CRED in Render before starting Northstar." >&2
  exit 1
fi

if [[ ! "$RENDER_PORT" =~ ^[0-9]+$ ]]; then
  echo "PORT must be a number; received: $RENDER_PORT" >&2
  exit 1
fi

if [[ ! -f static/ui/index.html ]]; then
  echo "The production frontend is missing. Run 'npm ci && npm run build' during the Render build step." >&2
  exit 1
fi

mkdir -p data

echo "Starting Northstar on 0.0.0.0:${RENDER_PORT}"
exec python -m uvicorn main:app \
  --host 0.0.0.0 \
  --port "$RENDER_PORT" \
  --proxy-headers
