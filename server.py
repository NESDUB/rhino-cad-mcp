#!/usr/bin/env python3
"""Thin MCP interface for the Claude Code -> Rhino 8 + Grasshopper agent core."""
from pathlib import Path
import json

from mcp.server.fastmcp import FastMCP

from bridge import execute, status, job_status, wait_job, list_jobs
from tool_support import targeted, runtime_call, check_code
from snippets import DOCUMENT_INFO, SELECTION_INFO, GH_DOCUMENT_INFO

ROOT = Path(__file__).resolve().parent
KNOWLEDGE = ROOT / "knowledge"
mcp = FastMCP("rhino-cad")
rhino_tool = targeted(mcp)


@rhino_tool
def rhino_status(instance_id: str = "", ping_timeout_seconds: float = 8.0) -> dict:
    """Check whether Rhino 8 is running and reachable through rhinocode."""
    return status(instance_id=instance_id or None, ping_timeout=ping_timeout_seconds)


@rhino_tool
def rhino_inspect_document() -> dict:
    """Return active Rhino document state: units, tolerances, layers, objects and bounding boxes."""
    return runtime_call("inspect_document")


@rhino_tool
def rhino_inspect_selection() -> dict:
    """Return GUIDs, types, validity and bounding boxes for selected Rhino objects."""
    return execute(SELECTION_INFO, operation="inspect_selection")


@rhino_tool
def rhino_inspect_object(guid: str) -> dict:
    """Inspect one Rhino object by GUID, including metadata and geometry validation details."""
    code = r'''
import Rhino
import scriptcontext as sc
import System

gid = System.Guid(%r)
obj = sc.doc.Objects.FindId(gid)
if obj is None:
    result = {"found": False, "guid": %r}
else:
    geo = obj.Geometry
    bb = geo.GetBoundingBox(True) if geo else None
    strings = {}
    nvc = obj.Attributes.GetUserStrings()
    if nvc:
        for key in nvc.AllKeys:
            strings[key] = nvc[key]
    data = {
        "found": True, "guid": str(obj.Id), "type": str(obj.ObjectType),
        "name": obj.Attributes.Name, "layer_index": obj.Attributes.LayerIndex,
        "is_valid": bool(geo.IsValid) if geo else False,
        "user_strings": strings,
        "bbox": None if not bb or not bb.IsValid else {
            "min": [bb.Min.X, bb.Min.Y, bb.Min.Z], "max": [bb.Max.X, bb.Max.Y, bb.Max.Z]
        },
    }
    if isinstance(geo, Rhino.Geometry.Brep):
        data.update({
            "is_solid": bool(geo.IsSolid), "is_manifold": bool(geo.IsManifold),
            "faces": geo.Faces.Count, "edges": geo.Edges.Count, "vertices": geo.Vertices.Count,
            "naked_edges": sum(1 for e in geo.Edges if e.Valence == Rhino.Geometry.EdgeAdjacency.Naked),
        })
        vmp = Rhino.Geometry.VolumeMassProperties.Compute(geo)
        amp = Rhino.Geometry.AreaMassProperties.Compute(geo)
        data["volume"] = None if vmp is None else vmp.Volume
        data["area"] = None if amp is None else amp.Area
    result = data
''' % (guid, guid)
    return execute(code, operation="inspect_object")


@rhino_tool
def rhino_run(code: str, timeout_seconds: float = 30.0, idempotency_key: str = "", wait: bool = True) -> dict:
    """Execute RhinoCommon Python 3.9 code in the active Rhino document. Assign a JSON-serializable value to `result` to return data. Never use subprocess or interactive Rhino commands inside this code."""
    return execute(check_code(code), timeout=timeout_seconds, operation="run_script", idempotency_key=idempotency_key or None, wait=wait)


@rhino_tool
def rhino_validate(guid: str) -> dict:
    """Validate an existing Rhino object by GUID. Returns validity, Brep solidity/manifold/naked-edge checks, dimensions, area and volume when applicable."""
    # Inspection already includes standardized validation; keep one implementation path.
    return rhino_inspect_object(guid)


@rhino_tool
def rhino_capture_viewport(width: int = 1920, height: int = 1080, output_path: str = "", archive_scene: bool = True, preset: dict | None = None, square: bool = False) -> dict:
    """Capture PNG plus camera/display/lighting manifest; by default archive a verified .3dm scene. preset supports camera, target, up, parallel, lens_mm, display_mode. Does not guarantee raytracer convergence."""
    return runtime_call("capture", timeout=120, width=width, height=height, output_path=output_path, archive_scene=archive_scene, preset=preset, square=square)

