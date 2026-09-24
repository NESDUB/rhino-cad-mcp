# Controller-authored Rhino payload
# Task: bridge-phase24-001
# Combined modern PET soda-bottle redesign + high-resolution Zestly label.
# Source state: verified Phase 21 FOUNDATION artifact.
# Python 3.9 / Rhino 8 compatible.

import base64
import hashlib
import math
import os

import Rhino
import scriptcontext as sc
import System
from System.Drawing import Color

TASK_ID = "bridge-phase24-001"
MODELING_RUN_ID = "zestly-modern-soda-bottle-001"
PARENT_TASK_ID = "bridge-phase21-001"
PARENT_RESULT_COMMIT = "e8ace3769f9be3c1c925e452483b0d5b3e47e5bb"

LABEL_B64_RELATIVE_PATH = ".bridge/assets/bridge-phase24-001/zestly_label_960_q80.jpg.b64"
LABEL_SHA256 = "c597c2f244b6f3e31812e54d2af71fe7817a4517a9c8e226aad608293074860e"
LABEL_DIMENSIONS_PX = [960, 249]

doc = sc.doc
if doc is None:
    raise RuntimeError("No active Rhino document.")

if str(doc.ModelUnitSystem) != "Millimeters":
    raise RuntimeError("Phase 24 requires a millimeter Rhino document.")

repo_root = os.path.join(os.path.expanduser("~"), "bin", "mcp", "rhino-cad-mcp")
label_b64_path = os.path.join(repo_root, LABEL_B64_RELATIVE_PATH)
if not os.path.isfile(label_b64_path):
    raise RuntimeError("High-resolution label transport asset missing: " + label_b64_path)

with open(label_b64_path, "r") as f:
    encoded_label = "".join(f.read().split())
try:
    label_bytes = base64.b64decode(encoded_label)
except Exception as exc:
    raise RuntimeError("Could not decode high-resolution label asset: " + str(exc))

actual_label_sha = hashlib.sha256(label_bytes).hexdigest()
if actual_label_sha != LABEL_SHA256:
    raise RuntimeError("High-resolution label SHA-256 mismatch: " + actual_label_sha)

artifact_dir = os.path.join(repo_root, ".bridge", "artifacts", TASK_ID)
if not os.path.isdir(artifact_dir):
    os.makedirs(artifact_dir)
label_path = os.path.join(artifact_dir, "zestly_label_960_q80.jpg")
with open(label_path, "wb") as f:
    f.write(label_bytes)

tol = doc.ModelAbsoluteTolerance

# ---------------------------------------------------------------------------
# Source-state validation
# ---------------------------------------------------------------------------

def live_objects():
    return [obj for obj in doc.Objects if not obj.IsDeleted]

def find_named(name):
    found = [obj for obj in live_objects() if obj.Attributes.Name == name]
    if len(found) != 1:
        raise RuntimeError("Expected exactly one Phase 21 object named %r; found %d" % (name, len(found)))
    return found[0]

expected_names = [
    "Zestly PET Bottle Body",
    "Zestly Neck Finish",
    "Zestly Printed Label Sleeve",
    "Zestly Screw Cap",
    "Zestly Tamper Ring",
    "Zestly Base Contact Ring"
]
for n in expected_names:
    find_named(n)

phase21_ribs = [
    obj for obj in live_objects()
    if (obj.Attributes.Name or "").startswith("Zestly Cap Rib ")
]
if len(phase21_ribs) != 28:
    raise RuntimeError("Expected 28 Phase 21 cap ribs; found %d" % len(phase21_ribs))

if len(live_objects()) != 34:
    raise RuntimeError("Expected exactly 34 live Phase 21 objects; found %d" % len(live_objects()))

# Delete the old foundation geometry only after the source state is proven.
for obj in list(live_objects()):
    if not doc.Objects.Delete(obj.Id, True):
        raise RuntimeError("Failed to clear Phase 21 object: " + (obj.Attributes.Name or str(obj.Id)))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_layer(name, color):
    idx = doc.Layers.FindByFullPath(name, -1)
    if idx >= 0:
        layer = doc.Layers[idx]
        if layer.Color != color:
            dup = layer.Duplicate()
            dup.Color = color
            doc.Layers.Modify(dup, idx, True)
        return idx
    layer = Rhino.DocObjects.Layer()
    layer.Name = name
    layer.Color = color
    idx = doc.Layers.Add(layer)
    if idx < 0:
        raise RuntimeError("Failed to create layer: " + name)
    return idx

