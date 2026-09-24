# Agent Bootstrap

Before substantive work, read `AI_ORIENTATION.md` and `.bridge/orientation/operator.md`. Then read the active structured request, `.bridge/protocol.json`, and all applicable project-specific safety rules, especially `CLAUDE.md` for Rhino CAD work.

Treat request JSON as authoritative for active task scope. Preserve local work, use the required operator branch lifecycle, validate before push, and do not bypass Git, Rhino, or repository safeguards.

**Modeling authority:** ChatGPT Web is the normal author of Rhino Python. Local AI (Claude or Codex) executes, validates, captures, and reports. Local modeling is only authorized when the active structured request explicitly grants it. For tasks with a controller payload in `.bridge/payloads/<task-id>/`, use `python3 .bridge/run_rhino_payload.py` rather than rewriting the script.