@rhino_tool
def rhino_capture_views(views: list[dict], width: int = 640, height: int = 480, output_path: str = "", display_mode: str = "Rendered", parallel: bool = True, archive_scene: bool = False, columns: int = 3, square: bool = False) -> dict:
    """Capture arbitrary camera presets as individual PNGs plus a labeled contact sheet; restores the original viewport."""
    return runtime_call("capture_views", timeout=300, views=views, width=width, height=height, output_path=output_path, display_mode=display_mode, parallel=parallel, archive_scene=archive_scene, columns=columns, square=square)

@rhino_tool
def rhino_visual_qa(view_presets: list[dict] | None = None, output_path: str = "", width: int = 640, height: int = 640, display_mode: str = "Rendered", require_solids: bool = False, check_intersections: bool = True) -> dict:
    """Run visual QA: captures plus proportion, silhouette, shading, material, seam, intersection, and composition heuristics."""
    return runtime_call("visual_qa", timeout=300, view_presets=view_presets, output_path=output_path, width=width, height=height, display_mode=display_mode, require_solids=require_solids, check_intersections=check_intersections)


@rhino_tool
def rhino_undo() -> dict:
    """Undo the most recent Rhino document operation. NOTE: programmatic undo from rhinocode is unreliable — this is best-effort. For guaranteed undo, the user should press Cmd+Z in Rhino. All mutating operations are wrapped in undo records so Cmd+Z undoes the entire agent operation as one step."""
    return execute('import Rhino\nimport scriptcontext as sc\nok = Rhino.RhinoApp.RunScript("_Undo", False)\nsc.doc.Views.Redraw()\nresult = {"undo_attempted": True, "note": "Programmatic undo from rhinocode is unreliable. Use Cmd+Z in Rhino for guaranteed undo."}', operation="undo")


@rhino_tool
def rhino_command(command: str) -> dict:
    """Execute a scripted Rhino command string. Commands MUST be fully scripted with all arguments inline — never use commands that prompt for interactive input. Prefix with underscore for language-independent names (e.g. '_-FilletEdge 2'). The leading '_-' suppresses dialogs."""
    code = r'''
import Rhino
import scriptcontext as sc

count_before = sc.doc.Objects.Count
cmd = %r
ok = Rhino.RhinoApp.RunScript(cmd, False)
sc.doc.Views.Redraw()
count_after = sc.doc.Objects.Count

result = {"command": cmd, "executed": bool(ok), "objects_before": count_before, "objects_after": count_after, "objects_delta": count_after - count_before}
''' % (command,)
    return execute(code, operation="rhino_command")


@rhino_tool
def rhino_save(file_path: str = "", overwrite: bool = True, verify: bool = True) -> dict:
    """Noninteractive save with readback validation. Reports written and active paths separately; does not pretend Write3dmFile renames the active document. overwrite=True preserves legacy behavior."""
    return runtime_call("verified_save", timeout=120, path=file_path, overwrite=overwrite, verify=verify)

@rhino_tool
def rhino_save_as(file_path: str, overwrite: bool = False, verify: bool = True) -> dict:
    """SaveAs through Rhino's document API, updating the target path and verifying the archive."""
    return runtime_call("save_as_active", timeout=120, path=file_path, overwrite=overwrite, verify=verify)


