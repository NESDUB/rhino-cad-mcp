#!/usr/bin/env bash
# install-claude-orientation.sh
# Idempotent installer: copies the canonical project skill into
# ~/.claude/skills/rhino-chatgpt-orientation/ and inserts a managed
# pointer block into ~/.claude/CLAUDE.md.
#
# Phase 12 baseline revealed that Claude Code 2.x does not load skills
# from ~/.claude/skills/ when the skill directory is a symlink. This
# installer was updated in Phase 13 to use a real managed file copy
# so that skill discovery works without relying on symlink resolution.
# The canonical project skill remains .claude/skills/rhino-chatgpt-orientation/SKILL.md;
# the personal copy is a managed duplicate that this installer keeps in sync.
#
# Usage: ./install-claude-orientation.sh [--uninstall]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_SKILL_DIR="$SCRIPT_DIR/.claude/skills/rhino-chatgpt-orientation"
PROJECT_SKILL_FILE="$PROJECT_SKILL_DIR/SKILL.md"
GLOBAL_SKILLS_DIR="$HOME/.claude/skills"
PERSONAL_SKILL_DIR="$GLOBAL_SKILLS_DIR/rhino-chatgpt-orientation"
PERSONAL_SKILL_FILE="$PERSONAL_SKILL_DIR/SKILL.md"
MANAGED_MARKER_FILE="$PERSONAL_SKILL_DIR/.managed-by-install-claude-orientation"
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

  # Remove managed personal skill directory (only if this installer owns it)
  if [[ -d "$PERSONAL_SKILL_DIR" ]]; then
    if [[ -f "$MANAGED_MARKER_FILE" ]]; then
      rm -rf "$PERSONAL_SKILL_DIR"
      echo "REMOVED managed personal skill dir: $PERSONAL_SKILL_DIR"
    else
      echo "SKIP: $PERSONAL_SKILL_DIR exists but was not created by this installer (no marker file). Not removing."
    fi
  elif [[ -L "$PERSONAL_SKILL_DIR" ]]; then
    # Legacy: remove old symlink if present
    rm "$PERSONAL_SKILL_DIR"
    echo "REMOVED legacy symlink: $PERSONAL_SKILL_DIR"
  else
    echo "OK: no managed skill at $PERSONAL_SKILL_DIR"
  fi

  # Remove managed block from CLAUDE.md
  if [[ -f "$GLOBAL_CLAUDE_MD" ]]; then
    if grep -qF "$MANAGED_BLOCK_START" "$GLOBAL_CLAUDE_MD"; then
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

# Verify canonical project skill exists
if [[ ! -f "$PROJECT_SKILL_FILE" ]]; then
  echo "ERROR: canonical project skill not found at $PROJECT_SKILL_FILE" >&2
  exit 1
fi
echo "OK: canonical project skill found at $PROJECT_SKILL_FILE"

# Create ~/.claude/skills if needed
if [[ ! -d "$GLOBAL_SKILLS_DIR" ]]; then
  mkdir -p "$GLOBAL_SKILLS_DIR"
  echo "CREATED: $GLOBAL_SKILLS_DIR"
else
  echo "OK: $GLOBAL_SKILLS_DIR exists"
fi

# Remove legacy symlink if present (Phase 11 installer created a symlink;
# Phase 13 replaces it with a real directory copy)
if [[ -L "$PERSONAL_SKILL_DIR" ]]; then
  echo "MIGRATE: removing legacy symlink at $PERSONAL_SKILL_DIR"
  rm "$PERSONAL_SKILL_DIR"
  echo "REMOVED legacy symlink"
fi

# Conflict check: if a real unmanaged directory exists, stop
if [[ -d "$PERSONAL_SKILL_DIR" && ! -f "$MANAGED_MARKER_FILE" ]]; then
  echo "CONFLICT: $PERSONAL_SKILL_DIR exists and is not managed by this installer." >&2
  echo "  Remove or rename it, then re-run this installer." >&2
  exit 1
fi

# Create managed personal skill directory
mkdir -p "$PERSONAL_SKILL_DIR"

# Copy SKILL.md from canonical source
cp "$PROJECT_SKILL_FILE" "$PERSONAL_SKILL_FILE"
echo "COPIED: $PROJECT_SKILL_FILE -> $PERSONAL_SKILL_FILE"

# Write managed marker
printf 'Managed by install-claude-orientation.sh\nCanonical source: %s\n' "$PROJECT_SKILL_FILE" > "$MANAGED_MARKER_FILE"

# Verify copy is byte-for-byte identical
if cmp -s "$PROJECT_SKILL_FILE" "$PERSONAL_SKILL_FILE"; then
  echo "OK: personal SKILL.md matches canonical source (byte-for-byte)"
else
  echo "ERROR: copy verification failed — SKILL.md does not match canonical source" >&2
  exit 1
fi
echo "OK: personal skill installed at $PERSONAL_SKILL_FILE"

# Insert managed block into ~/.claude/CLAUDE.md (idempotent)
if [[ ! -f "$GLOBAL_CLAUDE_MD" ]]; then
  echo "WARNING: $GLOBAL_CLAUDE_MD does not exist; creating with managed block only." >&2
  printf '%s\n' "$MANAGED_BLOCK" > "$GLOBAL_CLAUDE_MD"
  echo "CREATED: $GLOBAL_CLAUDE_MD with managed block"
elif grep -qF "$MANAGED_BLOCK_START" "$GLOBAL_CLAUDE_MD"; then
  echo "OK: managed block already present in $GLOBAL_CLAUDE_MD (idempotent, no change)"
else
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
echo "Personal skill: $PERSONAL_SKILL_FILE"
echo "Canonical source: $PROJECT_SKILL_FILE"
echo ""
echo "NOTE: A Claude Code session restart is required for the new skill to become"
echo "available. This is standard Claude Code behavior for newly installed skills."
