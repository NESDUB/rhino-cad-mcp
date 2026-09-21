# Rhino CAD MCP Test Ground

This directory is a living laboratory for improving AI-driven Rhino modeling. Tests are not disposable pass/fail checks: each one is also a documented modeling pattern, an executable example, and a record of what RhinoCommon actually does on the installed Rhino version.

## Goals

- Turn failures into reproducible, diagnosable examples rather than silently working around them.
- Preserve multiple valid ways to build the same form: primitives, profiles, lofts, sweeps, Breps, meshes, materials, and staged transactions.
- Verify geometry numerically and visually; successful script execution alone is never evidence of a correct model.
- Capture Rhino-version-specific API behavior so future agents can build on observed facts instead of guessing.
- Keep experiments safe, deterministic, and isolated from the user's working documents.

## Test categories

`test_enhancements.py` contains fast host-side tests. These cover discovery parsing, environment repair, document targeting, job persistence, idempotency, Python 3.9 compatibility, input restrictions, and MCP schema compatibility. They should run without Rhino:

```bash
python3 -m unittest discover -s tests -v
```

`live_integration.py` is an opt-in end-to-end suite. It creates disposable Rhino documents, exercises document lifecycle, geometry creation, materials, assembly validation, transactions, saves, captures, and stale-target handling. It must restore the original GUI document and must not edit a user's production file. Run it only when Rhino is open and the MCP transport is available:

```bash
python3 tests/live_integration.py
```

`live_receipt.json` is diagnostic evidence from the most recent live run. A failed receipt is useful: preserve it until the failure is understood, then add a regression test before changing behavior.

## How to add an experiment

1. State the modeling question in the test name and docstring, such as whether a loft remains valid after a fillet or whether a material survives a `.3dm` round trip.
2. Use a temporary or headless document. Never clear, overwrite, or dispose of an unrelated user document.
3. Build in small deterministic stages and record IDs, units, tolerances, bounding boxes, validity, and object-table counts.
4. Add visual feedback for appearance-sensitive work with `rhino_capture_viewport`; store manifests rather than relying on an unrecorded screenshot.
5. Validate important Breps for validity, solidity, manifoldness, naked edges, duplicates, and expected bounds.
6. When an API behaves unexpectedly, create a minimal probe that isolates the behavior. Keep the probe as a regression example instead of hiding it in production code.
7. On failure, preserve the exact inputs and receipt, identify whether the problem is transport, document targeting, Rhino API behavior, geometry, or assertion logic, then add a focused test for the fix.

## Modeling patterns worth expanding

- Compare primitive construction with profile-and-loft construction for the same silhouette.
- Compare direct object edits with staged `rhino_transaction` commits and dry runs.
- Test symmetry, controlled asymmetry, fillet radii, panel gaps, and material transitions at different document tolerances.
- Test duplicate detection and Boolean interference with both solids and intentionally open Breps.
- Test save/readback identity using names, GUIDs, units, bounds, materials, and object counts.
- Test lifecycle explicitly: create headless, save, save-as, reopen, inspect, and dispose; GUI documents should not be closed implicitly by an agent.
- Test camera presets and lighting manifests so visual results are reproducible rather than angle-dependent.
- Use `rhino_capture_views` for arbitrary camera directions and labeled contact sheets; inspect both the PNG and JSON manifest when validating orientation.
- Validate aspect-ratio contracts: `square=True` must produce equal pixel dimensions and manifest `aspect_ratio: 1.0`; `square=False` must preserve requested dimensions.
- Use `rhino_visual_qa` for a combined capture/validation report. Treat its warnings as deterministic review signals, not as a learned visual-quality judgment; fixtures with intentional overlaps should document expected intersection warnings.

## Safety and compatibility

Rhino-side scripts must remain Python 3.9 compatible, must not spawn processes, and must not issue interactive commands. Host tests may use the MCP launcher's Python version. Live tests should use explicit `document_id` values returned by `rhino_list_documents`; never rely on whichever document happens to be current. A pending job is not a failed or canceled job—poll its receipt before considering a retry.

The best test is one that teaches the next modeling agent both **how to succeed** and **how to recognize when a seemingly successful result is wrong**.
