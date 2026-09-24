#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

CMD="${1:-sync}"

require_clean() {
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "ERROR: working tree has uncommitted changes; refusing unsafe Git operation." >&2
    git status --short >&2
    exit 2
  fi
}

require_main() {
  local branch
  branch="$(git branch --show-current)"
  if [[ "$branch" != "main" ]]; then
    echo "ERROR: expected branch main, found $branch." >&2
    echo "Finish or safely leave the current task branch before synchronizing main." >&2
    exit 3
  fi
}

pull_main_ff() {
  require_clean
  require_main
  git fetch origin main
  git pull --ff-only origin main
}

prepare_task() {
  local task_id="${1:-}"
  if [[ -z "$task_id" ]]; then
    echo "usage: ./exchange.sh prepare TASK_ID" >&2
    exit 64
  fi

  require_clean
  require_main
  git fetch origin main
  git pull --ff-only origin main

  python3 .bridge/bridge_cli.py validate-request "$task_id"
  local task_branch
  task_branch="$(python3 .bridge/bridge_cli.py branch "$task_id")"

  if git show-ref --verify --quiet "refs/heads/$task_branch"; then
    echo "ERROR: local task branch already exists: $task_branch" >&2
    exit 4
  fi

  if git ls-remote --exit-code --heads origin "$task_branch" >/dev/null 2>&1; then
    echo "ERROR: remote task branch already exists: $task_branch" >&2
    exit 5
  fi

  git switch -c "$task_branch" origin/main
  echo "TASK_BRANCH=$task_branch"
  echo "BASE_COMMIT=$(git rev-parse HEAD)"
  python3 .bridge/bridge_cli.py validate-request "$task_id"
}

case "$CMD" in
  sync)
    pull_main_ff
    python3 .bridge/bridge_cli.py status
    echo "--- NEXT REQUEST ---"
    python3 .bridge/bridge_cli.py next
    ;;
  pull)
    pull_main_ff
    ;;
  status)
    python3 .bridge/bridge_cli.py status
    ;;
  next)
    python3 .bridge/bridge_cli.py next
    ;;
  prepare)
    prepare_task "${2:-}"
    ;;
  *)
    echo "usage: ./exchange.sh [sync|pull|status|next|prepare TASK_ID]" >&2
    exit 64
    ;;
esac
