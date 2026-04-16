#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
worker_dir="${repo_root}/cloudflare-worker"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required" >&2
  exit 1
fi

cd "${worker_dir}"

if [[ ! -d node_modules ]]; then
  npm install
fi

npx wrangler deploy
