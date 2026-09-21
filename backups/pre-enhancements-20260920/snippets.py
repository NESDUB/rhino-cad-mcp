"""Python snippets executed inside Rhino. Keep syntax Python 3.9-compatible."""

DOCUMENT_INFO = r'''
import scriptcontext as sc

doc = sc.doc
layers = []
for layer in doc.Layers:
    if layer is None or layer.IsDeleted:
        continue
    layers.append({
        "index": layer.Index, "id": str(layer.Id), "name": layer.Name,
        "full_path": layer.FullPath, "visible": layer.IsVisible,
        "locked": layer.IsLocked, "parent_id": str(layer.ParentLayerId),
    })
objects = []
for obj in doc.Objects:
    if obj is None or obj.IsDeleted:
        continue
    geo = obj.Geometry
    bb = geo.GetBoundingBox(True) if geo else None
    objects.append({
        "id": str(obj.Id), "type": str(obj.ObjectType), "name": obj.Attributes.Name,
        "layer_index": obj.Attributes.LayerIndex,
        "selected": obj.IsSelected(False) != 0,
        "bbox": None if not bb or not bb.IsValid else {
            "min": [bb.Min.X, bb.Min.Y, bb.Min.Z], "max": [bb.Max.X, bb.Max.Y, bb.Max.Z]
        },
    })
result = {
    "name": doc.Name, "path": doc.Path, "units": str(doc.ModelUnitSystem),
    "absolute_tolerance": doc.ModelAbsoluteTolerance,
    "relative_tolerance": doc.ModelRelativeTolerance,
    "angle_tolerance_degrees": doc.ModelAngleToleranceDegrees,
    "object_count": len(objects), "layers": layers, "objects": objects,
}
'''

SELECTION_INFO = r'''
import scriptcontext as sc
selected = []
for obj in sc.doc.Objects.GetSelectedObjects(False, False):
    geo = obj.Geometry
    bb = geo.GetBoundingBox(True) if geo else None
    selected.append({
        "id": str(obj.Id), "type": str(obj.ObjectType), "name": obj.Attributes.Name,
        "layer_index": obj.Attributes.LayerIndex,
        "is_valid": bool(geo.IsValid) if geo else False,
        "bbox": None if not bb or not bb.IsValid else {
            "min": [bb.Min.X, bb.Min.Y, bb.Min.Z], "max": [bb.Max.X, bb.Max.Y, bb.Max.Z]
        },
    })
result = {"count": len(selected), "objects": selected}
'''

GH_DOCUMENT_INFO = r'''
import Grasshopper
canvas = Grasshopper.Instances.ActiveCanvas
if canvas is None or canvas.Document is None:
    result = {"open": False, "message": "No active Grasshopper canvas/document"}
else:
    ghdoc = canvas.Document
    nodes = []
    for obj in ghdoc.Objects:
        item = {
            "instance_guid": str(obj.InstanceGuid),
            "type": obj.GetType().Name,
            "name": getattr(obj, "Name", None),
            "nickname": getattr(obj, "NickName", None),
            "runtime_messages": [],
        }
        try:
            import Grasshopper.Kernel as GHK
            for level_name, level in [("error", GHK.GH_RuntimeMessageLevel.Error), ("warning", GHK.GH_RuntimeMessageLevel.Warning)]:
                for msg in obj.RuntimeMessages(level):
                    item["runtime_messages"].append({"level": level_name, "message": msg})
        except Exception:
            pass
        if hasattr(obj, "Params"):
            item["inputs"] = [{"name": p.Name, "nickname": p.NickName, "type": p.TypeName, "sources": [str(s.InstanceGuid) for s in p.Sources]} for p in obj.Params.Input]
            item["outputs"] = [{"name": p.Name, "nickname": p.NickName, "type": p.TypeName, "recipient_count": len(p.Recipients)} for p in obj.Params.Output]
        nodes.append(item)
    result = {"open": True, "node_count": len(nodes), "nodes": nodes}
'''