@rhino_tool
def rhino_export(file_path: str, object_guids: list[str] = None) -> dict:
    """Export Rhino geometry to a file. Supported: .3dm (File3dm API), .stl (binary mesh), .obj (text mesh). All fully non-interactive. For .stl/.obj, mesh data is extracted from Rhino and written on the host side to avoid Rhino's slow Python I/O. If object_guids is provided, only those objects are exported; otherwise exports all."""
    if object_guids is None:
        object_guids = []
    import os
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".3dm":
        code = r'''
import Rhino, scriptcontext as sc, System, os
guids = %r
if guids:
    objects = [sc.doc.Objects.FindId(System.Guid(g)) for g in guids if sc.doc.Objects.FindId(System.Guid(g)) is not None]
else:
    objects = list(sc.doc.Objects)
if not objects:
    raise RuntimeError("No objects to export")
f3dm = Rhino.FileIO.File3dm()
for obj in objects:
    f3dm.Objects.Add(obj.Geometry, obj.Attributes)
path = %r
f3dm.Write(path, 8)
exists = os.path.exists(path)
size = os.path.getsize(path) if exists else 0
result = {"exported": True, "path": path, "format": ".3dm", "file_exists": exists, "file_size_bytes": size, "object_count": len(objects)}
''' % (object_guids, file_path)
        return execute(code, timeout=60, operation="export")

    elif ext in (".stl", ".obj"):
        # Phase 1: extract triangle data from Rhino
        code = r'''
import Rhino, scriptcontext as sc, System
guids = %r
if guids:
    objects = [sc.doc.Objects.FindId(System.Guid(g)) for g in guids if sc.doc.Objects.FindId(System.Guid(g)) is not None]
else:
    objects = list(sc.doc.Objects)
if not objects:
    raise RuntimeError("No objects to export")
mp = Rhino.Geometry.MeshingParameters.Coarse
tris = []
for obj in objects:
    geo = obj.Geometry
    ms = []
    if isinstance(geo, Rhino.Geometry.Mesh):
        ms.append(geo)
    elif isinstance(geo, Rhino.Geometry.Brep):
        created = Rhino.Geometry.Mesh.CreateFromBrep(geo, mp)
        if created:
            ms.extend(created)
    for mesh in ms:
        mesh.FaceNormals.ComputeFaceNormals()
        v = mesh.Vertices
        for i in range(mesh.Faces.Count):
            f = mesh.Faces[i]
            n = mesh.FaceNormals[i]
            tris.append([float(n.X),float(n.Y),float(n.Z),float(v[f.A].X),float(v[f.A].Y),float(v[f.A].Z),float(v[f.B].X),float(v[f.B].Y),float(v[f.B].Z),float(v[f.C].X),float(v[f.C].Y),float(v[f.C].Z)])
            if f.IsQuad:
                tris.append([float(n.X),float(n.Y),float(n.Z),float(v[f.A].X),float(v[f.A].Y),float(v[f.A].Z),float(v[f.C].X),float(v[f.C].Y),float(v[f.C].Z),float(v[f.D].X),float(v[f.D].Y),float(v[f.D].Z)])
result = {"count": len(tris), "object_count": len(objects), "tris": tris}
''' % (object_guids,)
        r = execute(code, timeout=60, operation="export_mesh_extract")
        if not r.get("ok"):
            return r

        tris = r["result"]["tris"]
        obj_count = r["result"]["object_count"]

        # Phase 2: write file on host side
        import struct
        if ext == ".stl":
            with open(file_path, "wb") as f:
                f.write(b"RhinoCADMCP" + b"\x00" * 69)
                f.write(struct.pack("<I", len(tris)))
                for t in tris:
                    f.write(struct.pack("<12fH", *t, 0))
        else:  # .obj
            with open(file_path, "w") as f:
                f.write("# Exported by RhinoCADMCP\n")
                for t in tris:
                    for i in range(3):
                        f.write(f"v {t[3+i*3]:.6f} {t[4+i*3]:.6f} {t[5+i*3]:.6f}\n")
                for i in range(len(tris)):
                    b = i * 3 + 1
                    f.write(f"f {b} {b+1} {b+2}\n")

        size = os.path.getsize(file_path)
        return {"ok": True, "result": {"exported": True, "path": file_path, "format": ext, "file_exists": True, "file_size_bytes": size, "triangles": len(tris), "object_count": obj_count}}
    else:
        return {"ok": False, "error": f"Unsupported format: {ext}. Use .3dm, .stl, or .obj"}


@rhino_tool
def rhino_set_metadata(guid: str, key: str, value: str) -> dict:
    """Set a user string (key-value metadata) on a Rhino object. Suggested keys: role, created_by, revision, parent, operation_id."""
    code = r'''
import scriptcontext as sc
import System

gid = System.Guid(%r)
obj = sc.doc.Objects.FindId(gid)
if obj is None:
    raise RuntimeError("Object not found: " + %r)
obj.Attributes.SetUserString(%r, %r)
obj.CommitChanges()
result = {"guid": str(obj.Id), "key": %r, "value": %r, "set": True}
''' % (guid, guid, key, value, key, value)
    return execute(code, operation="set_metadata")


