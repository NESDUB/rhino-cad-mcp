# Controller-authored Rhino payload
# Zestly modern 500 mL soda bottle — Pass 1 FOUNDATION
# Python 3.9 / Rhino 8 compatible.

import hashlib
import math
import os

import Rhino
import scriptcontext as sc
import System
from System.Drawing import Color

TASK_ID = "bridge-phase21-001"
MODELING_RUN_ID = "zestly-modern-soda-bottle-001"
LABEL_RELATIVE_PATH = ".bridge/assets/bridge-phase21-001/zestly_full_label_256.jpg"
LABEL_SHA256 = "8095b8b50f9b0a11b8ce335c767a607a9fa866752e0d34cc0895f493f0dda1f6"

doc = sc.doc
if doc is None:
    raise RuntimeError("No active Rhino document.")

# The bridge targets a dedicated document before this payload runs.
repo_root = os.path.join(os.path.expanduser("~"), "bin", "mcp", "rhino-cad-mcp")
texture_path = os.path.join(repo_root, LABEL_RELATIVE_PATH)
if not os.path.isfile(texture_path):
    raise RuntimeError("Label texture is missing: " + texture_path)

with open(texture_path, "rb") as f:
    actual_label_sha = hashlib.sha256(f.read()).hexdigest()
if actual_label_sha != LABEL_SHA256:
    raise RuntimeError("Label texture SHA-256 mismatch.")

def ensure_layer(name, color):
    idx = doc.Layers.FindByFullPath(name, -1)
    if idx >= 0:
        return idx
    layer = Rhino.DocObjects.Layer()
    layer.Name = name
    layer.Color = color
    idx = doc.Layers.Add(layer)
    if idx < 0:
        raise RuntimeError("Failed to create layer: " + name)
    return idx

def add_material(name, diffuse, transparency=0.0, bitmap_path=None):
    mat = Rhino.DocObjects.Material()
    mat.Name = name
    mat.DiffuseColor = diffuse
    mat.Transparency = float(transparency)
    if bitmap_path is not None:
        if not mat.SetBitmapTexture(bitmap_path):
            raise RuntimeError("Failed to attach bitmap texture: " + bitmap_path)
    idx = doc.Materials.Add(mat)
    if idx < 0:
        raise RuntimeError("Failed to add material: " + name)
    return idx

def add_brep(brep, name, layer_idx, material_idx, metadata, require_solid=True):
    if brep is None or not brep.IsValid:
        raise RuntimeError("Invalid Brep for " + name)
    if require_solid and not brep.IsSolid:
        raise RuntimeError("Expected solid Brep for " + name)
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.Name = name
    attrs.LayerIndex = layer_idx
    attrs.MaterialIndex = material_idx
    attrs.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
    for key, value in metadata.items():
        attrs.SetUserString(str(key), str(value))
    gid = doc.Objects.AddBrep(brep, attrs)
    if gid == System.Guid.Empty:
        raise RuntimeError("Failed to add " + name)
    return gid

def make_lofted_solid(section_specs):
    curves = []
    for z, radius in section_specs:
        plane = Rhino.Geometry.Plane(
            Rhino.Geometry.Point3d(0.0, 0.0, float(z)),
            Rhino.Geometry.Vector3d.ZAxis
        )
        curves.append(Rhino.Geometry.Circle(plane, float(radius)).ToNurbsCurve())

    lofts = Rhino.Geometry.Brep.CreateFromLoft(
        curves,
        Rhino.Geometry.Point3d.Unset,
        Rhino.Geometry.Point3d.Unset,
        Rhino.Geometry.LoftType.Normal,
        False
    )
    if lofts is None or len(lofts) != 1:
        raise RuntimeError("Bottle loft did not return exactly one Brep.")

    capped = lofts[0].CapPlanarHoles(doc.ModelAbsoluteTolerance)
    if capped is None or not capped.IsValid or not capped.IsSolid:
        raise RuntimeError("Bottle body failed capping/solid validation.")
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

