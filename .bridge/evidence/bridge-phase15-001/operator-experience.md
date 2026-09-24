# Operator Experience — bridge-phase15-001

**Role:** Claude Code acting as local operator  
**Model:** claude-sonnet-4-6 (v2.1.100)  
**Date:** 2026-09-24  
**Outcome:** Partial — blocked at MCP tool session visibility (Stage 7). New blocker; different from Phase 12.

---

## What Felt Smooth

The **orientation skill finally worked**. Instead of the Phase 12 fallback to `./orient.sh` manually, `/rhino-chatgpt-orientation` invoked correctly and the skill loaded from the real file copy. That's a real improvement. A fresh Claude session opened in any directory now gets a working orientation entry point.

The **Git bridge half is clean**. Sync, request discovery, branch prep — same reliable flow as Phase 12. No friction there.

The **server registration is real**. `claude mcp get rhino-cad` reports `Status: ✓ Connected`, which means the Phase 14 import fix worked and the server starts correctly. That's Phase 12 F1a + F1b both resolved.

---

## What Was Awkward

**The "Connected" status is a lie in practice.** Or rather, it's misleading. I saw `claude mcp get rhino-cad → Status: ✓ Connected` and expected tools to be callable. They weren't. The CLI checks whether the server *process* can start — not whether the session has the tools registered. An operator who checks `claude mcp get`, sees Connected, and proceeds to call `rhino_status` is going to get a confusing error with no obvious explanation.

**The session-directory rule for project `.mcp.json` is invisible.** The `.mcp.json` file is committed to the repo, registered, and the server starts. But the tools only appear in a session that was started from (or below) the project root. There is nowhere in the operator guide, CLAUDE.md, AGENTS.md, the orient.sh output, or the exchange.sh output that mentions this. An operator who starts Claude from their home directory — which is the natural thing to do — will hit this every time.

This is actually a more frustrating blocker than the Phase 12 import error, because the Phase 12 error had a clear error message (`ModuleNotFoundError`). This one has no error at all — you just don't see the tools, and the Connected status implies everything is fine.

---

## What Required Reasoning That Should Have Been Automated

**Distinguishing "CLI Connected" from "session tools available."** The operator has to know these are two different states. The fix is either: (a) add rhino-cad to the global `~/.claude.json` config so it loads in every session, or (b) document the session-directory requirement prominently. Option (a) is a 5-minute one-liner that eliminates the problem permanently.

**Knowing to use `ListMcpResourcesTool` to confirm session tool registration.** `ToolSearch` returned zero results. A less systematic operator might have tried to call `rhino_status` directly and received an opaque failure. The correct diagnostic — `ListMcpResourcesTool` to compare available server names — requires knowing that tool exists and what it tests.

---

## What Required Manual Intervention

None in this run. The session-directory blocker was identified through diagnostics without user intervention. The earlier "start on previous branch" issue was handled by `git checkout main` at the start of the sync step.

---

## Top Five Workflow Improvements (Ranked by Impact)

1. **Add rhino-cad to global `~/.claude.json` MCP config** (QW1 / MR1)  
   `claude mcp add --scope user rhino-cad -- /Users/nes/.pyenv/versions/3.12.0/bin/python3 /Users/nes/bin/mcp/rhino-cad-mcp/server.py`  
   Five minutes. Eliminates the session-directory requirement permanently. The next POC run from any directory will have the tools.

2. **Document the session start prerequisite** (QW2)  
   Add one line to operator.md and AGENTS.md: start Claude from the project root, or use global MCP config. This is a one-time documentation fix that prevents every future operator from burning 10 minutes diagnosing the same invisible blocker.

3. **Add a session-scope MCP check to exchange.sh prepare** (PC1)  
   After branch setup, check whether rhino-cad is in the session's active server list. Emit a clear warning — or fail fast — before the operator invests in the Rhino path. The error should say "rhino-cad not in session: start Claude from the project directory or add it to global config."

4. **Clarify `claude mcp get` Connected semantics** (PC2)  
   Either update the CLI output to distinguish "process reachable" from "tools registered in session", or add a note to operator documentation. The Connected/Failed distinction currently hides a second failure mode that is just as blocking.

5. **Add a preflight gate to orient.sh operator output** (from Phase 12 QW3, still relevant)  
   orient.sh should check whether local main is behind origin and warn. This was identified in Phase 12; it remains valid as a safety net for operators who load orientation before pulling.

---

## Overall Assessment

Three POC runs in, the Git bridge portion has been clean every time. The orientation skill is now working. The server starts correctly. The only thing standing between "running the bridge" and "running Rhino" is one `claude mcp add --scope user` command.

Each POC run has peeled one layer: Phase 12 found the server wasn't registered. Phase 13/14 fixed registration and the import. Phase 15 found that project-scope registration requires the right session directory. Phase 16 should fix that with a global registration, and then the next run will either reach Rhino or find the next layer.

The instrumentation discipline is paying off. Every blocker found has been concrete, specific, and fixable. None have required rearchitecting anything.