@rhino_tool
def rhino_get_metadata(guid: str, key: str = "") -> dict:
    """Get user string metadata from a Rhino object. If key is empty, returns all user strings."""
    code = r'''
import scriptcontext as sc
import System

gid = System.Guid(%r)
obj = sc.doc.Objects.FindId(gid)
if obj is None:
    raise RuntimeError("Object not found: " + %r)

key = %r
if key:
    val = obj.Attributes.GetUserString(key)
    result = {"guid": str(obj.Id), "key": key, "value": val}
else:
    nvc = obj.Attributes.GetUserStrings()
    strings = {}
    if nvc:
        for k in nvc.AllKeys:
            strings[k] = nvc[k]
    result = {"guid": str(obj.Id), "metadata": strings, "count": len(strings)}
''' % (guid, guid, key)
    return execute(code, operation="get_metadata")


@rhino_tool
def rhino_create_layer(name: str, color: str = "", parent: str = "") -> dict:
    """Create a Rhino layer. Color as 'R,G,B' (0-255). Parent is an existing layer name for nesting."""
    code = r'''
import Rhino
import scriptcontext as sc
import System

name = %r
color_str = %r
parent_name = %r

# Parse color
if color_str:
    parts = [int(c.strip()) for c in color_str.split(",")]
    color = System.Drawing.Color.FromArgb(255, parts[0], parts[1], parts[2])
else:
    color = System.Drawing.Color.Black

layer = Rhino.DocObjects.Layer()
layer.Name = name
layer.Color = color

if parent_name:
    pi = sc.doc.Layers.FindByFullPath(parent_name, -1)
    if pi < 0:
        raise RuntimeError("Parent layer not found: " + parent_name)
    layer.ParentLayerId = sc.doc.Layers[pi].Id

idx = sc.doc.Layers.Add(layer)
if idx < 0:
    existing = sc.doc.Layers.FindByFullPath(name, -1)
    if existing >= 0:
        idx = existing
    else:
        raise RuntimeError("Failed to create layer: " + name)

l = sc.doc.Layers[idx]
result = {"index": idx, "name": l.Name, "full_path": l.FullPath, "color": [l.Color.R, l.Color.G, l.Color.B], "id": str(l.Id)}
''' % (name, color, parent)
    return execute(code, operation="create_layer")


@rhino_tool
def rhino_move_to_layer(guid: str, layer_name: str) -> dict:
    """Move a Rhino object to a layer by name."""
    code = r'''
import scriptcontext as sc
import System

gid = System.Guid(%r)
obj = sc.doc.Objects.FindId(gid)
if obj is None:
    raise RuntimeError("Object not found: " + %r)

layer_name = %r
li = sc.doc.Layers.FindByFullPath(layer_name, -1)
if li < 0:
    raise RuntimeError("Layer not found: " + layer_name)

obj.Attributes.LayerIndex = li
obj.CommitChanges()
sc.doc.Views.Redraw()
result = {"guid": str(obj.Id), "layer": layer_name, "layer_index": li, "moved": True}
''' % (guid, guid, layer_name)
    return execute(code, operation="move_to_layer")


@mcp.tool()
def gh_inspect_document() -> dict:
    """Inspect the active Grasshopper graph: nodes, ports, connections and runtime messages."""
    return execute(GH_DOCUMENT_INFO, operation="gh_inspect_document")


@mcp.tool()
def gh_find_components(query: str, limit: int = 25) -> dict:
    """Search Rhino's live Grasshopper ComponentServer by name, nickname, category or description."""
    limit = max(1, min(int(limit), 100))
    code = r'''
import Grasshopper
needle = %r.casefold().strip()
hits = []
for proxy in Grasshopper.Instances.ComponentServer.ObjectProxies:
    fields = [str(getattr(proxy, x, "") or "") for x in ("Desc", "Category", "SubCategory")]
    try:
        fields.extend([str(proxy.Desc.Name), str(proxy.Desc.NickName), str(proxy.Desc.Description)])
    except Exception:
        pass
    if needle and not any(needle in x.casefold() for x in fields):
        continue
    hits.append({
        "guid": str(proxy.Guid),
        "name": getattr(proxy.Desc, "Name", None),
        "nickname": getattr(proxy.Desc, "NickName", None),
        "category": getattr(proxy.Desc, "Category", None),
        "subcategory": getattr(proxy.Desc, "SubCategory", None),
        "description": getattr(proxy.Desc, "Description", None),
    })
    if len(hits) >= %d:
        break
result = {"query": %r, "count": len(hits), "components": hits}
''' % (query, limit, query)
    return execute(code, operation="gh_find_components")


