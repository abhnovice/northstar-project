#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

cleanup() {
  trap - EXIT INT TERM
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  wait "${FRONTEND_PID:-}" "${BACKEND_PID:-}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "Starting React frontend: http://127.0.0.1:${FRONTEND_PORT}/ui/"
npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

echo "Starting FastAPI backend: http://127.0.0.1:${BACKEND_PORT}"
python -m uvicorn main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!

echo "Press Ctrl+C to stop both servers."

while kill -0 "$FRONTEND_PID" 2>/dev/null && kill -0 "$BACKEND_PID" 2>/dev/null; do
  sleep 1
done
