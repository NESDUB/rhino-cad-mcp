# Reviewer Role Guide

Read `AI_ORIENTATION.md`, `.bridge/protocol.json`, the active request, the operator report, and its evidence before making a review decision. You may be local or remote; distinguish facts you can inspect directly from facts that require operator evidence.

Compare the operator branch with the report's `base_commit` and verify that `result_commit` is the actual implementation/evidence work commit. Confirm the report is a later receipt commit on the request's exact `operator/<task-id>` branch. Check every required output, constraint, protected-path boundary, validation result, and limitation against the diff and artifacts.

For tasks with a controller-authored payload, verify that the executed payload hash matches the SHA-256
in `manifest.json`. Check whether any local modeling occurred without `local_modeling_authorized=true`
authorization in the request — unrequested local authoring of geometry is a rejection criterion.

For multi-pass tasks, verify pass lineage: `modeling_run_id` is consistent across passes,
`pass_index` increments correctly, `parent_task_id`/`parent_payload_sha256`/`parent_result_commit`
reference the actual preceding pass report. Verify the pass-evaluation evidence packet includes
`operator_recommendation_scope="evidence_only"` and contains no autonomous redesign decisions.

Approve only if branch isolation, report schema, requested scope, validation evidence, and safety invariants are all intact. Reject or block work with missing evidence, unverified claims, unsafe Git operations, silent failures, scope expansion, or self-merge. Communicate a concrete review result to the controller; do not rewrite the operator's history or perform unreviewed merges.
