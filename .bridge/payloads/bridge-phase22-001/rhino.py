# Controller-authored Rhino payload
# Task: bridge-phase22-001
# Model: Zestly modern 500 mL soda bottle — correction pass 2
# Python 3.9 / Rhino 8 compatible

import math
import Rhino
import scriptcontext as sc
import System

TASK_ID = "bridge-phase22-001"
MODELING_RUN_ID = "zestly-modern-soda-bottle-001"
PARENT_TASK_ID = "bridge-phase21-001"
PARENT_RESULT_COMMIT = "e8ace3769f9be3c1c925e452483b0d5b3e47e5bb"

doc = sc.doc
if doc is None:
    raise RuntimeError("No active Rhino document.")

tol = doc.ModelAbsoluteTolerance

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
        n = obj.Attributes.Name or ""
        if n.startswith(prefix):
            out.append(obj)
    return out

def replace_brep(obj, brep):
    if brep is None or not brep.IsValid:
        raise RuntimeError("Replacement Brep invalid for %s" % obj.Attributes.Name)
    ok = doc.Objects.Replace(obj.Id, brep)
    if not ok:
        raise RuntimeError("Replace failed for %s" % obj.Attributes.Name)
    return doc.Objects.FindId(obj.Id)

def set_meta(obj, role):
    attrs = obj.Attributes.Duplicate()
    attrs.SetUserString("role", role)
    attrs.SetUserString("created_by", "chatgpt-web-controller")
    attrs.SetUserString("task_id", TASK_ID)
    attrs.SetUserString("modeling_run_id", MODELING_RUN_ID)
    attrs.SetUserString("pass_index", "2")
    attrs.SetUserString("pass_kind", "correction")
    attrs.SetUserString("revision", "2")
    attrs.SetUserString("parent", PARENT_TASK_ID)
    attrs.SetUserString("parent_task_id", PARENT_TASK_ID)
    attrs.SetUserString("parent_result_commit", PARENT_RESULT_COMMIT)
    if not doc.Objects.ModifyAttributes(obj.Id, attrs, True):
        raise RuntimeError("Metadata update failed for %s" % obj.Attributes.Name)

def circle_curve(z, radius):
    plane = Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d(0.0, 0.0, float(z)),
        Rhino.Geometry.Vector3d.ZAxis
    )
    return Rhino.Geometry.Circle(plane, float(radius)).ToNurbsCurve()

def loft_solid(specs):
    curves = [circle_curve(z, r) for z, r in specs]
    lofts = Rhino.Geometry.Brep.CreateFromLoft(
        curves,
        Rhino.Geometry.Point3d.Unset,
        Rhino.Geometry.Point3d.Unset,
        Rhino.Geometry.LoftType.Normal,
        False
    )
    if lofts is None or len(lofts) != 1:
        raise RuntimeError("Body loft failed.")
    capped = lofts[0].CapPlanarHoles(tol)
    if capped is None or not capped.IsValid or not capped.IsSolid:
        raise RuntimeError("Body capping failed.")
    return capped

def cylinder_brep(radius, z0, height, cap_bottom=True, cap_top=True):
    plane = Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d(0.0, 0.0, float(z0)),
        Rhino.Geometry.Vector3d.ZAxis
    )
    circle = Rhino.Geometry.Circle(plane, float(radius))
    cyl = Rhino.Geometry.Cylinder(circle, float(height))
    brep = cyl.ToBrep(cap_bottom, cap_top)
    if brep is None or not brep.IsValid:
        raise RuntimeError("Cylinder creation failed.")
    return brep

def boolean_difference(a, b, label):
    out = Rhino.Geometry.Brep.CreateBooleanDifference(a, b, tol)
    if out is None or len(out) != 1:
        raise RuntimeError("%s boolean difference returned %s pieces" % (label, 0 if out is None else len(out)))
    if not out[0].IsValid:
        raise RuntimeError("%s boolean result invalid" % label)
    return out[0]

