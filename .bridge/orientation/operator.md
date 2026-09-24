# Local Operator Role Guide

Read `AI_ORIENTATION.md`, this guide, `CLAUDE.md`, `.bridge/protocol.json`, and the complete active request before substantive work. The request JSON is the authoritative contract for task scope, branch, challenge acknowledgement, outputs, and validation.

## Safe execution lifecycle

Start on clean `main`; inspect `git status --short --branch`; synchronize only with fast-forward behavior; then run `./exchange.sh prepare <task-id>`. Work only on the created `operator/<task-id>` branch. `./operator.sh` may initiate the normal one-command runner flow, but never substitutes for reading the request or validating the result.

Preserve all existing local work. A dirty worktree, branch mismatch, unexpected files, divergence, missing request, missing capability, or required safeguard conflict is a blocker: do not reset, clean, force-push, merge, or silently work around it. Record facts and hand the blocker back through the report/evidence path.

Keep protected runtime paths untouched unless the request specifically authorizes them. Do not imply a live Rhino session exists; when CAD work is authorized, comply with `CLAUDE.md`, inspect before modification, and validate geometry rather than trusting a script exit code.

## Completion contract

Run the exact required validations and proportional syntax/diff/schema checks. Create evidence that names commands, results, artifacts, and limitations. Commit implementation and evidence as the work commit and capture its SHA. Create the v0.3 report with the exact acknowledgement, base SHA, result SHA, required branch, tests, blockers, and controller notes; run `python3 .bridge/bridge_cli.py verify-report <task-id>` and require `REPORT_OK`; commit the report separately; push the operator branch normally. Never merge the branch yourself or force-push it.
