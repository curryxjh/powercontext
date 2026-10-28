#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

if [ -f .venv/Scripts/activate ]; then
  # Git Bash / Windows
  . .venv/Scripts/activate
else
  . .venv/bin/activate
fi

python -m pip install -q -r requirements.txt
export PYTHONUTF8=1
exec python run.py
