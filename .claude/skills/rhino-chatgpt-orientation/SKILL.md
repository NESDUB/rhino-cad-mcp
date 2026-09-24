---
name: rhino-chatgpt-orientation
description: >
  Load the canonical Rhino CHATGPT orientation system for the NESDUB/rhino-cad-mcp Git bridge.
  Invoke when the user mentions Rhino CHATGPT, rhino-cad-mcp, the Rhino bridge, the GitHub
  controller/operator bridge, orientation or onboarding for this system, operator.sh,
  exchange.sh, structured bridge requests, controller/operator/reviewer roles, asks Claude to
  remember or recall how the system works, or asks to load/orient context on this bridge.
  Use PROACTIVELY whenever these topics arise. Do not reconstruct bridge state from memory —
  always fetch fresh canonical orientation.
---

# Rhino CHATGPT Orientation

## What This Skill Does

This skill loads fresh canonical orientation context for the Rhino CHATGPT Git bridge
(`NESDUB/rhino-cad-mcp`). It does not duplicate the handbook — it locates and runs the
canonical source.

**Canonical repository path:** `/Users/nes/bin/mcp/rhino-cad-mcp`

## Usage

When invoked, determine the appropriate role from the user's request:

- **operator** — default for a local Claude Code coding session performing bridge work
- **controller** — if the user is acting as the ChatGPT-side controller queuing requests
- **reviewer** — if the user is reviewing a completed operator branch
- **universal** — if no specific role is clear

## Loading Orientation

Run the following command and apply the returned payload before answering or acting:

```bash
cd /Users/nes/bin/mcp/rhino-cad-mcp && ./orient.sh <role>
```

Example for the default operator role:

```bash
cd /Users/nes/bin/mcp/rhino-cad-mcp && ./orient.sh operator
```

The payload contains:
- Live facts: orientation version, repository identity, current main SHA, controller state,
  pending bridge tasks
- Stable handbook: mission, architecture, sources of truth, request lifecycle, role
  responsibilities, safety invariants
- Role-specific guide for the selected role

## Important Rules

1. **Always refresh** — run `./orient.sh <role>` before answering substantive bridge questions.
   Do not rely on stale recollection.

2. **If the repository is unavailable** — report clearly that the canonical source is
   unreachable. Do not reconstruct live state or bridge task state from memory.

3. **Active task contract is authoritative** — if `.bridge/requests/<task-id>.json` exists for
   an in-progress task, that JSON is the authoritative task contract. Orientation provides
   operating context, not permission to deviate from task requirements.

4. **Branch safety** — substantive bridge work always happens on a dedicated
   `operator/<task-id>` branch created by `./exchange.sh prepare <task-id>`. Never work
   directly on main.