def add_material(name, diffuse, transparency=0.0, shine=0.0, bitmap_path=None):
    mat = Rhino.DocObjects.Material()
    mat.Name = name
    mat.DiffuseColor = diffuse
    mat.Transparency = float(transparency)
    mat.Shine = float(shine)
    if bitmap_path is not None:
        if not mat.SetBitmapTexture(bitmap_path):
            raise RuntimeError("Failed to assign bitmap texture: " + bitmap_path)
    idx = doc.Materials.Add(mat)
    if idx < 0:
        raise RuntimeError("Failed to create material: " + name)
    return idx

def attrs_for(name, layer_idx, material_idx, role, extra=None):
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.Name = name
    attrs.LayerIndex = layer_idx
    attrs.MaterialIndex = material_idx
    attrs.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject

    metadata = {
        "created_by": "chatgpt-web-controller",
        "task_id": TASK_ID,
        "modeling_run_id": MODELING_RUN_ID,
        "pass_index": "2",
        "pass_kind": "correction",
        "revision": "2",
        "parent": PARENT_TASK_ID,
        "parent_task_id": PARENT_TASK_ID,
        "parent_result_commit": PARENT_RESULT_COMMIT,
        "role": role
    }
    if extra:
        metadata.update(extra)
    for k, v in metadata.items():
        attrs.SetUserString(str(k), str(v))
    return attrs

def add_brep(brep, name, layer_idx, material_idx, role, extra=None, require_solid=True):
    if brep is None or not brep.IsValid:
        raise RuntimeError("Invalid Brep: " + name)
    if require_solid and not brep.IsSolid:
        raise RuntimeError("Expected solid Brep: " + name)
    gid = doc.Objects.AddBrep(
        brep,
        attrs_for(name, layer_idx, material_idx, role, extra)
    )
    if gid == System.Guid.Empty:
        raise RuntimeError("Failed to add: " + name)
    return gid

def circle_curve(z, radius):
    plane = Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d(0.0, 0.0, float(z)),
        Rhino.Geometry.Vector3d.ZAxis
    )
    return Rhino.Geometry.Circle(plane, float(radius)).ToNurbsCurve()

def loft_solid(specs, label):
    curves = [circle_curve(z, radius) for z, radius in specs]
    lofts = Rhino.Geometry.Brep.CreateFromLoft(
        curves,
        Rhino.Geometry.Point3d.Unset,
        Rhino.Geometry.Point3d.Unset,
        Rhino.Geometry.LoftType.Normal,
        False
    )
    if lofts is None or len(lofts) != 1:
        raise RuntimeError(label + " loft did not return exactly one Brep.")
    capped = lofts[0].CapPlanarHoles(tol)
    if capped is None or not capped.IsValid or not capped.IsSolid:
        raise RuntimeError(label + " failed capping/solid validation.")
    return capped

def cylinder_brep(radius, z0, height, cap_bottom=True, cap_top=True):
    plane = Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d(0.0, 0.0, float(z0)),
        Rhino.Geometry.Vector3d.ZAxis
    )
    circle = Rhino.Geometry.Circle(plane, float(radius))
    cyl = Rhino.Geometry.Cylinder(circle, float(height))
    brep = cyl.ToBrep(bool(cap_bottom), bool(cap_top))
    if brep is None or not brep.IsValid:
        raise RuntimeError("Cylinder creation failed.")
    return brep, cyl

def annulus_brep(outer_radius, inner_radius, z0, height, label):
    outer, _ = cylinder_brep(outer_radius, z0, height, True, True)
    inner, _ = cylinder_brep(inner_radius, z0 - 0.2, height + 0.4, True, True)
    diff = Rhino.Geometry.Brep.CreateBooleanDifference(outer, inner, tol)
    if diff is None or len(diff) != 1:
        raise RuntimeError(label + " annulus boolean failed.")
    if not diff[0].IsValid or not diff[0].IsSolid:
        raise RuntimeError(label + " annulus invalid.")
    return diff[0]

