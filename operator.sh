#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

command -v git >/dev/null 2>&1 || fail "git is required."
command -v python3 >/dev/null 2>&1 || fail "python3 is required."
command -v codex >/dev/null 2>&1 || fail "codex is required."

branch="$(git branch --show-current)"
[[ "$branch" == "main" ]] || fail "expected branch main, found ${branch:-detached HEAD}."

if ! git diff --quiet || ! git diff --cached --quiet; then
  git status --short >&2
  fail "tracked worktree changes are present; refusing unsafe execution."
fi

untracked="$(git ls-files --others --exclude-standard)"
if [[ -n "$untracked" ]]; then
  printf '%s\n' "$untracked" >&2
  fail "untracked files are present; refusing unsafe execution."
fi

git fetch origin main
git pull --ff-only origin main

task_id="$(python3 .bridge/bridge_cli.py next-id)"
task_branch="$(python3 .bridge/bridge_cli.py next-branch)"
request_path=".bridge/requests/${task_id}.json"

[[ -f "$request_path" ]] || fail "structured request not found: $request_path"

if git show-ref --verify --quiet "refs/heads/$task_branch"; then
  fail "local task branch already exists: $task_branch"
fi

if git ls-remote --exit-code --heads origin "$task_branch" >/dev/null 2>&1; then
  fail "remote task branch already exists: $task_branch"
fi

prompt="Operate only in ${ROOT}.
Read and follow the structured request at ${request_path} exactly.
The discovered task_id is ${task_id} and the required operator branch is ${task_branch}.
Start from the current clean main branch. Use ./exchange.sh prepare ${task_id}, perform the requested work, validations, work commit, report/receipt commit, and push lifecycle.
Do not parse task instructions from this bootstrap text; the JSON request is authoritative.
Do not force-push, do not merge the operator branch, do not discard local work, and do not use another repository unless the structured request explicitly authorizes it."

echo "TASK_ID=$task_id"
echo "TASK_BRANCH=$task_branch"
echo "REQUEST_PATH=$request_path"
echo "Launching Codex non-interactively..."

exec codex exec \
  --cd "$ROOT" \
  --sandbox workspace-write \
  --approve-for-me \
  --ephemeral \
  --color never \
  "$prompt"