def hollow_cylinder(outer_r, inner_r, z0, height, top_thickness, label):
    outer = cylinder_brep(outer_r, z0, height, True, True)
    cutter_z = z0 - 0.5
    cutter_h = height - top_thickness + 0.5
    inner = cylinder_brep(inner_r, cutter_z, cutter_h, True, True)
    return boolean_difference(outer, inner, label)

def rotated_box_rib(angle, r0, r1, half_tan, z0, z1):
    box = Rhino.Geometry.Box(
        Rhino.Geometry.Plane.WorldXY,
        Rhino.Geometry.Interval(r0, r1),
        Rhino.Geometry.Interval(-half_tan, half_tan),
        Rhino.Geometry.Interval(z0, z1)
    )
    b = box.ToBrep()
    xf = Rhino.Geometry.Transform.Rotation(
        float(angle),
        Rhino.Geometry.Vector3d.ZAxis,
        Rhino.Geometry.Point3d.Origin
    )
    b.Transform(xf)
    return b

# Resolve foundation objects.
body_obj = find_one("Zestly PET Bottle Body")
neck_obj = find_one("Zestly Neck Finish")
label_obj = find_one("Zestly Printed Label Sleeve")
cap_obj = find_one("Zestly Screw Cap")
tamper_obj = find_one("Zestly Tamper Ring")
base_ring_obj = find_one("Zestly Base Contact Ring")
rib_objs = find_prefix("Zestly Cap Rib ")

# 1) Correct body/neck transition and improve the modern PET silhouette.
body_specs = [
    (0.0, 30.8),
    (2.0, 32.0),
    (7.0, 33.0),
    (18.0, 33.2),
    (52.0, 33.2),
    (58.0, 33.1),
    (146.0, 33.1),
    (156.0, 32.9),
    (166.0, 31.6),
    (176.0, 28.0),
    (184.0, 23.0),
    (190.0, 17.2),
    (196.0, 14.2)
]
new_body = loft_solid(body_specs)

# Add a shallow central push-up so the base reads as PET rather than a flat cylinder.
punt = Rhino.Geometry.Sphere(
    Rhino.Geometry.Point3d(0.0, 0.0, -15.0),
    24.0
).ToBrep()
new_body = boolean_difference(new_body, punt, "base push-up")
body_obj = replace_brep(body_obj, new_body)

# Neck now starts exactly where body ends, eliminating the volume overlap.
new_neck = cylinder_brep(14.2, 196.0, 7.0, True, True)
neck_obj = replace_brep(neck_obj, new_neck)

# 2) Replace proxy cap/tamper solids with hollow, clearance-aware packaging geometry.
cap_shell = hollow_cylinder(17.1, 14.8, 203.0, 16.5, 2.0, "cap shell")

rib_breps = [cap_shell]
rib_count = 28
for i in range(rib_count):
    a = 2.0 * math.pi * float(i) / float(rib_count)
    rib_breps.append(rotated_box_rib(a, 16.9, 18.15, 0.75, 204.0, 218.3))

unioned = Rhino.Geometry.Brep.CreateBooleanUnion(rib_breps, tol)
if unioned is None or len(unioned) != 1 or not unioned[0].IsValid:
    raise RuntimeError("Cap rib union failed.")
cap_obj = replace_brep(cap_obj, unioned[0])

new_tamper = hollow_cylinder(17.4, 14.8, 199.6, 3.0, 0.0, "tamper ring")
tamper_obj = replace_brep(tamper_obj, new_tamper)

for obj in rib_objs:
    if not doc.Objects.Delete(obj.Id, True):
        raise RuntimeError("Failed to delete old cap rib %s" % obj.Attributes.Name)

# 3) Conform label sleeve more closely and rotate artwork ~180 degrees so the hero panel faces Front.
label_radius = 33.17
label_z0 = 58.0
label_height = 88.0
label_brep = cylinder_brep(label_radius, label_z0, label_height, False, False)
label_obj = replace_brep(label_obj, label_brep)

