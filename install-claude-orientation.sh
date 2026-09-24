#!/usr/bin/env bash
# install-claude-orientation.sh
# Idempotent installer: creates ~/.claude/skills/rhino-chatgpt-orientation symlink and
# inserts a managed pointer block into ~/.claude/CLAUDE.md.
# Usage: ./install-claude-orientation.sh [--uninstall]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_SKILL_DIR="$SCRIPT_DIR/.claude/skills/rhino-chatgpt-orientation"
GLOBAL_SKILLS_DIR="$HOME/.claude/skills"
SYMLINK_PATH="$GLOBAL_SKILLS_DIR/rhino-chatgpt-orientation"
GLOBAL_CLAUDE_MD="$HOME/.claude/CLAUDE.md"

MANAGED_BLOCK_START="<!-- BEGIN RHINO-CHATGPT-ORIENTATION MANAGED BLOCK -->"
MANAGED_BLOCK_END="<!-- END RHINO-CHATGPT-ORIENTATION MANAGED BLOCK -->"

MANAGED_BLOCK="$MANAGED_BLOCK_START
# Rhino CHATGPT Bridge — Orientation Skill Pointer

When the user mentions Rhino CHATGPT, rhino-cad-mcp, the Rhino bridge, operator.sh,
exchange.sh, structured bridge requests, controller/operator/reviewer roles, or asks to
recall/load/orient on that system, invoke the **rhino-chatgpt-orientation** skill before
answering or acting. Prefer fresh canonical orientation (./orient.sh) over memory.
Canonical repository: /Users/nes/bin/mcp/rhino-cad-mcp
$MANAGED_BLOCK_END"

uninstall_mode=0
for arg in "$@"; do
  case "$arg" in
    --uninstall) uninstall_mode=1 ;;
    *) echo "ERROR: unknown argument: $arg" >&2; exit 64 ;;
  esac
done

# ── Uninstall ──────────────────────────────────────────────────────────────────
if [[ "$uninstall_mode" -eq 1 ]]; then
  echo "--- Uninstall mode ---"

  # Remove symlink only (never remove a real directory)
  if [[ -L "$SYMLINK_PATH" ]]; then
    rm "$SYMLINK_PATH"
    echo "REMOVED symlink: $SYMLINK_PATH"
  elif [[ -e "$SYMLINK_PATH" ]]; then
    echo "SKIP: $SYMLINK_PATH exists but is not a symlink; not removing."
  else
    echo "OK: no symlink at $SYMLINK_PATH"
  fi

  # Remove managed block from CLAUDE.md
  if [[ -f "$GLOBAL_CLAUDE_MD" ]]; then
    if grep -qF "$MANAGED_BLOCK_START" "$GLOBAL_CLAUDE_MD"; then
      # Use Python for safe multi-line removal
      python3 - "$GLOBAL_CLAUDE_MD" "$MANAGED_BLOCK_START" "$MANAGED_BLOCK_END" <<'PYEOF'
import sys, re, pathlib
path, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
text = pathlib.Path(path).read_text()
pattern = re.compile(
    r'\n?' + re.escape(start) + r'.*?' + re.escape(end) + r'\n?',
    re.DOTALL
)
new_text = pattern.sub('', text)
pathlib.Path(path).write_text(new_text)
print(f"REMOVED managed block from {path}")
PYEOF
    else
      echo "OK: no managed block found in $GLOBAL_CLAUDE_MD"
    fi
  fi

  echo "Uninstall complete."
  exit 0
fi

# ── Install ────────────────────────────────────────────────────────────────────
echo "--- Install mode ---"

# Verify project skill exists
if [[ ! -f "$PROJECT_SKILL_DIR/SKILL.md" ]]; then
  echo "ERROR: project skill not found at $PROJECT_SKILL_DIR/SKILL.md" >&2
  exit 1
fi
echo "OK: project skill found at $PROJECT_SKILL_DIR/SKILL.md"

# Create ~/.claude/skills if needed
if [[ ! -d "$GLOBAL_SKILLS_DIR" ]]; then
  mkdir -p "$GLOBAL_SKILLS_DIR"
  echo "CREATED: $GLOBAL_SKILLS_DIR"
else
  echo "OK: $GLOBAL_SKILLS_DIR exists"
fi

# Create or repair symlink
if [[ -L "$SYMLINK_PATH" ]]; then
  current_target="$(readlink "$SYMLINK_PATH")"
  if [[ "$current_target" == "$PROJECT_SKILL_DIR" ]]; then
    echo "OK: symlink already correct: $SYMLINK_PATH -> $PROJECT_SKILL_DIR"
  else
    echo "REPAIR: updating symlink from $current_target to $PROJECT_SKILL_DIR"
    rm "$SYMLINK_PATH"
    ln -s "$PROJECT_SKILL_DIR" "$SYMLINK_PATH"
    echo "CREATED: $SYMLINK_PATH -> $PROJECT_SKILL_DIR"
  fi
elif [[ -e "$SYMLINK_PATH" ]]; then
  echo "CONFLICT: $SYMLINK_PATH exists and is not a symlink. Manual resolution required." >&2
  echo "  Remove or rename it, then re-run this installer." >&2
  exit 1
else
  ln -s "$PROJECT_SKILL_DIR" "$SYMLINK_PATH"
  echo "CREATED: $SYMLINK_PATH -> $PROJECT_SKILL_DIR"
fi

# Verify symlink resolves
resolved="$(readlink -f "$SYMLINK_PATH" 2>/dev/null)" || true
if [[ "$resolved" == "$PROJECT_SKILL_DIR" ]]; then
  echo "OK: symlink resolves correctly to $resolved"
else
  echo "WARNING: symlink target may not resolve as expected. Resolved to: $resolved"
fi

# Insert managed block into ~/.claude/CLAUDE.md (idempotent)
if [[ ! -f "$GLOBAL_CLAUDE_MD" ]]; then
  echo "WARNING: $GLOBAL_CLAUDE_MD does not exist; creating with managed block only." >&2
  printf '%s\n' "$MANAGED_BLOCK" > "$GLOBAL_CLAUDE_MD"
  echo "CREATED: $GLOBAL_CLAUDE_MD with managed block"
elif grep -qF "$MANAGED_BLOCK_START" "$GLOBAL_CLAUDE_MD"; then
  echo "OK: managed block already present in $GLOBAL_CLAUDE_MD (idempotent, no change)"
else
  # Append with a blank line separator
  printf '\n%s\n' "$MANAGED_BLOCK" >> "$GLOBAL_CLAUDE_MD"
  echo "APPENDED: managed block to $GLOBAL_CLAUDE_MD"
fi

# Verify exactly one managed block
block_count="$(grep -cF "$MANAGED_BLOCK_START" "$GLOBAL_CLAUDE_MD")"
if [[ "$block_count" -eq 1 ]]; then
  echo "OK: exactly 1 managed block in $GLOBAL_CLAUDE_MD"
else
  echo "WARNING: found $block_count managed block(s) in $GLOBAL_CLAUDE_MD — expected exactly 1"
fi

echo ""
echo "Install complete."
echo ""
echo "NOTE: A Claude Code session restart may be required for the new skill to appear in"
echo "the session's skill list. The skill is immediately available to any new session."
