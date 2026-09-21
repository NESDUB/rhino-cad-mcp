# Rhino CAD MCP

Thin MCP wrapper around the experimentally verified **Claude Code → rhinocode → Rhino 8 / Grasshopper** pipeline on macOS.

## Architecture

```text
Claude Code ──MCP/stdio──> server.py ──> bridge.py ──> rhinocode
                                                   ├─> RhinoCommon / active .3dm
                                                   └─> Grasshopper / active .gh
```

`server.py` stays deliberately thin. `bridge.py` owns the critical asynchronous `rhinocode` behavior: unique scripts/results, file signaling, polling, timeout handling, JSON parsing, and exception capture.

## MCP tools

### Rhino
- `rhino_status`
- `rhino_inspect_document`
- `rhino_inspect_selection`
- `rhino_inspect_object`
- `rhino_run`
- `rhino_validate`
- `rhino_capture_viewport`
- `rhino_undo`

### Grasshopper
- `gh_inspect_document`
- `gh_find_components`
- `gh_solve`

## Resources
- `grasshopper://capability-map`
- `grasshopper://recipe-intelligence`
- `grasshopper://compatibility`

The supplied Grasshopper intelligence files are reused rather than replaced. Rhino's live ComponentServer remains authoritative for currently installed component metadata.

## Requirements

- macOS
- Rhino 8 running
- `/Applications/Rhino 8.app/Contents/Resources/bin/rhinocode`
- Python environment used to launch this server must have the `mcp` package providing `mcp.server.fastmcp.FastMCP`

No package is installed inside Rhino.

## Run

```bash
python3 /path/to/rhino-cad-mcp/server.py
```

The MCP client should launch `server.py` over stdio, just like the supplied `codex-keymap-mcp` example.

If Rhino is installed elsewhere:

```bash
export RHINOCODE_PATH="/path/to/rhinocode"
```

Optional default timeout:

```bash
export RHINO_MCP_TIMEOUT=30
```

## Critical safety invariants

1. **Never use `subprocess.run()` or spawn blocking subprocesses from code executing inside Rhino.** The audit showed this can freeze Rhino's Python runtime/script queue.
2. **Never issue interactive Rhino commands from agent scripts.** A command waiting for user input blocks the queue.
3. Do not trust `rhinocode` exit codes as proof of script success.
4. Do not expect `rhinocode` stdout/stderr to carry script output.
5. `rhinocode` execution is asynchronous; the bridge's result-file handshake is the completion signal.
6. Rhino's bundled Python is 3.9; code passed to `rhino_run` must be Python 3.9 compatible.

## `rhino_run` contract

Code executes inside Rhino with a variable named `result` predeclared. Assign JSON-serializable output to it:

```python
import Rhino
import scriptcontext as sc

sphere = Rhino.Geometry.Sphere(Rhino.Geometry.Point3d.Origin, 10)
guid = sc.doc.Objects.AddSphere(sphere)
sc.doc.Views.Redraw()
result = {"guid": str(guid)}
```

The bridge captures exceptions, traceback, redirected Python console output, operation ID, Rhino execution time, and host-side round-trip time.

## Design note

This project intentionally keeps the CAD core independent of MCP. A CLI or tests can import `bridge.execute()` directly, and the transport can later be replaced without changing Rhino/Grasshopper semantics.