@mcp.tool()
def gh_bake(instance_guid: str, output_nickname: str = "", layer: str = "") -> dict:
    """Bake solved Grasshopper geometry into the Rhino document. Specify the component instance GUID and optionally which output port nickname. Optionally assign to a Rhino layer by name."""
    code = r'''
import Grasshopper
from Grasshopper.Kernel import IGH_Component, IGH_Param
import Rhino
import scriptcontext as sc
import System

canvas = Grasshopper.Instances.ActiveCanvas
if canvas is None or canvas.Document is None:
    raise RuntimeError("No active Grasshopper canvas/document")
ghdoc = canvas.Document

guid = System.Guid(%r)
obj = ghdoc.FindObject(guid, True)
if obj is None:
    raise RuntimeError("GH object not found: " + %r)

# Find the output param to bake from
out_nick = %r
params = []
if isinstance(obj, IGH_Component):
    params = list(obj.Params.Output)
elif isinstance(obj, IGH_Param):
    params = [obj]

if out_nick:
    params = [p for p in params if p.NickName == out_nick]
if not params:
    raise RuntimeError("No matching output port found")

# Resolve layer index
layer_name = %r
layer_idx = -1
if layer_name:
    li = sc.doc.Layers.FindByFullPath(layer_name, -1)
    if li < 0:
        li = sc.doc.Layers.Add(layer_name, System.Drawing.Color.FromArgb(255, 0, 0, 0))
    layer_idx = li

baked = []
for param in params:
    vd = param.VolatileData
    if vd is None or vd.PathCount == 0:
        continue
    for branch_idx in range(vd.PathCount):
        branch = vd.get_Branch(branch_idx)
        if branch is None:
            continue
        for item in branch:
            geo = getattr(item, "Value", None) if item else None
            if geo is None:
                continue
            attrs = Rhino.DocObjects.ObjectAttributes()
            if layer_idx >= 0:
                attrs.LayerIndex = layer_idx
            oid = sc.doc.Objects.Add(geo, attrs)
            if oid != System.Guid.Empty:
                baked.append({"guid": str(oid), "type": type(geo).__name__, "port": param.NickName})

sc.doc.Views.Redraw()
result = {"baked_count": len(baked), "objects": baked}
''' % (instance_guid, instance_guid, output_nickname, layer)
    return execute(code, operation="gh_bake")


@mcp.tool()
def gh_solve() -> dict:
    """Trigger a new solution on the active Grasshopper document and return runtime messages."""
    code = r'''
import Grasshopper
import Grasshopper.Kernel as GHK
canvas = Grasshopper.Instances.ActiveCanvas
if canvas is None or canvas.Document is None:
    raise RuntimeError("No active Grasshopper document")
ghdoc = canvas.Document
ghdoc.NewSolution(True)
messages = []
for obj in ghdoc.Objects:
    for label, level in [("error", GHK.GH_RuntimeMessageLevel.Error), ("warning", GHK.GH_RuntimeMessageLevel.Warning)]:
        for msg in obj.RuntimeMessages(level):
            messages.append({"node": str(obj.InstanceGuid), "name": getattr(obj, "Name", None), "level": label, "message": msg})
result = {"solved": True, "node_count": len(ghdoc.Objects), "runtime_messages": messages}
'''
    return execute(code, operation="gh_solve")


@mcp.tool()
def gh_add_component(component_guid: str, x: float = 200, y: float = 200, nickname: str = "") -> dict:
    """Add a Grasshopper component to the active canvas by its ComponentServer GUID. Use gh_find_components to discover GUIDs."""
    code = r'''
import Grasshopper
import System

canvas = Grasshopper.Instances.ActiveCanvas
if canvas is None or canvas.Document is None:
    raise RuntimeError("No active Grasshopper canvas/document")
ghdoc = canvas.Document
server = Grasshopper.Instances.ComponentServer

guid = System.Guid(%r)
obj = server.EmitObject(guid)
if obj is None:
    raise RuntimeError("ComponentServer.EmitObject returned None for GUID: " + %r)
obj.CreateAttributes()
obj.Attributes.Pivot = System.Drawing.PointF(%r, %r)
nickname = %r
if nickname:
    obj.NickName = nickname
ghdoc.AddObject(obj, False)
ghdoc.NewSolution(False)

info = {"instance_guid": str(obj.InstanceGuid), "name": obj.Name, "nickname": obj.NickName}
if hasattr(obj, "Params"):
    info["inputs"] = [{"nickname": p.NickName, "type": getattr(p, "TypeName", "")} for p in obj.Params.Input]
    info["outputs"] = [{"nickname": p.NickName, "type": getattr(p, "TypeName", "")} for p in obj.Params.Output]
result = info
''' % (component_guid, component_guid, float(x), float(y), nickname)
    return execute(code, operation="gh_add_component")


