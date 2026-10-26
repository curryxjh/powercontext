#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data_dir="${1:-"$repo_root/minimax/.runtime"}"
mkdir -p "$data_dir"
data_dir="$(cd "$data_dir" && pwd)"

cd "$repo_root"
"$repo_root/minimax/.venv/bin/python" -m minimax.sdd_context context \
  --data-dir "$data_dir" --query status > "$data_dir/context-before.json"
mcode exec --input - --file "$data_dir/context-before.json" \
  --cwd "$repo_root" --model minimax/MiniMax-M3 \
  --permission full --prompt-mode coding --timeout 5m --output-format json \
  < "$repo_root/minimax/evidence/minimax-prompt.md" > "$data_dir/agent-run.json"
