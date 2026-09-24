# Controller-authored Rhino payload
# Task: bridge-phase23-001
# Replacement Pass 2 CORRECTION after visual rejection of bridge-phase22-001.
# Source state: verified Phase 21 FOUNDATION artifact only.
# Python 3.9 / Rhino 8 compatible.

import math

import Rhino
import scriptcontext as sc

TASK_ID = "bridge-phase23-001"
MODELING_RUN_ID = "zestly-modern-soda-bottle-001"
PARENT_TASK_ID = "bridge-phase21-001"
PARENT_RESULT_COMMIT = "e8ace3769f9be3c1c925e452483b0d5b3e47e5bb"

doc = sc.doc
if doc is None:
    raise RuntimeError("No active Rhino document.")

def find_one(name):
    found = []
    for obj in doc.Objects:
        if obj.Attributes.Name == name:
            found.append(obj)
    if len(found) != 1:
        raise RuntimeError("Expected exactly one object named %r; found %d" % (name, len(found)))
    return found[0]

def find_prefix(prefix):
    out = []
    for obj in doc.Objects:
        name = obj.Attributes.Name or ""
        if name.startswith(prefix):
            out.append(obj)
    return out

def set_lineage(obj):
    attrs = obj.Attributes.Duplicate()
    attrs.SetUserString("task_id", TASK_ID)
    attrs.SetUserString("modeling_run_id", MODELING_RUN_ID)
    attrs.SetUserString("pass_index", "2")
    attrs.SetUserString("pass_kind", "correction")
    attrs.SetUserString("revision", "2")
    attrs.SetUserString("parent", PARENT_TASK_ID)
    attrs.SetUserString("parent_task_id", PARENT_TASK_ID)
    attrs.SetUserString("parent_result_commit", PARENT_RESULT_COMMIT)
    attrs.SetUserString("controller_change_scope", "label_mapping_and_metadata_only")
    if not doc.Objects.ModifyAttributes(obj.Id, attrs, True):
        raise RuntimeError("Failed metadata update for " + (obj.Attributes.Name or str(obj.Id)))

# Require the exact Phase 21 foundation state.
expected_names = [
    "Zestly PET Bottle Body",
    "Zestly Neck Finish",
    "Zestly Printed Label Sleeve",
    "Zestly Screw Cap",
    "Zestly Tamper Ring",
    "Zestly Base Contact Ring"
]
for name in expected_names:
    find_one(name)

ribs = find_prefix("Zestly Cap Rib ")
if len(ribs) != 28:
    raise RuntimeError("Expected 28 Phase 21 cap ribs; found %d" % len(ribs))

live = [obj for obj in doc.Objects if not obj.IsDeleted]
if len(live) != 34:
    raise RuntimeError("Expected exactly 34 live Phase 21 objects; found %d" % len(live))

# Preserve a pre-change geometric signature using GUID + bbox + topology counts.
before = {}
for obj in live:
    geo = obj.Geometry
    bb = geo.GetBoundingBox(True)
    record = {
        "bbox": [
            bb.Min.X, bb.Min.Y, bb.Min.Z,
            bb.Max.X, bb.Max.Y, bb.Max.Z
        ],
        "type": str(obj.ObjectType)
    }
    if isinstance(geo, Rhino.Geometry.Brep):
        record["faces"] = geo.Faces.Count
        record["edges"] = geo.Edges.Count
        record["vertices"] = geo.Vertices.Count
        record["is_solid"] = bool(geo.IsSolid)
    before[str(obj.Id)] = record

# The only visual correction: rotate the existing cylindrical label mapping
# so the green Zestly hero panel faces the standard Front view.
label_obj = find_one("Zestly Printed Label Sleeve")
label_radius = 33.85
label_z0 = 58.0
label_height = 88.0

mapping_plane = Rhino.Geometry.Plane(
    Rhino.Geometry.Point3d(0.0, 0.0, label_z0),
    Rhino.Geometry.Vector3d.XAxis,
    Rhino.Geometry.Vector3d.YAxis
)
mapping_plane.Rotate(math.radians(184.0), Rhino.Geometry.Vector3d.ZAxis)
mapping_circle = Rhino.Geometry.Circle(mapping_plane, label_radius)
mapping_cylinder = Rhino.Geometry.Cylinder(mapping_circle, label_height)
mapping = Rhino.Render.TextureMapping.CreateCylinderMapping(mapping_cylinder, False)
if mapping is None:
    raise RuntimeError("Failed to create cylindrical label mapping.")
if not doc.Objects.ModifyTextureMapping(label_obj, 1, mapping):
    raise RuntimeError("Failed to apply label mapping correction.")

# Metadata-only lineage update across the preserved Phase 21 object set.
for obj in live:
    set_lineage(obj)

doc.Strings.SetString("RHINO_CHATGPT", "modeling_run_id", MODELING_RUN_ID)
doc.Strings.SetString("RHINO_CHATGPT", "task_id", TASK_ID)
doc.Strings.SetString("RHINO_CHATGPT", "pass_index", "2")
doc.Strings.SetString("RHINO_CHATGPT", "pass_kind", "correction")
doc.Strings.SetString("RHINO_CHATGPT", "parent_task_id", PARENT_TASK_ID)
doc.Strings.SetString("RHINO_CHATGPT", "parent_result_commit", PARENT_RESULT_COMMIT)
doc.Strings.SetString("RHINO_CHATGPT", "controller_change_scope", "label_mapping_and_metadata_only")

# Verify no geometry changed.
after_live = [obj for obj in doc.Objects if not obj.IsDeleted]
if len(after_live) != 34:
    raise RuntimeError("Live object count changed unexpectedly.")

changed_geometry = []
for obj in after_live:
    geo = obj.Geometry
    bb = geo.GetBoundingBox(True)
    record = {
        "bbox": [
            bb.Min.X, bb.Min.Y, bb.Min.Z,
            bb.Max.X, bb.Max.Y, bb.Max.Z
        ],
        "type": str(obj.ObjectType)
    }
    if isinstance(geo, Rhino.Geometry.Brep):
        record["faces"] = geo.Faces.Count
        record["edges"] = geo.Edges.Count
        record["vertices"] = geo.Vertices.Count
        record["is_solid"] = bool(geo.IsSolid)
    if before.get(str(obj.Id)) != record:
        changed_geometry.append(str(obj.Id))

if changed_geometry:
    raise RuntimeError("Geometry changed outside authorized scope: " + ",".join(changed_geometry))

doc.Views.Redraw()

result = {
    "ok": True,
    "task_id": TASK_ID,
    "modeling_run_id": MODELING_RUN_ID,
    "pass_index": 2,
    "pass_kind": "correction",
    "parent_task_id": PARENT_TASK_ID,
    "source_state": "bridge-phase21-001 foundation artifact",
    "rejected_intermediate_task": "bridge-phase22-001",
    "authorized_change_scope": "label_mapping_and_metadata_only",
    "geometry_unchanged": True,
    "live_object_count": len(after_live),
    "cap_rib_count": len(ribs),
    "label_mapping_rotation_degrees": 184.0,
    "notes": [
        "This replacement correction intentionally preserves the complete Phase 21 bottle geometry.",
        "The controller rejected Phase 22 because numerical cleanup caused a visible regression.",
        "No body, base, neck, cap, tamper-ring, rib, or label-surface geometry was replaced, moved, deleted, booleaned, or resized.",
        "Only cylindrical texture mapping orientation and provenance metadata were changed."
    ]
}