@mcp.tool()
def gh_add_slider(nickname: str, minimum: float = 0, maximum: float = 100, value: float = 50,
                  decimal_places: int = 1, x: float = 50, y: float = 100) -> dict:
    """Add a Number Slider to the active Grasshopper canvas."""
    code = r'''
import Grasshopper
import System

canvas = Grasshopper.Instances.ActiveCanvas
if canvas is None or canvas.Document is None:
    raise RuntimeError("No active Grasshopper canvas/document")
ghdoc = canvas.Document

slider = Grasshopper.Kernel.Special.GH_NumberSlider()
slider.NickName = %r
slider.CreateAttributes()
slider.Slider.Minimum = System.Decimal(%r)
slider.Slider.Maximum = System.Decimal(%r)
slider.Slider.Value = System.Decimal(%r)
slider.Slider.DecimalPlaces = %d
slider.Attributes.Pivot = System.Drawing.PointF(%r, %r)
ghdoc.AddObject(slider, False)

result = {"instance_guid": str(slider.InstanceGuid), "nickname": slider.NickName,
          "value": str(slider.CurrentValue), "min": str(slider.Slider.Minimum), "max": str(slider.Slider.Maximum)}
''' % (nickname, float(minimum), float(maximum), float(value), int(decimal_places), float(x), float(y))
    return execute(code, operation="gh_add_slider")


@mcp.tool()
def gh_add_panel(nickname: str = "Panel", x: float = 400, y: float = 100) -> dict:
    """Add a Panel to the active Grasshopper canvas."""
    code = r'''
import Grasshopper
import System

canvas = Grasshopper.Instances.ActiveCanvas
if canvas is None or canvas.Document is None:
    raise RuntimeError("No active Grasshopper canvas/document")
ghdoc = canvas.Document

panel = Grasshopper.Kernel.Special.GH_Panel()
panel.NickName = %r
panel.CreateAttributes()
panel.Attributes.Pivot = System.Drawing.PointF(%r, %r)
ghdoc.AddObject(panel, False)

result = {"instance_guid": str(panel.InstanceGuid), "nickname": panel.NickName}
''' % (nickname, float(x), float(y))
    return execute(code, operation="gh_add_panel")


@mcp.tool()
def gh_wire(from_instance_guid: str, from_output_nickname: str,
            to_instance_guid: str, to_input_nickname: str) -> dict:
    """Wire a Grasshopper output port to an input port. Use instance GUIDs (from gh_add_component etc.) and port nicknames."""
    code = r'''
import Grasshopper
from Grasshopper.Kernel import IGH_Component, IGH_Param
from Grasshopper.Kernel.Special import GH_NumberSlider, GH_Panel
import System

canvas = Grasshopper.Instances.ActiveCanvas
if canvas is None or canvas.Document is None:
    raise RuntimeError("No active Grasshopper canvas/document")
ghdoc = canvas.Document

from_guid = System.Guid(%r)
to_guid = System.Guid(%r)
from_nick = %r
to_nick = %r

src_obj = ghdoc.FindObject(from_guid, True)
dst_obj = ghdoc.FindObject(to_guid, True)
if src_obj is None:
    raise RuntimeError("Source object not found: " + %r)
if dst_obj is None:
    raise RuntimeError("Target object not found: " + %r)

# Resolve source output param
src_param = None
if isinstance(src_obj, IGH_Component):
    for p in src_obj.Params.Output:
        if p.NickName == from_nick:
            src_param = p
            break
elif isinstance(src_obj, (GH_NumberSlider, IGH_Param)):
    src_param = src_obj  # floating params are their own output

if src_param is None:
    raise RuntimeError("Source output port not found: " + from_nick)

# Resolve destination input param
dst_param = None
if isinstance(dst_obj, IGH_Component):
    for p in dst_obj.Params.Input:
        if p.NickName == to_nick:
            dst_param = p
            break
elif isinstance(dst_obj, (GH_Panel, IGH_Param)):
    dst_param = dst_obj  # panels/params are their own input

if dst_param is None:
    raise RuntimeError("Target input port not found: " + to_nick)

dst_param.AddSource(src_param)
ghdoc.NewSolution(False)

result = {"wired": True, "from": str(from_guid), "from_port": from_nick,
          "to": str(to_guid), "to_port": to_nick}
''' % (from_instance_guid, to_instance_guid, from_output_nickname, to_input_nickname,
       from_instance_guid, to_instance_guid)
    return execute(code, operation="gh_wire")


