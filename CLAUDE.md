# Onboarding

Before substantive repository work, read `AI_ORIENTATION.md` and `.bridge/orientation/operator.md`. The Rhino CAD Agent Rules below remain mandatory for live Rhino or Grasshopper work.

# Rhino CAD Agent Rules

Use the `rhino-cad` MCP tools as the primary interface to Rhino 8 and Grasshopper.

## Workflow
1. Inspect state before modifying existing work (`rhino_inspect_document`, `rhino_inspect_selection`, `gh_inspect_document`).
2. Plan using document units and model tolerances.
3. Execute the smallest deterministic operation.
4. Validate geometry; successful script execution is not proof of correct CAD output.
5. Capture the viewport when visual verification materially helps.
6. Re-inspect after significant changes.

## Hard prohibitions
- NEVER call `subprocess`, `os.system`, or other blocking process-spawn mechanisms from Python executed inside Rhino.
- NEVER issue Rhino commands that require interactive user input.
- NEVER infer success from rhinocode exit codes.
- Rhino runtime code must remain Python 3.9 compatible.

## Grasshopper
- Live ComponentServer metadata is authoritative for installed components.
- Use the bundled capability map, recipe intelligence, and compatibility rules as higher-level planning knowledge.
- Inspect runtime messages after solving.

## Metadata
Prefer Rhino object user strings/document strings for semantic identity before introducing an external registry. Suggested keys: `role`, `created_by`, `revision`, `parent`, `operation_id`.
