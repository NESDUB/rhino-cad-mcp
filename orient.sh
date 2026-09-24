#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
  cat <<'USAGE'
Usage: ./orient.sh [controller|operator|reviewer|universal] [--copy] [--copy-only]

Build a self-contained AI orientation payload. The default role is universal.
--copy copies the payload with macOS pbcopy when available and also prints it.
--copy-only copies the payload and suppresses stdout; it fails if pbcopy is unavailable.
USAGE
}

role="universal"
copy_mode="none"
role_seen=0

for argument in "$@"; do
  case "$argument" in
    controller|operator|reviewer|universal)
      if [[ "$role_seen" -eq 1 ]]; then
        echo "ERROR: only one role may be specified." >&2
        usage >&2
        exit 64
      fi
      role="$argument"
      role_seen=1
      ;;
    --copy)
      [[ "$copy_mode" == "none" ]] || { echo "ERROR: choose only one copy option." >&2; exit 64; }
      copy_mode="copy"
      ;;
    --copy-only)
      [[ "$copy_mode" == "none" ]] || { echo "ERROR: choose only one copy option." >&2; exit 64; }
      copy_mode="copy-only"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unsupported argument: $argument" >&2
      usage >&2
      exit 64
      ;;
  esac
done

payload="$(python3 .bridge/orientation/build_payload.py "$role")"

if [[ "$copy_mode" != "none" ]]; then
  if ! command -v pbcopy >/dev/null 2>&1; then
    echo "ERROR: pbcopy is unavailable; cannot satisfy $copy_mode." >&2
    exit 69
  fi
  printf '%s' "$payload" | pbcopy
fi

if [[ "$copy_mode" != "copy-only" ]]; then
  printf '%s\n' "$payload"
fi