@mcp.tool()
def gh_set_slider(instance_guid: str, value: float) -> dict:
    """Set a Grasshopper slider value and trigger a new solution."""
    code = r'''
import Grasshopper
from Grasshopper.Kernel.Special import GH_NumberSlider
import System

canvas = Grasshopper.Instances.ActiveCanvas
if canvas is None or canvas.Document is None:
    raise RuntimeError("No active Grasshopper canvas/document")
ghdoc = canvas.Document

guid = System.Guid(%r)
obj = ghdoc.FindObject(guid, True)
if obj is None:
    raise RuntimeError("Object not found: " + %r)
if not isinstance(obj, GH_NumberSlider):
    raise RuntimeError("Object is not a Number Slider: " + type(obj).__name__)

obj.SetSliderValue(System.Decimal(%r))
ghdoc.NewSolution(True)

result = {"instance_guid": str(obj.InstanceGuid), "value": str(obj.CurrentValue)}
''' % (instance_guid, instance_guid, float(value))
    return execute(code, operation="gh_set_slider")


@mcp.tool()
def gh_load_document(file_path: str) -> dict:
    """Load a .gh file into the active Grasshopper canvas, replacing the current document."""
    code = r'''
import Grasshopper
import os

canvas = Grasshopper.Instances.ActiveCanvas
if canvas is None:
    import Rhino
    Rhino.RhinoApp.RunScript("_-Grasshopper _W _S _T _Enter", False)
    import time
    time.sleep(1.5)
    canvas = Grasshopper.Instances.ActiveCanvas
if canvas is None:
    raise RuntimeError("Could not open Grasshopper canvas")

path = %r
if not os.path.exists(path):
    raise RuntimeError("File not found: " + path)

io = Grasshopper.Kernel.GH_DocumentIO()
loaded = io.Open(path)
if not loaded:
    raise RuntimeError("GH_DocumentIO.Open failed for: " + path)

ghdoc = io.Document
ghdoc.Enabled = True
canvas.Document = ghdoc
canvas.Refresh()
ghdoc.NewSolution(True)

import time
time.sleep(0.5)

result = {"loaded": True, "path": path, "object_count": ghdoc.ObjectCount}
''' % (file_path,)
    return execute(code, timeout=30, operation="gh_load_document")



@rhino_tool
def rhino_list_documents(instance_id: str = "") -> dict:
    """List GUI and headless documents with stable process:runtime document IDs. Supply instance_id when multiple Rhino instances are running."""
    code = "_ns={}\nexec(open(%r).read(),_ns)\nresult=_ns['documents']()" % str(ROOT / "runtime_ops.py")
    return execute(code, operation="list_documents", instance_id=instance_id or None)

@rhino_tool
def rhino_inspect_hierarchy() -> dict:
    """Inspect both Rhino layer trees and object groups, including parent-child layers and group membership."""
    return runtime_call("inspect_hierarchy")

@rhino_tool
def rhino_test_hierarchy_effective_state() -> dict:
    """Run an isolated regression proving parent layer visibility/locking affects child effective state without changing child-local flags."""
    return runtime_call("hierarchy_regression", timeout=60)


@rhino_tool
def rhino_create_document(units: str = "Millimeters", absolute_tolerance: float = 0.01, headless: bool = False) -> dict:
    """Create and initialize a separate document without clearing existing work. Returns its document_id."""
    return runtime_call("new_document", units=units, absolute_tolerance=absolute_tolerance, headless=headless)


@rhino_tool
def rhino_open_document(file_path: str, headless: bool = False) -> dict:
    """Open an existing .3dm without closing the current document. Returns the opened document_id."""
    return runtime_call("open_document", timeout=120, path=file_path, headless=headless)


