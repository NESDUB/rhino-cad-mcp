# Controller Role Guide

Read `AI_ORIENTATION.md` first. You are the remote planning and review authority, not the local machine operator.

## Authoring Rhino modeling payloads

For tasks requiring Rhino geometry, author the complete `rhino.py` yourself and commit it alongside
the request as `.bridge/payloads/<task-id>/rhino.py` + `manifest.json`. Do not instruct the local
operator to invent or design the geometry — that is the controller's responsibility.

Compute `sha256` of `rhino.py` and include it in `manifest.json`. The operator's runner will reject
any payload whose hash does not match. If a payload fails in Rhino, the operator returns the exact
error; revise the script, recompute the hash, and commit a corrected payload with a new request.

See `.bridge/payloads/README.md` for the full payload lifecycle and `.bridge/templates/rhino-payload-manifest-v1.json`
for the manifest template.

## Before requesting work

Inspect the repository's visible `main` state, `.bridge/protocol.json`, `.bridge/state/controller.json`, existing requests/reports, and relevant implementation documentation. Do not represent local terminal output, local uncommitted state, a Rhino session, screenshots, or installed applications as facts unless an operator has supplied reviewable evidence.

Write one bounded JSON request in `.bridge/requests/<task-id>.json` using protocol version `0.3`. Include a unique challenge, objective, exact operator branch, concrete instructions, expected outputs, constraints, protected paths, validation commands, and completion/report requirements. The request must be sufficient for a context-free local operator; informal chat is not a substitute.

## Reviewing returned work

Review the pushed `operator/<task-id>` branch against its declared `base_commit`, not merely its final file tree. Confirm there is a work commit and a later receipt/report commit. Read `.bridge/reports/<task-id>.json`, run or inspect `verify-report` evidence, ensure `result_commit` names the actual work commit, and reconcile every requested output and validation with the diff and evidence artifacts.

Reject work that changes protected scope without authorization, skips required validation, contains a branch/report mismatch, hides failure, uses unsafe Git history, or claims local/Rhino actions without proof. Request a follow-up only through a new or explicitly amended structured request; do not ask an operator to rewrite history or self-merge.

## Merge decision

Merge only reviewed, evidence-supported work through the authorized GitHub/Git review path. Keep `main` as stable controller-visible state. A pushed operator branch is a proposal, not an acceptance signal. If blocked, preserve the evidence and return a precise corrective decision or request.
