#!/usr/bin/env bash
# Saves your GitHub OAuth App's values to backend/.env. The running backend picks them up by itself.
set -euo pipefail
cd "$(dirname "$0")/.."

read -rp "GitHub Client ID: " client_id
read -rsp "GitHub Client Secret (hidden as you type): " client_secret
echo

if [ -z "$client_id" ] || [ -z "$client_secret" ]; then
  echo "Both values are needed. Nothing was saved."
  exit 1
fi

touch backend/.env
chmod 600 backend/.env
grep -vE '^(GITHUB_CLIENT_ID|GITHUB_CLIENT_SECRET)=' backend/.env > backend/.env.tmp || true
{
  cat backend/.env.tmp
  echo "GITHUB_CLIENT_ID=$client_id"
  echo "GITHUB_CLIENT_SECRET=$client_secret"
} > backend/.env
rm backend/.env.tmp

echo "Saved. Reload http://localhost:3000 and click Sign in with GitHub."
