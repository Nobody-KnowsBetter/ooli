#!/usr/bin/env bash
# Starts everything DocGuard needs: Qwen through Ollama, the API and the dashboard.
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${DOCGUARD_MODEL:-qwen2.5-coder:3b}"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -e ".[dev]" -r backend/requirements.txt
fi
[ -d frontend/node_modules ] || npm --prefix frontend install --no-audit --no-fund

if command -v ollama >/dev/null && curl -sf -m 2 http://127.0.0.1:11434/api/tags >/dev/null; then
  ollama list | grep -q "$MODEL" || ollama pull "$MODEL"
else
  echo "Ollama isn't running, so scans will use rules only. Start the Ollama app to use Qwen."
fi

.venv/bin/python -m uvicorn backend.app.main:app --port 8000 &
BACKEND=$!
trap 'kill $BACKEND' EXIT

echo "Dashboard: http://localhost:3000"
npm --prefix frontend run dev
