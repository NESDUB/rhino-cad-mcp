# Controller-Authored Payload Convention

This directory holds Rhino modeling payloads authored by the controller (ChatGPT Web).
Each task payload lives in `.bridge/payloads/<task-id>/` alongside its structured request.

## Role policy

**ChatGPT Web (controller)** is the normal author of Rhino Python modeling code.
The controller designs the geometry logic and commits the exact Python script that will run in Rhino.

**Local Claude (operator)** executes, validates, captures, saves, and reports.
Claude must not invent substitute geometry, redesign objects, or edit modeling code to make it work.
If a controller payload fails, Claude records the failure and returns it for correction.

**Local Codex (operator)** follows the same default as Claude.
Codex may author, repair, or alter Rhino modeling code only when the active structured request
explicitly contains `"local_modeling_authorized": true` or equivalent unambiguous authorization.
There is no implicit modeling authority from being Codex.

## Payload structure

Each task payload directory contains exactly two tracked files:

```
.bridge/payloads/<task-id>/
    rhino.py        The controller-authored Rhino Python (Python 3.9, RhinoCommon).
    manifest.json   Metadata and SHA-256 of rhino.py (see template).
```

Use `.bridge/templates/rhino-payload-manifest-v1.json` as the manifest template.

## Controller workflow

1. Author `rhino.py` locally or in the ChatGPT session.
2. Compute `sha256` of `rhino.py`: `sha256sum .bridge/payloads/<task-id>/rhino.py`
3. Write `manifest.json` with all required fields including the computed hash.
4. Commit both files alongside `.bridge/requests/<task-id>.json` to `main`.
5. The structured request should reference `payload_type: rhino_run` and include
   `"payload_path": ".bridge/payloads/<task-id>/rhino.py"` in its instructions if targeting
   is non-obvious.

## Operator execution

The operator uses `.bridge/run_rhino_payload.py` to execute the exact controller-authored payload:

```bash
# Dry-run (verify manifest, hash, Python 3.9 compat — no Rhino execution):
python3 .bridge/run_rhino_payload.py --task <task-id> --dry-run

# Live execution (Rhino must be running):
python3 .bridge/run_rhino_payload.py --task <task-id> --document-id PID:runtime_serial
```

The runner:
- Validates `manifest.json` schema and `task_id` match
- Recomputes and requires SHA-256 match — refuses to execute if payload was modified
- Requires `author_role=controller` — refuses to execute local-authored payloads
- Checks Python 3.9 compatibility via `tool_support.check_code`
- Requires `--document-id` when `target_document_required=true`
- Calls `bridge.execute()` with the exact verified code
- Prints the bridge result as JSON; exits nonzero on any failure

The operator must not patch the payload before running it. Any failure goes back to the controller
as a reportable blocker with the exact error evidence.

## Failure policy

A payload that fails validation, hash check, or Rhino execution is a blocker.
The operator records the failure in evidence and reports it through the normal branch/report flow.
The controller revises `rhino.py`, recomputes the hash, updates `manifest.json`, and commits a
corrected request. The operator does not silently fix controller code.

## Backward compatibility

Tasks that predate this convention (Phases 1–17) used direct `rhino_run` MCP tool calls.
Those tasks remain valid as-is. The payload convention applies to tasks that opt in by
committing a `payloads/<task-id>/` directory alongside the request.

## Example

`.bridge/payloads/_example/` is a non-mutating fixture (reads document metadata, no geometry
changes). Use it to validate the runner and toolchain:

```bash
python3 .bridge/run_rhino_payload.py --task _example --dry-run
```
