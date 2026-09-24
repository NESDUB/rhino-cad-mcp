# Operator Experience — bridge-phase17-001

**Role:** Claude Code acting as local operator  
**Model:** claude-sonnet-4-6 (v2.1.100)  
**Date:** 2026-09-24  
**Outcome:** COMPLETE — full end-to-end path demonstrated for the first time.

---

## What Felt Smooth

**Everything from preflight to save worked.** After six phases of incremental debugging, the full path ran without a single high-severity blocker. `rhino_status` returned a live ping in 5.3ms. `rhino_list_documents` correctly identified the existing user document. `rhino_create_document` created an isolated working space. `rhino_run` created three valid solids in a single call. All metadata read back correctly. All three validations passed. The contact sheet rendered. The save verified. The final inspection confirmed the document is clean and open.

**The MCP tool execution model is effective.** Writing geometry with `rhino_run` and RhinoCommon felt natural — no more boilerplate than writing a Python script directly. The tool's idempotency_key parameter is a useful guard for accidental duplicate executions. `rhino_validate` returning structured geometry data (is_solid, is_manifold, naked_edges, volume, area) in one call is the right design — no inference required.

**rhino_save_as with verify=true is a solid completion gate.** The readback (live_count, file_count, all_valid, units_match, bbox mismatches) gives a reviewer everything they need to confirm the save without re-opening the file.

**The Git bridge is invisible in the right way.** Exchange, commit, push — no friction. The protocol overhead is proportional to task complexity. For a task this size (~16 MCP calls), the bridge adds maybe 5 minutes of scaffolding total.

---

## What Was Awkward

**rhino_capture_views required two retries due to undocumented API format.** The tool schema description says "Capture arbitrary camera presets" but the runtime rejects both (a) a directory path and (b) preset name strings. The correct format — `{"name":"iso", "direction":[1,1,1], "up":[0,0,1]}` — is only discoverable by reading `runtime_ops.py` source. Two error/retry cycles were required. The errors were clear, but the fix required reading source code.

**rhino_create_document produces an opaque temp name.** The document identity (RHINO_CHATGPT_BRIDGE_POC_004) is established at save time, not creation time. In the Rhino GUI, the document shows up with a UUID filename. This is a minor UX issue — the document is correctly isolated and identified in the artifact — but it may confuse a user watching the GUI who sees a meaningless name rather than the task name.

**rhino_save_as active_document_path_after doesn't update.** After saving to the artifact directory, the document's GUI path remains the temp TMPDIR path. This is technically correct SaveAs behavior, but an operator who checks "what is this document's path in Rhino" will see the temp path, not the artifact path. Not a blocker, but worth documenting.

**assembly_validation tested_pairs=0 requires explanation.** The three objects are stacked (touching at faces, not overlapping), so the broad-phase bbox test finds 0 candidate pairs above the overlap threshold. The result is correct — no interference — but "tested_pairs=0" looks at first glance like the test didn't run. An operator who doesn't understand the broad-phase axis overlap mechanism might misread this as an inconclusive check.

---

## What Required Reasoning That Should Have Been Automated

**Direction vector format for rhino_capture_views.** The mapping from human-readable view names to direction vectors (iso=[1,1,1], top=[0,0,1], front=[0,-1,0], right=[1,0,0]) is standard knowledge, but it required source code inspection to confirm the tool expected it. A preset lookup table in the tool or its documentation would eliminate this step.

**Document name tracking.** After `rhino_create_document`, the operator must mentally track that the document identity will be the save path, not the temp name. This is implicit state that an operator must carry through the lifecycle without any tool feedback until save_as.

---

## What Required Manual Intervention

None. The two retries on rhino_capture_views were resolved by reading source code and adjusting parameters — no human action required.

---

## Top Five Workflow Improvements (Ranked by Impact)

1. **Add named view presets to rhino_capture_views** (MR2)  
   Accept 'iso', 'top', 'front', 'right', 'perspective' as direction shorthands. The current API is correct but requires source-code knowledge to use correctly. This is the only tool where schema documentation required source-code inspection during this run.

2. **Add a name parameter to rhino_create_document** (MR1)  
   Let operators set a semantic name at creation time. The document shows up in the GUI with a UUID filename; setting `name="RHINO_CHATGPT_BRIDGE_POC_004"` at creation would make the workflow legible in real time.

3. **Document the full-quit-and-relaunch requirement in operator.md** (PC1 from Phase 16)  
   Now proven: fresh relaunch = tools in session. This must be the first line in the operator checklist for any session that follows an MCP config change.

4. **Add a rhino_capture_views example to the operator guide**  
   Four standard view direction vectors with a working call example. One JSON code block would have prevented both retries in this run.

5. **Consider rhino_save_as "SaveAndRename" mode**  
   After SaveAs, update the document's active path to the new destination. This would make the Rhino GUI path match the artifact path, eliminating the active_document_path ambiguity.

---

## Overall Assessment

This is the run the series was building toward. Six phases of incremental debugging — server registration, import fix, scope discovery, session restart — all converged on a clean end-to-end execution. The architecture works: ChatGPT queues a structured request → Git carries it → Claude receives, branches, executes, validates, captures, saves, reports → Git carries the evidence back.

The MCP tool surface is coherent and the RhinoCommon execution model is expressive. The two retries in this run were entirely due to undocumented API format — both were fixable with one additional information source. No geometry errors, no connectivity failures, no validation failures.

The bridge is proven. The next logical step is to refine the friction points (view preset naming, document naming) and run a more complex geometry task.