def set_cylindrical_mapping(guid, cylinder):
    obj = doc.Objects.FindId(guid)
    if obj is None:
        raise RuntimeError("Could not find label object for texture mapping.")
    mapping = Rhino.Render.TextureMapping.CreateCylinderMapping(cylinder, False)
    if mapping is None:
        raise RuntimeError("Failed to create cylindrical texture mapping.")
    if not doc.Objects.ModifyTextureMapping(obj, 1, mapping):
        raise RuntimeError("Failed to assign cylindrical texture mapping.")

def volume_of(guid):
    obj = doc.Objects.FindId(guid)
    if obj is None:
        return None
    brep = obj.Geometry
    if not isinstance(brep, Rhino.Geometry.Brep):
        return None
    props = Rhino.Geometry.VolumeMassProperties.Compute(brep)
    return props.Volume if props else None

# ---- Layers and materials ---------------------------------------------------

bottle_layer = ensure_layer("ZESTLY_BOTTLE", Color.FromArgb(105, 170, 135))
label_layer = ensure_layer("ZESTLY_LABEL", Color.FromArgb(20, 210, 120))
cap_layer = ensure_layer("ZESTLY_CAP", Color.FromArgb(50, 205, 95))
detail_layer = ensure_layer("ZESTLY_DETAILS", Color.FromArgb(50, 50, 55))

pet_mat = add_material("Zestly PET Clear", Color.FromArgb(210, 235, 220), 0.72)
cap_mat = add_material("Zestly Cap Green", Color.FromArgb(35, 190, 75), 0.0)
label_mat = add_material("Zestly Lemon Lime Label", Color.White, 0.0, texture_path)

common = {
    "created_by": "chatgpt-web-controller",
    "task_id": TASK_ID,
    "modeling_run_id": MODELING_RUN_ID,
    "pass_index": "1",
    "pass_kind": "foundation"
}

# ---- Bottle exterior --------------------------------------------------------

# Exterior design proxy, approximately 500 mL class.
# The foundation pass intentionally prioritizes silhouette and packaging zones.
sections = [
    (0.0, 27.5),
    (3.0, 31.2),
    (9.0, 33.1),
    (22.0, 33.6),
    (55.0, 33.4),
    (82.0, 32.6),
    (110.0, 32.0),
    (138.0, 32.5),
    (154.0, 33.0),
    (164.0, 31.5),
    (173.0, 28.5),
    (181.0, 24.5),
    (188.0, 19.5),
    (194.0, 15.2),
    (202.0, 14.6)
]
body = make_lofted_solid(sections)
meta = dict(common)
meta.update({"role": "bottle_body", "nominal_volume_ml": "500"})
body_id = add_brep(body, "Zestly PET Bottle Body", bottle_layer, pet_mat, meta)

neck_brep, _ = cylinder_brep(14.8, 196.0, 9.0, True, True)
meta = dict(common)
meta["role"] = "neck_finish"
neck_id = add_brep(neck_brep, "Zestly Neck Finish", bottle_layer, pet_mat, meta)

# ---- Printed wrap label -----------------------------------------------------

label_radius = 33.85
label_z0 = 58.0
label_height = 88.0
label_brep, label_cyl = cylinder_brep(label_radius, label_z0, label_height, False, False)
meta = dict(common)
meta.update({
    "role": "printed_label_sleeve",
    "source_asset": LABEL_RELATIVE_PATH,
    "texture_sha256": LABEL_SHA256
})
label_id = add_brep(
    label_brep,
    "Zestly Printed Label Sleeve",
    label_layer,
    label_mat,
    meta,
    require_solid=False
)
set_cylindrical_mapping(label_id, label_cyl)

# ---- Cap and tamper ring ----------------------------------------------------

cap_brep, _ = cylinder_brep(17.1, 203.0, 16.5, True, True)
meta = dict(common)
meta["role"] = "screw_cap"
cap_id = add_brep(cap_brep, "Zestly Screw Cap", cap_layer, cap_mat, meta)