def ellipsoid_brep(radial_scale, tangent_scale, vertical_scale, angle, radial_center, z_center):
    radial = Rhino.Geometry.Vector3d(math.cos(angle), math.sin(angle), 0.0)
    tangent = Rhino.Geometry.Vector3d(-math.sin(angle), math.cos(angle), 0.0)
    scale_plane = Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d.Origin,
        radial,
        tangent
    )

    brep = Rhino.Geometry.Sphere(Rhino.Geometry.Point3d.Origin, 1.0).ToBrep()
    xform_scale = Rhino.Geometry.Transform.Scale(
        scale_plane,
        float(radial_scale),
        float(tangent_scale),
        float(vertical_scale)
    )
    brep.Transform(xform_scale)

    center = Rhino.Geometry.Point3d(
        radial_center * math.cos(angle),
        radial_center * math.sin(angle),
        z_center
    )
    brep.Transform(Rhino.Geometry.Transform.Translation(center.X, center.Y, center.Z))
    if not brep.IsValid or not brep.IsSolid:
        raise RuntimeError("Petaloid foot ellipsoid invalid.")
    return brep

def torus_brep(angle, radial_center, z_center, major_radius, minor_radius):
    origin = Rhino.Geometry.Point3d(
        radial_center * math.cos(angle),
        radial_center * math.sin(angle),
        z_center
    )
    normal = Rhino.Geometry.Vector3d(math.cos(angle), math.sin(angle), 0.0)
    plane = Rhino.Geometry.Plane(origin, normal)
    torus = Rhino.Geometry.Torus(plane, float(major_radius), float(minor_radius))
    brep = torus.ToBrep()
    if brep is None or not brep.IsValid or not brep.IsSolid:
        raise RuntimeError("Grip detail torus invalid.")
    return brep

def set_cylindrical_mapping(guid, radius, z0, height, rotation_degrees):
    obj = doc.Objects.FindId(guid)
    if obj is None:
        raise RuntimeError("Could not find label object for mapping.")

    plane = Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d(0.0, 0.0, z0),
        Rhino.Geometry.Vector3d.XAxis,
        Rhino.Geometry.Vector3d.YAxis
    )
    plane.Rotate(math.radians(rotation_degrees), Rhino.Geometry.Vector3d.ZAxis)
    circle = Rhino.Geometry.Circle(plane, radius)
    cyl = Rhino.Geometry.Cylinder(circle, height)
    mapping = Rhino.Render.TextureMapping.CreateCylinderMapping(cyl, False)
    if mapping is None:
        raise RuntimeError("Failed to create cylindrical texture mapping.")
    if not doc.Objects.ModifyTextureMapping(obj, 1, mapping):
        raise RuntimeError("Failed to apply cylindrical texture mapping.")

# ---------------------------------------------------------------------------
# Layers + materials
# ---------------------------------------------------------------------------

bottle_layer = ensure_layer("ZESTLY_BOTTLE", Color.FromArgb(215, 235, 228))
label_layer = ensure_layer("ZESTLY_LABEL", Color.FromArgb(25, 205, 95))
cap_layer = ensure_layer("ZESTLY_CAP", Color.FromArgb(35, 190, 70))
grip_layer = ensure_layer("ZESTLY_GRIP", Color.FromArgb(185, 220, 205))
base_layer = ensure_layer("ZESTLY_BASE", Color.FromArgb(195, 225, 212))
detail_layer = ensure_layer("ZESTLY_DETAILS", Color.FromArgb(65, 75, 70))

pet_mat = add_material(
    "Zestly PET Clear HR",
    Color.FromArgb(245, 250, 248),
    transparency=0.86,
    shine=90.0
)
pet_detail_mat = add_material(
    "Zestly PET Detail HR",
    Color.FromArgb(225, 240, 233),
    transparency=0.72,
    shine=100.0
)
cap_mat = add_material(
    "Zestly Cap Green Modern",
    Color.FromArgb(30, 190, 70),
    transparency=0.0,
    shine=45.0
)
label_mat = add_material(
    "Zestly Lemon Lime Label HIGH RES",
    Color.White,
    transparency=0.0,
    shine=20.0,
    bitmap_path=label_path
)

# ---------------------------------------------------------------------------
# Modern PET bottle body
# ---------------------------------------------------------------------------

# Contemporary 500 mL soda-bottle proportions:
# raised central bottom at Z=6, five petaloid feet to Z=0,
# lower grip waist, cylindrical label zone, fast but smooth shoulder transition.
body_sections = [
    (6.0,   29.0),
    (10.0,  31.0),
    (18.0,  32.4),
    (30.0,  32.9),
    (42.0,  32.7),
    (54.0,  31.8),
    (64.0,  30.2),
    (74.0,  30.0),
    (84.0,  31.0),
    (90.0,  32.2),
    (105.0, 32.35),
    (135.0, 32.35),
    (150.0, 32.25),
    (156.0, 31.8),
    (163.0, 30.4),
    (170.0, 28.4),
    (177.0, 25.7),
    (184.0, 22.5),
    (190.0, 19.4),
    (196.0, 16.4),
    (201.0, 14.6),
    (204.0, 14.3)
]