mapping_plane = Rhino.Geometry.Plane(
    Rhino.Geometry.Point3d(0.0, 0.0, label_z0),
    Rhino.Geometry.Vector3d.XAxis,
    Rhino.Geometry.Vector3d.YAxis
)
mapping_plane.Rotate(math.radians(184.0), Rhino.Geometry.Vector3d.ZAxis)
mapping_circle = Rhino.Geometry.Circle(mapping_plane, label_radius)
mapping_cyl = Rhino.Geometry.Cylinder(mapping_circle, label_height)
mapping = Rhino.Render.TextureMapping.CreateCylinderMapping(mapping_cyl, False)
if mapping is None:
    raise RuntimeError("Failed to create rotated label mapping.")
if not doc.Objects.ModifyTextureMapping(label_obj, 1, mapping):
    raise RuntimeError("Failed to apply rotated label texture mapping.")

# 4) Remove the overlapping foundation base-ring proxy; the body now owns the corrected base.
if not doc.Objects.Delete(base_ring_obj.Id, True):
    raise RuntimeError("Failed to delete old base contact ring.")

# 5) Complete lineage/revision metadata on every remaining controlled object.
body_obj = doc.Objects.FindId(body_obj.Id)
neck_obj = doc.Objects.FindId(neck_obj.Id)
label_obj = doc.Objects.FindId(label_obj.Id)
cap_obj = doc.Objects.FindId(cap_obj.Id)
tamper_obj = doc.Objects.FindId(tamper_obj.Id)

set_meta(body_obj, "bottle_body")
set_meta(neck_obj, "neck_finish")
set_meta(label_obj, "printed_label_sleeve")
set_meta(cap_obj, "screw_cap_with_integrated_grip_ribs")
set_meta(tamper_obj, "tamper_ring")

# Document lineage.
doc.Strings.SetString("RHINO_CHATGPT", "modeling_run_id", MODELING_RUN_ID)
doc.Strings.SetString("RHINO_CHATGPT", "task_id", TASK_ID)
doc.Strings.SetString("RHINO_CHATGPT", "pass_index", "2")
doc.Strings.SetString("RHINO_CHATGPT", "pass_kind", "correction")
doc.Strings.SetString("RHINO_CHATGPT", "parent_task_id", PARENT_TASK_ID)
doc.Strings.SetString("RHINO_CHATGPT", "parent_result_commit", PARENT_RESULT_COMMIT)

doc.Views.Redraw()

bbox = new_body.GetBoundingBox(True)

result = {
    "ok": True,
    "task_id": TASK_ID,
    "modeling_run_id": MODELING_RUN_ID,
    "pass_index": 2,
    "pass_kind": "correction",
    "parent_task_id": PARENT_TASK_ID,
    "corrected_targets": [
        "body_neck_overlap_and_silhouette",
        "cap_tamper_proxy_overlap",
        "label_front_orientation_and_radial_gap",
        "flat_overlapping_base_proxy",
        "missing_revision_parent_metadata"
    ],
    "objects": {
        "body": str(body_obj.Id),
        "neck_finish": str(neck_obj.Id),
        "label_sleeve": str(label_obj.Id),
        "cap": str(cap_obj.Id),
        "tamper_ring": str(tamper_obj.Id)
    },
    "object_count_expected_controlled": 5,
    "body_bbox": {
        "min": [bbox.Min.X, bbox.Min.Y, bbox.Min.Z],
        "max": [bbox.Max.X, bbox.Max.Y, bbox.Max.Z]
    },
    "nominal_dimensions_mm": {
        "overall_height": 219.5,
        "max_body_diameter": 66.4,
        "label_outer_diameter": 66.34,
        "neck_outer_diameter": 28.4,
        "cap_outer_diameter": 36.3
    },
    "notes": [
        "Pass 2 is a bounded correction pass; no new branding or unrelated features were introduced.",
        "Five foundation discrepancies were addressed. Petaloid feet, true thread geometry, PET wall thickness, and final micro-detail remain candidates for detail_qa."
    ]
}
