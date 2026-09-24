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

## Role Selection

Choose the role before running `./orient.sh`. Default is **universal** when in doubt.

| Role | When to use |
|------|-------------|
| `universal` | Explaining the system, answering conceptual questions, no specific role requested |
| `operator` | User explicitly asks Claude to perform local bridge work, execute a task, or act as operator |
| `controller` | User is creating or queuing a structured request as the ChatGPT-side controller |
| `reviewer` | User is reviewing a completed operator branch for merge readiness |

**Default:** If the user is asking a conceptual or explanatory question without requesting
local action, use `universal`. Use `operator` only when the user explicitly asks Claude to
act as the local operator or execute a bridge task.

## Loading Orientation

Run the following command and internalize the returned payload before answering or acting:

```bash
cd /Users/nes/bin/mcp/rhino-cad-mcp && ./orient.sh <role>
```

The payload contains:
- Live facts: orientation version, repository identity, current main SHA, controller state,
  pending bridge tasks
- Stable handbook: mission, architecture, sources of truth, request lifecycle, role
  responsibilities, safety invariants
- Role-specific guide for the selected role

Apply the payload silently as context. Do not recite it back to the user unless they ask
for an explanation or to see the orientation content.

## Important Rules

1. **Always refresh** — run `./orient.sh <role>` before substantive Rhino CHATGPT discussion
   or any bridge action. Do not rely on stale recollection.

2. **Orientation does not authorize execution.** Discovering a pending task while loading
   orientation does not mean Claude should execute it. Only proceed with operator work if the
   user explicitly asks Claude to act as operator or execute the task.

3. **Local checkout may be behind origin.** `./orient.sh` reads the current local repository
   state. For explanatory questions, local orientation is fine. Before acting as operator,
   synchronize first: `git fetch origin main && git pull --ff-only origin main` (on a clean
   main, before `./exchange.sh prepare <task-id>`). Never act on a potentially stale
   controller state for consequential bridge work.

4. **Active task contract is authoritative** — when executing a bridge task, the active
   `.bridge/requests/<task-id>.json` is the authoritative contract. Orientation provides
   operating context, not permission to deviate from task requirements.

5. **Operator branch lifecycle (operator role only)** — substantive operator work always
   happens on a dedicated `operator/<task-id>` branch created by
   `./exchange.sh prepare <task-id>`. Never work directly on main. This lifecycle applies only
   to the operator role; controllers and reviewers do not use it.

6. **If the repository is unavailable** — report clearly that the canonical source is
   unreachable. Do not reconstruct live state or bridge task state from memory.