@rhino_tool
def rhino_activate_document() -> dict:
    """GUI-activate the document specified by document_id. Headless documents cannot be activated."""
    return runtime_call("activate_document")

@rhino_tool
def rhino_close_document(force: bool = False) -> dict:
    """Close a targeted document. Headless documents are safely disposed; GUI documents require force=True."""
    return runtime_call("close_document", force=force)


@mcp.tool()
def rhino_job_status(job_id: str) -> dict:
    """Retrieve a persistent pending/completed/failed job. No Rhino script is submitted."""
    return job_status(job_id)


@mcp.tool()
def rhino_job_wait(job_id: str, timeout_seconds: float = 30.0) -> dict:
    """Wait for an existing job without resubmitting it; timeout never means cancellation."""
    return wait_job(job_id, timeout_seconds)


@mcp.tool()
def rhino_list_jobs(limit: int = 30) -> dict:
    """List persistent job receipts, including uncertain submissions and recoverable late results."""
    return {"jobs": list_jobs(limit)}


@rhino_tool
def rhino_apply_material(object_ids: list[str], name: str, base_color: list[int], metallic: float = 0.0, roughness: float = 0.3, clearcoat: float = 0.0, clearcoat_roughness: float = 0.1, opacity: float = 1.0, ior: float = 1.5, specular: float = 0.5, anisotropic: float = 0.0) -> dict:
    """Create, assign and read back a genuine physical render material. Rejects shader downgrades and missing object IDs. RGB inputs are 0..255; no silent lighting compensation."""
    return runtime_call("material_apply", timeout=120, object_ids=object_ids, name=name, base_color=base_color, metallic=metallic, roughness=roughness, clearcoat=clearcoat, clearcoat_roughness=clearcoat_roughness, opacity=opacity, ior=ior, specular=specular, anisotropic=anisotropic)


@rhino_tool
def rhino_read_material(object_id: str) -> dict:
    """Read the effective render material from an object, not merely the legacy material-table entry."""
    return runtime_call("material_read", object_id=object_id)


@rhino_tool
def rhino_validate_assembly(object_ids: list[str] | None = None, require_solids: bool = True, check_intersections: bool = False, overlap_tolerance: float = 0.03, minimum_intersection_volume: float = 0.2, max_pairs: int = 5000) -> dict:
    """Check live geometry, naked edges, duplicates and semantic metadata. Optional bounded Boolean interference screening reports inconclusive failures and skipped pairs explicitly. Thresholds are in document units."""
    if overlap_tolerance < 0 or minimum_intersection_volume < 0 or not 1 <= max_pairs <= 100000:
        raise ValueError("Invalid validation thresholds or pair limit")
    return runtime_call("validate_assembly", timeout=300, object_ids=object_ids, require_solids=require_solids, check_intersections=check_intersections, overlap_tolerance=overlap_tolerance, minimum_intersection_volume=minimum_intersection_volume, max_pairs=max_pairs)


@rhino_tool
def rhino_transaction(code: str, require_solids: bool = True, dry_run: bool = False) -> dict:
    """Run trusted geometry/object-attribute edits in a headless snapshot. Validate before committing, detect target conflicts, restore objects on commit failure, retain a recovery .3dm. No layer/material/document-table edits or external-side-effect rollback; not a Python security sandbox. Use sc.doc, never ActiveDoc."""
    return runtime_call("transaction", timeout=300, code=check_code(code), require_solids=require_solids, dry_run=dry_run)


def _knowledge_text(filename: str) -> str:
    p = KNOWLEDGE / filename
    if not p.exists():
        return f"Knowledge asset not installed: {filename}"
    return p.read_text(encoding="utf-8", errors="replace")


@mcp.resource("grasshopper://capability-map")
def gh_capability_map() -> str:
    """Existing higher-level Grasshopper capability intelligence."""
    return _knowledge_text("capability_map.json")


@mcp.resource("grasshopper://recipe-intelligence")
def gh_recipe_intelligence() -> str:
    """Existing Grasshopper workflow/recipe intelligence database."""
    return _knowledge_text("recipe_intelligence.json")


@mcp.resource("grasshopper://compatibility")
def gh_compatibility() -> str:
    """Existing Grasshopper type compatibility rules."""
    return _knowledge_text("gh_compat.py")


if __name__ == "__main__":
    mcp.run(transport="stdio")