tamper_brep, _ = cylinder_brep(17.4, 200.0, 3.2, True, True)
meta = dict(common)
meta["role"] = "tamper_ring"
tamper_id = add_brep(tamper_brep, "Zestly Tamper Ring", cap_layer, cap_mat, meta)

# Foundation-level cap grip ribs.
rib_ids = []
rib_count = 28
for i in range(rib_count):
    angle = 2.0 * math.pi * float(i) / float(rib_count)
    cx = 17.55 * math.cos(angle)
    cy = 17.55 * math.sin(angle)

    box = Rhino.Geometry.Box(
        Rhino.Geometry.Plane.WorldXY,
        Rhino.Geometry.Interval(-0.55, 0.55),
        Rhino.Geometry.Interval(-1.25, 1.25),
        Rhino.Geometry.Interval(204.2, 218.2)
    )
    rib = box.ToBrep()
    rib.Transform(
        Rhino.Geometry.Transform.Rotation(
            angle,
            Rhino.Geometry.Vector3d.ZAxis,
            Rhino.Geometry.Point3d.Origin
        )
    )
    rib.Transform(Rhino.Geometry.Transform.Translation(cx, cy, 0.0))

    meta = dict(common)
    meta.update({"role": "cap_grip_rib", "rib_index": str(i)})
    gid = add_brep(
        rib,
        "Zestly Cap Rib %02d" % (i + 1),
        detail_layer,
        cap_mat,
        meta
    )
    rib_ids.append(str(gid))

# Base contact ring gives a readable lower edge without attempting the
# petaloid bottom in Pass 1.
base_ring_brep, _ = cylinder_brep(29.1, 0.6, 1.4, True, True)
meta = dict(common)
meta["role"] = "base_contact_ring"
base_ring_id = add_brep(
    base_ring_brep,
    "Zestly Base Contact Ring",
    detail_layer,
    pet_mat,
    meta
)

doc.Strings.SetString("RHINO_CHATGPT", "modeling_run_id", MODELING_RUN_ID)
doc.Strings.SetString("RHINO_CHATGPT", "task_id", TASK_ID)
doc.Strings.SetString("RHINO_CHATGPT", "model_name", "Zestly Modern Soda Bottle")
doc.Strings.SetString("RHINO_CHATGPT", "pass_kind", "foundation")
doc.Views.Redraw()

bbox = body.GetBoundingBox(True)

result = {
    "ok": True,
    "task_id": TASK_ID,
    "modeling_run_id": MODELING_RUN_ID,
    "pass_index": 1,
    "pass_kind": "foundation",
    "model_name": "Zestly Modern Soda Bottle",
    "units_expected": "millimeters",
    "label_asset": {
        "path": texture_path,
        "repo_relative_path": LABEL_RELATIVE_PATH,
        "sha256": LABEL_SHA256,
        "texture_dimensions_px": [256, 67]
    },
    "objects": {
        "body": str(body_id),
        "neck_finish": str(neck_id),
        "label_sleeve": str(label_id),
        "cap": str(cap_id),
        "tamper_ring": str(tamper_id),
        "base_contact_ring": str(base_ring_id),
        "cap_ribs": rib_ids
    },
    "body_bbox": {
        "min": [bbox.Min.X, bbox.Min.Y, bbox.Min.Z],
        "max": [bbox.Max.X, bbox.Max.Y, bbox.Max.Z]
    },
    "body_volume_mm3": volume_of(body_id),
    "overall_nominal_height_mm": 219.5,
    "max_nominal_diameter_mm": 67.2,
    "notes": [
        "Foundation pass: primary bottle silhouette, neck, separate cap, tamper ring, printed wrap label, and coarse cap grip detail.",
        "The bottle is an exterior solid design proxy, not a hollow manufacturing model yet.",
        "Petaloid bottom sculpting, actual thread geometry, wall thickness, and fine seam alignment are intentionally deferred to controller-authored correction/detail passes."
    ]
}
