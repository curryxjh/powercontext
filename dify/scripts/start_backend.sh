#!/usr/bin/env bash
# Start the 忘川当铺 adapter. Dependencies: pip install -r backend/requirements.txt
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$root/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$root/.env"
  set +a
fi

cd "$root/backend"
exec "${PYTHON:-python}" -m wangchuan
