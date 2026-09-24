# Operator Experience — bridge-phase12-001

**Role:** Claude Code acting as local operator  
**Model:** claude-sonnet-4-6  
**Date:** 2026-09-24  
**Outcome:** Partially demonstrated. Blocked at MCP Discovery (Stage 7 of ~16).

---

## What Felt Smooth

**The Git bridge portion worked without friction.** From the moment `git fetch` ran through `./exchange.sh prepare bridge-phase12-001`, every step was deterministic and fast. The request JSON is a well-structured contract — I knew exactly what I was supposed to do, what the expected outputs were, and what I was not allowed to touch. That clarity is genuinely valuable; it means the operator can't accidentally drift into scope creep.

**orient.sh is solid.** The payload is cleanly separated into stable handbook content and live-generated facts. Reading it feels like getting a proper briefing rather than guessing at system state. The separation of handbook (stable) from live facts (generated) is the right design.

**The task constraint language is precise.** "Do not fix anything during the run. Record kinks instead." That instruction was easy to follow and kept me from second-guessing whether I should be solving the blocker I found. A baseline run needs that discipline.

---

## What Was Awkward

**The rhino-chatgpt-orientation skill didn't load.** This was the first thing I tried. The skill was installed by the previous session, the session was restarted, and the skill still wasn't available. I had to fall back to `./orient.sh operator` manually — which works fine, but the skill is supposed to be the "institutional memory" entry point for a fresh Claude session. A new Claude session that doesn't know about `./orient.sh` would stall here.

The deeper issue: `~/.claude/skills/` contains symlinks, but it's unclear whether Claude Code actually discovers skills from that directory. The other symlinks in that folder (`article-extractor`, `swiftui-liquid-glass`, etc.) all point to `../../.agents/skills/...` which are also dangling. The entire `~/.claude/skills/` pattern may not be a working Claude Code feature — it may be an artifact of a different tool's convention.

**The rhino-cad MCP server is not registered anywhere.** This was the hard stop. The server exists, is fully implemented, the mcp package is available, Rhino might well be running — but Claude has no way to reach any of it. `ToolSearch` found nothing. This isn't a runtime error; it's a missing configuration artifact. The server was never added to `~/.claude.json` and there's no project `.mcp.json`. Every Rhino operation — status check, document creation, CAD work, validation, capture, save — was unreachable.

The frustrating part is that this is invisible to the operator until they actively search for the tools. If I hadn't used `ToolSearch` explicitly, I might have written a `rhino_status()` call and only discovered the problem when it returned an error. The orientation system, the request JSON, the handbook — none of them surface "by the way, the MCP server isn't registered" as a precondition. It's assumed.

---

## What Required Reasoning That Should Have Been Automated

**Knowing to check `~/.claude.json` for MCP registration.** The operator should not need to know the global Claude config format to discover that a server is missing. A preflight step in `exchange.sh prepare` or a dedicated `./preflight.sh` that checks MCP registration for the relevant server would catch this in 2 seconds with zero operator judgment required.

**Determining whether a skill installation worked.** After `install-claude-orientation.sh` ran, there was no way to verify the skill was actually discoverable short of trying to invoke it. The installer correctly noted a restart was required; the restart happened; the skill still didn't work. The diagnostic path from there is: check symlink targets, compare with other known-working skill paths, read Claude Code docs on skill discovery. That's several minutes of reasoning that a `./check-skill.sh` script could automate.

**Choosing between session-level and project-level MCP registration.** The request asks for a project `.mcp.json` as the right fix (MR1). That's the correct call — but the reasoning about *why* project-level is better than global-level required understanding the Claude Code configuration hierarchy. New operators won't know this.

---

## What Required Manual Intervention

1. **Session restart** — performed by the user after skill installation failed. Required because skill loading happens at session start. The restart didn't solve the underlying problem.

2. **Switching branches before pulling** — the session started on `operator/bridge-phase11-001`. A manual `git checkout main` was required before the sync step. This should always be the operator's first action but isn't documented as such in the operator guide.

---

## Top Five Workflow Improvements (Ranked by Impact)

1. **Register the rhino-cad MCP server** (QW1 / MR1)  
   Without this, no Rhino work is possible. Everything else is moot. Add a project `.mcp.json` with the server entry point. Five minutes of work, unlocks the entire Rhino half of the system.

2. **Fix the skill discovery path** (QW2)  
   The orientation skill is the right architectural idea — a lightweight "where to look" pointer that loads fresh context on demand. But it needs to actually work. Investigate whether Claude Code scans `~/.claude/skills/` and under what conditions. If that path doesn't work, the canonical alternative is a project-level skill (which the SKILL.md already is) and the personal symlink approach needs a rethink.

3. **Add MCP registration check to exchange.sh prepare or a preflight script** (PC3)  
   Before the operator starts any Rhino task, a one-line `grep 'rhino-cad' ~/.claude.json` check (or `cat .mcp.json`) would immediately surface missing registrations. This moves the failure from "buried in a ToolSearch query midway through the session" to "first thing you see when preparing the branch."

4. **Add a "next action" hint to bridge_cli.py status** (PC1)  
   Right now `bridge_cli.py status` tells you there's a pending task. It could also print: `Next: ./exchange.sh prepare bridge-phase12-001`. The operator already knows this, but a fresh Claude session benefits from explicit next-step prompts, and it costs nothing.

5. **Add a staleness warning to orient.sh** (QW3)  
   A simple `git fetch --dry-run` check before generating the payload, with a warning if local main is behind origin, prevents the orient-then-act-on-stale-state failure mode. It's a short bash addition to orient.sh and doesn't change the payload format.

---

## Overall Assessment

The Git bridge half of the system works well. The controller-to-request-to-operator handoff is clean, the request JSON is a usable contract, and the exchange workflow is solid. The architecture is correct.

The Rhino half has never been connected in this Claude Code context. The MCP registration gap means the entire CAD, validation, and artifact pipeline is theoretical until QW1/MR1 is addressed.

Once the server is registered and Rhino connectivity is confirmed, the most interesting unknowns will be: does `rhino_create_document` reliably isolate from the user's existing work, what does `rhinocode` error handling look like under real conditions, and how does the capture/save pipeline behave with real file paths? Those are the questions for the next POC run.
