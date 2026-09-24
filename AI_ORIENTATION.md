# Rhino CHATGPT AI Orientation Handbook

**Canonical stable handbook — orientation version 1.0.0.** Read this before making substantive repository, bridge, or Rhino decisions. Generated payloads from `./orient.sh` deliberately separate this stable content from live Git/controller facts.

## Mission and architecture

`NESDUB/rhino-cad-mcp` provides a Rhino 8 and Grasshopper MCP integration while using the Git-backed `.bridge/` control plane to coordinate a remote controller and a local execution operator. The runtime is authoritative for CAD behavior; the bridge is a separate coordination system. Its durable transport is Git/GitHub: requests, evidence, reports, commits, and reviewed merges are the record of work.

The system has four operating roles. The **controller** (normally ChatGPT Web) converts desired outcomes into structured `.bridge/requests/<task-id>.json` requests and reviews returned work. **Git/GitHub** carries the durable reviewable state. The **operator** (normally Codex or another local LLM) works only in the local checkout on a dedicated `operator/<task-id>` branch. **Rhino** is the live CAD application accessed through the MCP runtime; it is not implied to be available merely because a controller can read this repository. A **reviewer** independently checks scope, evidence, branch isolation, and merge readiness.

## Sources of truth and instruction precedence

Git-tracked repository state is durable truth. The request JSON for an active task is the authoritative task contract; its challenge, branch, constraints, and required lifecycle override informal bootstrap wording. Current controller/operator state files are measured context, not authority to rewrite task requirements. Live Rhino inspection is authoritative for the active Rhino/Grasshopper document; never infer live CAD state from a Git commit or a successful script exit alone.

Resolve conflicts in this order: platform and safety requirements; the active structured request and bridge protocol; repository safety files such as `AGENTS.md` and `CLAUDE.md`; this handbook and role guide; generated live-state facts; then informal chat instructions. If a higher-precedence instruction is ambiguous or conflicts with a requested action, stop and report the blocker rather than inventing a workaround.

## Normal request-to-review lifecycle

1. The controller commits a machine-readable request to `.bridge/requests/` on `main`.
2. The local operator begins from a clean `main`, fast-forwards from `origin/main`, and uses `./exchange.sh prepare <task-id>` to validate the request and create the required `operator/<task-id>` branch.
3. The operator completes only the requested scope, records validation and evidence, and commits implementation/evidence as the **work commit**.
4. The operator writes `.bridge/reports/<task-id>.json` with the exact request acknowledgement, base SHA, work-commit SHA as `result_commit`, and branch; validates it with `python3 .bridge/bridge_cli.py verify-report <task-id>`; commits it separately as the **receipt commit**; and pushes the operator branch without force-pushing or merging.
5. The controller/reviewer inspects the branch, report, evidence, diff, base/result commits, and validations. Only reviewed work may be merged into `main` by the authorized review path.

`./operator.sh` is the one-command local runner for the normal operator flow: from a clean `main`, it synchronizes, finds the single pending task, and launches Codex with the task bootstrap. It does not replace review, make Rhino available remotely, or authorize unsafe Git operations.

## Responsibilities

**Controller responsibilities:** inspect `main` and bridge state before queuing work; write bounded, testable JSON requests; state expected outputs, constraints, and a unique challenge; avoid claiming local filesystem, local Git, or Rhino access it does not have; review the returned branch rather than assuming completion; and merge only after evidence supports the request.

**Local operator responsibilities:** verify local branch and worktree safety; treat the active request JSON as authoritative; preserve existing work; stay on the required operator branch; avoid protected paths unless explicitly authorized; run the requested validations; create the work commit and separate report receipt commit; and push the unmerged branch for review.

**Reviewer responsibilities:** independently compare request, diff, evidence, commits, and report; verify the receipt references the actual work commit and exact branch; reject missing validation, scope creep, invented capabilities, or unsafe Git history; and communicate approval or blockers to the controller.

## Modeling authority and controller-authored payloads

**ChatGPT Web is the normal author of Rhino modeling Python.** For geometry tasks, the controller
authors `rhino.py` and commits it as `.bridge/payloads/<task-id>/rhino.py` alongside a `manifest.json`
containing a SHA-256 hash of the script. The local operator executes the exact controller-authored
payload through `python3 .bridge/run_rhino_payload.py --task <task-id> --document-id <id>`.

**Local Claude** is an execution/validation operator. Claude must not invent substitute geometry,
redesign objects, or edit modeling code to compensate for errors. A failed payload is a reportable
blocker returned to the controller for correction — not an invitation to rewrite the script.

**Local Codex** follows the same default. Codex may author, repair, or alter Rhino modeling code
only when the active structured request explicitly grants `local_modeling_authorized=true`. There is
no implicit modeling authority from being Codex or from a task being urgent.

The runner (`run_rhino_payload.py`) enforces these invariants: it rejects mismatched hashes,
non-controller author_role, missing targets, and Python that fails `tool_support.check_code`.

**Complex modeling is normally controller-led and iterative.** Each pass is a separate structured
request; the local operator returns objective evidence after execution; the controller reviews that
evidence and authors the next targeted refinement payload. The operator does not autonomously
redesign geometry or create its own next-pass payload. See `.bridge/workflows/MULTI_PASS_RHINO.md`.

## Safety invariants

- Never work directly on `main` for an operator task; never force-push, overwrite history, auto-discard local work, or merge an operator branch as the operator.
- Pull only by fast-forward or fail. A dirty or divergent repository is a stop condition, not permission to reset it.
- Do not claim execution, inspection, screenshots, tests, or Rhino access that did not occur. Successful code execution alone is not CAD validation.
- Keep bridge control-plane work isolated from Rhino/MCP runtime changes unless the request explicitly authorizes those changes. Preserve project-specific prohibitions in `CLAUDE.md`.
- Treat credentials, personal data, external side effects, and live CAD modifications as actions requiring the applicable explicit authority and evidence.

## Evidence, validation, and failure behavior

Evidence must let a reviewer reproduce the claim: name the command/check, its result, relevant artifact paths, and known limitations. Run the request-mandated validation plus proportional diff/syntax/schema checks. A failed validation, missing required capability, unclear ownership, branch mismatch, or unexpected local change is a blocker. Preserve the current state, do not hide or discard it, record the blocker in evidence/reporting, and return control to the controller for a corrected request or human decision.

## Merge and review model

The operator produces a reviewable branch; it does not self-approve or merge. The controller/reviewer verifies base isolation, implementation scope, work and receipt commits, report schema, validations, and evidence before merging. `main` remains the controller-visible stable state. Until reviewed and merged, an operator branch is proposed work rather than accepted repository truth.

## First five minutes for a context-free AI

1. Identify your role: controller, operator, or reviewer; generate `./orient.sh <role>` if a local checkout is available.
2. Read this handbook, `.bridge/orientation/manifest.json`, the selected role guide, and the current `.bridge/protocol.json`.
3. Inspect `git status --short --branch`, current commit, `.bridge/state/controller.json`, and `.bridge/state/operator.json` if present; label unavailable machine facts as unavailable.
4. For an active task, read the complete `.bridge/requests/<task-id>.json`; do not rely on a copied chat summary.
5. Before changing anything, confirm branch ownership, required outputs, protected paths, validation requirements, and the next handoff: controller request, operator branch, or review decision.