body = loft_solid(body_sections, "Modern PET bottle body")
body_id = add_brep(
    body,
    "Zestly Modern PET Bottle Body",
    bottle_layer,
    pet_mat,
    "bottle_body",
    {
        "design_language": "modern_current_day_soda_bottle",
        "nominal_volume_ml": "500",
        "reference_intent": "current commercial PET soda bottle proportions"
    }
)

# ---------------------------------------------------------------------------
# Five-foot petaloid-style base
# ---------------------------------------------------------------------------

foot_ids = []
for i in range(5):
    angle = math.radians(90.0 + i * 72.0)
    foot = ellipsoid_brep(
        radial_scale=9.2,
        tangent_scale=5.6,
        vertical_scale=5.8,
        angle=angle,
        radial_center=24.2,
        z_center=5.8
    )
    gid = add_brep(
        foot,
        "Zestly Petaloid Foot %02d" % (i + 1),
        base_layer,
        pet_detail_mat,
        "petaloid_foot",
        {
            "foot_index": str(i),
            "intended_contact": "overlaps lower bottle body to read as integrated PET base"
        }
    )
    foot_ids.append(str(gid))

# ---------------------------------------------------------------------------
# Lower-body grip language: staggered embossed dimple rings
# ---------------------------------------------------------------------------

grip_ids = []
grip_rows = [
    (36.0, 0.0, 31.7),
    (49.0, 36.0, 31.3),
    (62.0, 0.0, 30.1)
]
for row_index, row in enumerate(grip_rows):
    z, offset_deg, radial_center = row
    for i in range(5):
        angle = math.radians(offset_deg + i * 72.0)
        ring = torus_brep(
            angle=angle,
            radial_center=radial_center,
            z_center=z,
            major_radius=3.1,
            minor_radius=0.42
        )
        gid = add_brep(
            ring,
            "Zestly Grip Dimple R%d-%02d" % (row_index + 1, i + 1),
            grip_layer,
            pet_detail_mat,
            "grip_dimple_ring",
            {
                "row_index": str(row_index),
                "dimple_index": str(i)
            }
        )
        grip_ids.append(str(gid))

# ---------------------------------------------------------------------------
# Neck / support ring
# ---------------------------------------------------------------------------

neck_brep, _ = cylinder_brep(14.3, 204.0, 6.5, True, True)
neck_id = add_brep(
    neck_brep,
    "Zestly Modern Neck Finish",
    bottle_layer,
    pet_mat,
    "neck_finish"
)

support_brep, _ = cylinder_brep(15.5, 207.8, 1.4, True, True)
support_id = add_brep(
    support_brep,
    "Zestly Neck Support Ring",
    detail_layer,
    pet_detail_mat,
    "neck_support_ring"
)

# ---------------------------------------------------------------------------
# High-resolution printed label
# ---------------------------------------------------------------------------

label_radius = 32.55
label_z0 = 90.0
label_height = 66.0
label_brep, _ = cylinder_brep(label_radius, label_z0, label_height, False, False)
label_id = add_brep(
    label_brep,
    "Zestly HIGH RES Printed Label Sleeve",
    label_layer,
    label_mat,
    "printed_label_sleeve",
    {
        "source_asset": LABEL_B64_RELATIVE_PATH,
        "decoded_texture_path": ".bridge/artifacts/%s/zestly_label_960_q80.jpg" % TASK_ID,
        "texture_sha256": LABEL_SHA256,
        "texture_dimensions_px": "960x249",
        "texture_resolution_class": "high_resolution"
    },
    require_solid=False
)

# 184 degrees was visually verified in Phase 22 to put the green hero artwork
# toward the standard Front view. We retain the orientation while discarding
# the rejected Phase 22 geometry.
set_cylindrical_mapping(
    label_id,
    label_radius,
    label_z0,
    label_height,
    184.0
)

# ---------------------------------------------------------------------------
# Modern cap + tamper system
# ---------------------------------------------------------------------------

cap_sections = [
    (210.6, 17.15),
    (212.0, 17.25),
    (223.8, 17.0),
    (225.6, 16.55)
]
cap_body = loft_solid(cap_sections, "Modern soda cap")
cap_id = add_brep(
    cap_body,
    "Zestly Modern Screw Cap",
    cap_layer,
    cap_mat,
    "screw_cap"
)

