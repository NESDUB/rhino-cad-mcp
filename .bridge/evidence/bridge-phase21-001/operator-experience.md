# Operator Experience — bridge-phase21-001

Execution friction only. No modeling recommendations.

## Execution environment

- Rhino 8 was running. MCP rhino-cad server was live.
- Dedicated document `16858:268435461` created via `rhino_create_document`. Units: Millimeters (confirmed).
- Branch: `operator/bridge-phase21-001` prepared via `./exchange.sh prepare bridge-phase21-001`.

## Dry-run friction

The initial dry-run attempt (without `--document-id`) failed because `manifest.target_document_required=true` requires a document ID argument. Resolved by passing the pre-created document ID `16858:268435461`. Dry-run then passed cleanly.

## Payload execution

Executed via `python3 .bridge/run_rhino_payload.py --task bridge-phase21-001 --document-id 16858:268435461`. Returned `EXECUTION COMPLETE` with all 34 objects and GUIDs. No Python exceptions.

## Capture friction

`rhino_capture_views` requires:
1. `output_path` must end in `.png` (not a directory). Discovered on first call.
2. Each view dict must contain a `direction` vector — the `camera` preset name alone is not accepted. Discovered on second call.

Both resolved on the third call. No data loss.

## Save

`rhino_save_as` with `overwrite=false` succeeded on first attempt. Save mode reported as `SaveAs` (document internal path unchanged — correct, artifact written to `.bridge/artifacts/`).

## Context window interruption

The session exceeded context limits between payload execution and post-execution steps. All execution output (GUIDs, bbox, volume) was preserved in the session summary. No data was lost; post-execution steps resumed from summary.

## No other blockers

SHA verification, document isolation, validation, assembly check, and all evidence generation completed without errors.
