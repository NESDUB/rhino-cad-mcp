# Multi-Pass Rhino Modeling Workflow

This document describes the controller-led iterative modeling architecture for the NESDUB/rhino-cad-mcp bridge.
It is the canonical reference for multi-pass geometry work.

## Core principle

Complex or reference-driven modeling is **iterative by design**. The controller authors each pass;
the local operator executes and returns objective evidence; the controller reviews that evidence
and authors the next targeted correction. The loop continues until the controller accepts the result.

**The local operator never decides how to redesign geometry.** Between passes, all design decisions
belong to the controller. The operator's job is to return accurate, structured evidence that makes
those decisions possible.

**These policies are machine-enforced.** `verify-report` checks payload SHA provenance,
unauthorized operator modifications, multi-pass lineage sequencing, and presence of the canonical
`pass-evaluation.json` at `.bridge/evidence/<task-id>/pass-evaluation.json`. A report that
violates any of these invariants will not reach `REPORT_OK`.

## Role boundaries

| Who | Does |
|-----|------|
| ChatGPT Web (controller) | Authors `rhino.py` for every pass. Reviews returned evidence. Selects correction targets. Accepts result. |
| Local Claude (operator) | Executes exact payload, measures, validates, captures, saves, reports. Stops. Does not redesign. |
| Local Codex (operator) | Same default as Claude. May author modeling code only when the active request grants `local_modeling_authorized=true`. |
| Git/GitHub | Carries payloads in, evidence out. Every pass is a separate task_id, branch, and report. |

## Pass taxonomy

| pass_kind | Purpose |
|-----------|---------|
| `foundation` | Pass 1. Primary proportions, topology strategy, major solids, coarse dimensions. |
| `correction` | Pass 2+. Controller-selected, bounded discrepancy corrections based on returned evidence. |
| `detail_qa` | Final pass. Secondary geometry, cleanup, dimensional/visual QA, artifact finalization. |
| `hotfix` | Out-of-band targeted fix for a specific defect found in review. |
| `single_pass` | A complete one-shot payload when iterative refinement is not needed. |

These are guidelines, not hard protocol constraints. Extra or skipped passes are valid when the
task warrants it. Three passes (foundation → correction → detail_qa) are a useful default for
complex reference-driven work, not a mandatory limit.

## Lifecycle

```
Controller                          Git                      Local Operator
---------                           ---                      --------------
Author rhino.py (pass 1)
Commit payload + request ---------> main
                                     |
                                     |   (operator picks up)
                                     |
                                     |   exchange.sh prepare
                                     |   verify payload hash
                                     |   execute via run_rhino_payload.py
                                     |   validate, capture, save
                                     |   write pass-evaluation evidence
                                     |   commit work + receipt
                                     <-- push operator/<task-id>
                                     |
Review evidence, captures, .3dm
Compare against reference/spec
Select bounded correction targets
Author rhino.py (pass 2)
Commit payload + request ---------> main
                                     |
                                     |   (repeat)
                                     ...
Accept result
Merge branch
```

Each pass is a **separate structured request** with its own `task_id`, operator branch, payload,
hash-verified execution, evidence commit, and report. The controller receives evidence between
passes — there is no autonomous internal redesign loop.

## Payload pass lineage

Passes in the same modeling run share a stable `modeling_run_id`. Each pass also carries optional
references to its parent: `parent_task_id`, `parent_payload_sha256`, and `parent_result_commit`.
These fields are optional and backward-compatible; single-pass payloads omit them.

Example manifest chain:

```
Pass 1 (foundation): task_id=model001-pass1, modeling_run_id=run-abc, pass_index=1
Pass 2 (correction): task_id=model001-pass2, modeling_run_id=run-abc, pass_index=2,
                     parent_task_id=model001-pass1, parent_payload_sha256=<hash1>,
                     parent_result_commit=<commit1>
Pass 3 (detail_qa):  task_id=model001-pass3, modeling_run_id=run-abc, pass_index=3,
                     parent_task_id=model001-pass2, parent_payload_sha256=<hash2>,
                     parent_result_commit=<commit2>
```

## Evidence packet (per pass)

The operator produces a standardized pass-evaluation document after each executed pass.
See `.bridge/templates/rhino-pass-evaluation-v1.json` for the full schema.

Key fields:
- `executed_payload_sha256` — must match the manifest; confirms exact payload was run
- `measurements` — bounding boxes, volumes, areas, object counts, layer counts
- `validation_summary` — per-object validity, solid state, naked edges
- `capture_artifacts` — paths to PNGs, contact sheet, manifest
- `save_artifact` — path and size of saved `.3dm`
- `objective_discrepancies` — measurable gaps vs. spec/reference, no redesign proposals
- `operator_recommendation_scope` — always `"evidence_only"`

The `operator_recommendation_scope` field encodes the policy in the evidence itself: the
operator observes and measures; recommendations are outside scope.

## Correction target selection

Between passes, the controller inspects the returned evidence and selects correction targets.
A useful default is a bounded set of the highest-impact discrepancies (typically 3–5), but this
is a judgment call for the controller, not a protocol constraint. The controller then authors a
new `rhino.py` that addresses those specific targets and commits it as the next pass payload.

## Failure and retry behavior

A payload execution failure is a blocker. The operator records the exact error, does not patch
the script, and returns it through the normal report path. The controller revises the payload,
recomputes the hash, and commits a corrected request. This may be a new `pass_kind=hotfix` pass
or an incremented `pass_index` within the same modeling run.

## Stop conditions

The controller accepts the result when the returned evidence meets the acceptance criteria for
the task. Common stop conditions:
- All required geometry validated (valid, solid, manifold)
- Key dimensions within tolerance
- Visual captures match reference sufficiently
- Controller explicitly accepts in the review

## Example three-pass sequence

**Task:** model a decorative column base to a reference image.

**Pass 1 — foundation** (`pass_kind=foundation`, `pass_index=1`)
- Controller authors: primary box for base slab, rough cylinder for shaft, cap block.
- Operator returns: bounding boxes, volumes, 4-view capture, saved .3dm.
- Controller observes: shaft is too narrow, cap overhangs by 8mm, overall height is 15% short.

**Pass 2 — correction** (`pass_kind=correction`, `pass_index=2`)
- Controller selects 3 targets: correct shaft radius, reduce cap, scale total height.
- Controller authors new rhino.py addressing only those three issues.
- Operator returns: updated measurements, 4-view capture, saved .3dm.
- Controller observes: proportions are now close; edge fillets and chamfers needed.

**Pass 3 — detail_qa** (`pass_kind=detail_qa`, `pass_index=3`)
- Controller authors: fillets, chamfers, final dimensional pass, assembly validation.
- Operator returns: final validation (valid, solid, 0 naked edges), 4-view capture, saved .3dm.
- Controller accepts. Merges branch.

Total controller round trips: 3. Total autonomous operator redesigns: 0.
