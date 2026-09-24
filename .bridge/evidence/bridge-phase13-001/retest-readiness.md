# Retest Readiness — bridge-phase13-001

**Assessment date:** 2026-09-24  
**For:** Phase 12 full Rhino workflow POC rerun

---

## GO / NO-GO: **NO-GO** (one action required)

The Phase 12 POC cannot be rerun successfully in its current state.  
**One blocking action is needed before retest.**

---

## Status of the Two Phase 12 High-Severity Blockers

### F1 — rhino-cad MCP server registration

| Sub-issue | Status |
|-----------|--------|
| F1a: server not registered | **FIXED** — `.mcp.json` created at project root; `claude mcp get rhino-cad` confirms project-scope registration |
| F1b: server.py broken import | **BLOCKED** — `from mcp.server.mcpserver import MCPServer as FastMCP` fails at startup; `mcp.server.mcpserver` does not exist in mcp 1.27.0 |

**Action required before retest:**  
Change server.py line 6:
```python
# Current (broken):
from mcp.server.mcpserver import MCPServer as FastMCP

# Fix:
from mcp.server.fastmcp import FastMCP
```
This is a 1-line change. The pre-enhancement backup (`backups/pre-enhancements-20260920/server.py`) uses the correct import. The fix was introduced during the 2026-09-20 enhancements and has been present ever since. Phase 13 constraints protect server.py; a controller-authorized amendment or a dedicated Phase 13.1 is needed.

### F2 — rhino-chatgpt-orientation skill not discoverable

**Status: FIXED**

- Root cause confirmed: Claude Code 2.x does not follow directory symlinks when scanning `~/.claude/skills/`. Real file copies are required.
- `install-claude-orientation.sh` updated to create a managed real-directory copy at `~/.claude/skills/rhino-chatgpt-orientation/SKILL.md`.
- Skill appeared in the current session's skill list without a restart after install.
- Idempotency verified (two consecutive runs).
- Byte-for-byte match between canonical and personal copy confirmed.

---

## GO Conditions

The Phase 12 POC rerun is GO when **all** of the following are true:

1. `server.py` line 6 is fixed to `from mcp.server.fastmcp import FastMCP`
2. `/Users/nes/.pyenv/versions/3.12.0/bin/python3 server.py` starts without import error (produces MCP stdio output)
3. `claude mcp get rhino-cad` shows `Status: Connected` (not `Failed to connect`)
4. Rhino 8 is running and accessible via rhinocode on the local machine
5. Session opened in `/Users/nes/bin/mcp/rhino-cad-mcp` or from any directory with `~/.claude/skills/rhino-chatgpt-orientation/SKILL.md` installed (currently true)

Conditions 1–3 depend on the server.py fix. Conditions 4–5 are operator environment prerequisites.

---

## What a Rerun Will Now Test for the First Time

Once the server.py import is fixed:

- Does `rhino_status` correctly report Rhino running/not running?
- Does `rhino_create_document` safely isolate from the user's existing documents?
- Does `rhino_run` execute RhinoCommon Python cleanly for deterministic geometry?
- Do `rhino_validate` and `rhino_validate_assembly` produce useful structured output?
- Does `rhino_capture_viewport` produce a PNG and what path does it write to?
- Does `rhino_save_as` work without overwriting existing files?
- Do tool schemas match what server.py defines (any surprises in Claude's tool picker)?

These are the genuine next-layer unknowns. The infrastructure questions are now answered.
