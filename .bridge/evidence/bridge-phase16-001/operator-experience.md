# Operator Experience — bridge-phase16-001

**Role:** Claude Code acting as local operator  
**Model:** claude-sonnet-4-6 (v2.1.100)  
**Date:** 2026-09-24  
**Outcome:** Partial — blocked at MCP tool session visibility (Stage 6). New sub-blocker; distinct from Phase 15.

---

## What Felt Smooth

The **Git bridge is reliable and fast**. Sync, request discovery, branch prep — same clean execution as every prior phase. `exchange.sh prepare` is well-designed: it validates the request, creates the branch atomically, and produces a clear BASE_COMMIT. No friction here.

The **orientation skill continues to work**. The managed CLAUDE.md block triggers the skill correctly. The skill loads from the real file copy at `~/.claude/skills/rhino-chatgpt-orientation/SKILL.md`. Phase 13 fix holds.

The **user-scope MCP entry is correctly applied**. Direct inspection of `~/.claude.json` confirms the `rhino-cad` entry under `mcpServers` exactly as expected. `claude mcp get` reports Connected. The Phase 15 fix was applied correctly and is durable.

---

## What Was Awkward

**The same invisible blocker, again, in a new form.** The Phase 15 fix was: add rhino-cad to user-scope `~/.claude.json`. That fix was applied. The entry is there. The server is Connected. But the tools are still not in the session.

The new layer: Claude Code reads `~/.claude.json` at session startup only. This session is a context-compaction continuation of the session that predates the user-scope registration. Compaction does not trigger a config re-read. The session's MCP server list was frozen at the original startup time — before the entry was written.

The experience from inside the session is identical to Phase 15: `ToolSearch` returns 0 results, `ListMcpResourcesTool` reports `rhino-cad` not found. There is no error, no warning, no indication that anything is wrong with the config. The Connected status from the CLI looks correct. Everything looks fine — and nothing works.

**The scope display added confusion.** Running `claude mcp get rhino-cad` inside the project directory shows `Scope: Project config (shared via .mcp.json)`, not the user-scope entry. An operator who applied the user-scope fix and then runs this check to confirm it might conclude the fix didn't apply — when in fact both entries exist and the display is just prioritizing the project-scope entry. I needed a direct JSON parse of `~/.claude.json` to confirm the user-scope entry is actually there.

---

## What Required Reasoning That Should Have Been Automated

**Identifying "context-compaction continuation" as a distinct session type.** The session summary explicitly noted this was a continuation after context compaction. A systematic operator would flag this immediately: if the session predates the user-scope fix, the fix cannot have taken effect in this session. This reasoning step is non-obvious and was not automated anywhere in the bridge tooling.

**Distinguishing three connected-but-different states:**
1. `rhino-cad` entry in `~/.claude.json` (config presence) — ✓
2. `claude mcp get` Connected status (server process reachability) — ✓
3. `rhino-cad` in session's active server list (tool callability) — ✗

All three look like the same thing but test different layers. A session could have 1+2 but not 3, which is exactly the state we're in. No single CLI check surfaces all three simultaneously.

---

## What Required Manual Intervention

None in this run. The blocker was identified through diagnostics without user intervention. The `~/.claude.json` direct parse was necessary to disambiguate the scope display issue.

---

## Top Five Workflow Improvements (Ranked by Impact)

1. **Full quit-and-relaunch of Claude Code (immediate, required for Phase 17)**  
   The user-scope entry is correct. The next session must be a fully fresh start — not a compaction continuation, not a new conversation window in the same application instance. After relaunch, verify with `ListMcpResourcesTool server=rhino-cad` before starting any bridge work. This is the only remaining step between "configuration correct" and "tools in session".

2. **Add a session-scope MCP check as a preflight gate in exchange.sh prepare** (PC1)  
   Before reporting REQUEST_OK, exchange.sh prepare should verify rhino-cad is in the session's active server list. If absent, print a clear failure: "rhino-cad not in session — quit and relaunch Claude Code before proceeding." This would have caught the blocker at Stage 4 rather than Stage 6, before branch creation.

3. **Document the quit-and-relaunch requirement explicitly** (QW2)  
   Add to operator.md and AGENTS.md: MCP config changes require a full application restart. Context compaction and new conversation windows do not re-read the config. This is a non-obvious rule that has now caused three consecutive POC runs to block at MCP visibility.

4. **Add session-scope MCP status to orient.sh operator output** (PC2)  
   One line in the preflight section: `rhino-cad: IN SESSION (32 tools)` or `rhino-cad: NOT IN SESSION`. This would be the first thing an operator sees on each run, making the session-scope gap visible before any branch work begins.

5. **Clarify claude mcp get scope display when multiple scopes coexist** (PC3)  
   Document that project scope takes display priority over user scope when CWD is inside the project root. Operators who want to confirm user-scope registration should either parse `~/.claude.json` directly or run the check from outside the project directory.

---

## Overall Assessment

Four POC phases in. The Git bridge is clean every time. The orientation skill works. The server starts correctly. The user-scope registration is applied correctly. The only remaining obstacle is a full application restart to load the new entry into an active session.

The pattern across phases: Phase 12 — server not registered. Phase 13/14 — registration fixed, server import fixed. Phase 15 — project scope requires session to start from project dir. Phase 16 — user-scope entry written after session start (or into a continued session); requires quit-and-relaunch.

Each phase has found a concrete, fixable blocker. None has required rearchitecting anything. Phase 17 should be the live Rhino POC — assuming the session is a fresh start after full relaunch with Rhino 8 already running.

The instrumentation discipline is holding. The operator can now diagnose each failure layer precisely and distinguish config presence, CLI connectivity, and session-scope tool registration as three separate checkpoints.