cap_rib_ids = []
rib_count = 30
for i in range(rib_count):
    angle = 2.0 * math.pi * float(i) / float(rib_count)
    box = Rhino.Geometry.Box(
        Rhino.Geometry.Plane.WorldXY,
        Rhino.Geometry.Interval(16.85, 17.85),
        Rhino.Geometry.Interval(-0.48, 0.48),
        Rhino.Geometry.Interval(212.0, 224.0)
    )
    rib = box.ToBrep()
    rib.Transform(
        Rhino.Geometry.Transform.Rotation(
            angle,
            Rhino.Geometry.Vector3d.ZAxis,
            Rhino.Geometry.Point3d.Origin
        )
    )
    gid = add_brep(
        rib,
        "Zestly Modern Cap Rib %02d" % (i + 1),
        cap_layer,
        cap_mat,
        "cap_grip_rib",
        {"rib_index": str(i)}
    )
    cap_rib_ids.append(str(gid))

tamper = annulus_brep(17.0, 14.75, 208.2, 2.1, "Tamper ring")
tamper_id = add_brep(
    tamper,
    "Zestly Modern Tamper Ring",
    cap_layer,
    cap_mat,
    "tamper_ring"
)

# ---------------------------------------------------------------------------
# Document metadata + result
# ---------------------------------------------------------------------------

doc.Strings.SetString("RHINO_CHATGPT", "modeling_run_id", MODELING_RUN_ID)
doc.Strings.SetString("RHINO_CHATGPT", "task_id", TASK_ID)
doc.Strings.SetString("RHINO_CHATGPT", "model_name", "Zestly Modern 500 mL PET Soda Bottle")
doc.Strings.SetString("RHINO_CHATGPT", "pass_index", "2")
doc.Strings.SetString("RHINO_CHATGPT", "pass_kind", "correction")
doc.Strings.SetString("RHINO_CHATGPT", "parent_task_id", PARENT_TASK_ID)
doc.Strings.SetString("RHINO_CHATGPT", "parent_result_commit", PARENT_RESULT_COMMIT)
doc.Strings.SetString("RHINO_CHATGPT", "label_resolution", "960x249")

doc.Views.Redraw()

assembly = live_objects()
bbox = Rhino.Geometry.BoundingBox.Empty
for obj in assembly:
    bbox.Union(obj.Geometry.GetBoundingBox(True))

result = {
    "ok": True,
    "task_id": TASK_ID,
    "modeling_run_id": MODELING_RUN_ID,
    "pass_index": 2,
    "pass_kind": "correction",
    "parent_task_id": PARENT_TASK_ID,
    "source_state": "verified bridge-phase21-001 artifact",
    "combined_objective": [
        "modern current-day commercial PET soda bottle redesign",
        "high-resolution label replacement and correct front orientation"
    ],
    "label_asset": {
        "repo_relative_path": LABEL_RELATIVE_PATH,
        "sha256": LABEL_SHA256,
        "dimensions_px": LABEL_DIMENSIONS_PX,
        "mapping_rotation_degrees": 184.0
    },
    "design_dimensions_mm": {
        "overall_height": 225.6,
        "body_max_diameter": 64.7,
        "label_outer_diameter": 65.1,
        "label_height": 66.0,
        "cap_max_diameter_approx": 35.7,
        "raised_center_bottom_z": 6.0,
        "petaloid_foot_contact_z": 0.0
    },
    "object_counts": {
        "total_live": len(assembly),
        "petaloid_feet": len(foot_ids),
        "grip_dimples": len(grip_ids),
        "cap_ribs": len(cap_rib_ids)
    },
    "assembly_bbox": {
        "min": [bbox.Min.X, bbox.Min.Y, bbox.Min.Z],
        "max": [bbox.Max.X, bbox.Max.Y, bbox.Max.Z]
    },
    "notes": [
        "This pass intentionally combines the modern bottle redesign and high-resolution label correction.",
        "The bottle uses a raised-center five-foot base strategy rather than the rejected Phase 22 spherical subtraction.",
        "The label texture is 960 pixels wide versus the Phase 21 256-pixel proxy, with approximately 13.9x the source pixel count.",
        "The lower body includes a pronounced grip waist and staggered dimple-ring detailing inspired by current commercial soda PET packaging.",
        "The design is generic modern soda packaging and does not reproduce the supplied Sprite branding."
    ]
}
