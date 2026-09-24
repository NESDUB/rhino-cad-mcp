# Local Operator Role Guide

Read `AI_ORIENTATION.md`, this guide, `CLAUDE.md`, `.bridge/protocol.json`, and the complete active request before substantive work. The request JSON is the authoritative contract for task scope, branch, challenge acknowledgement, outputs, and validation.

## Safe execution lifecycle

Start on clean `main`; inspect `git status --short --branch`; synchronize only with fast-forward behavior; then run `./exchange.sh prepare <task-id>`. Work only on the created `operator/<task-id>` branch. `./operator.sh` may initiate the normal one-command runner flow, but never substitutes for reading the request or validating the result.

Preserve all existing local work. A dirty worktree, branch mismatch, unexpected files, divergence, missing request, missing capability, or required safeguard conflict is a blocker: do not reset, clean, force-push, merge, or silently work around it. Record facts and hand the blocker back through the report/evidence path.

Keep protected runtime paths untouched unless the request specifically authorizes them. Do not imply a live Rhino session exists; when CAD work is authorized, comply with `CLAUDE.md`, inspect before modification, and validate geometry rather than trusting a script exit code.

## Modeling authority

The controller (ChatGPT Web) is the normal author of Rhino modeling Python. The operator's role
for geometry work is **execution, validation, capture, save, and reporting** — not design or authoring.

**Claude:** must not invent substitute geometry, redesign objects, or edit controller modeling code.
If a controller-authored payload (`bridge.payloads/<task-id>/rhino.py`) fails, record the failure
with exact error evidence and return it to the controller as a blocker. Do not silently patch.

**Codex:** same default. Codex may author, repair, or alter Rhino modeling code only when the active
structured request explicitly contains `local_modeling_authorized=true` or equivalent unambiguous
authorization. No implicit modeling authority from being Codex.

When a task provides a payload, execute it through `python3 .bridge/run_rhino_payload.py --task <task-id>
--document-id <id>` rather than copying the Python into an MCP call. The runner verifies the hash and
calls `bridge.execute()` with the exact controller-authored code.

**Multi-pass operator loop:** execute the exact payload → collect standardized evidence using the
`.bridge/templates/rhino-pass-evaluation-v1.json` schema → stop and hand back to the controller.
Do not author a next-pass payload. Do not redesign geometry to fix discrepancies you observe.
Discrepancies go into `objective_discrepancies` in the evidence packet with `operator_recommendation_scope="evidence_only"`.

## Completion contract

Run the exact required validations and proportional syntax/diff/schema checks. Create evidence that names commands, results, artifacts, and limitations. Commit implementation and evidence as the work commit and capture its SHA. Create the v0.3 report with the exact acknowledgement, base SHA, result SHA, required branch, tests, blockers, and controller notes; run `python3 .bridge/bridge_cli.py verify-report <task-id>` and require `REPORT_OK`; commit the report separately; push the operator branch normally. Never merge the branch yourself or force-push it.
