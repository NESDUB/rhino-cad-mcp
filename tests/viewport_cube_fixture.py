"""Build a six-color orientation cube for viewport/camera regression tests."""
import Rhino, scriptcontext as sc, System
G = Rhino.Geometry

size = 20.0
t = 0.35
origin = G.Point3d(-size/2.0, -size/2.0, -size/2.0)
faces = [
    ('+X_RIGHT', System.Drawing.Color.Red, G.Point3d(size/2.0-t, -size/2.0, -size/2.0), G.Point3d(size/2.0, size/2.0, size/2.0)),
    ('-X_LEFT', System.Drawing.Color.Blue, G.Point3d(-size/2.0, -size/2.0, -size/2.0), G.Point3d(-size/2.0+t, size/2.0, size/2.0)),
    ('+Y_BACK', System.Drawing.Color.Green, G.Point3d(-size/2.0, size/2.0-t, -size/2.0), G.Point3d(size/2.0, size/2.0, size/2.0)),
    ('-Y_FRONT', System.Drawing.Color.Yellow, G.Point3d(-size/2.0, -size/2.0, -size/2.0), G.Point3d(size/2.0, -size/2.0+t, size/2.0)),
    ('+Z_TOP', System.Drawing.Color.Magenta, G.Point3d(-size/2.0, -size/2.0, size/2.0-t), G.Point3d(size/2.0, size/2.0, size/2.0)),
    ('-Z_BOTTOM', System.Drawing.Color.Cyan, G.Point3d(-size/2.0, -size/2.0, -size/2.0), G.Point3d(size/2.0, size/2.0, -size/2.0+t)),
]
ids = []
for name, color, a, b in faces:
    # Assign both object color and a true PBR render material. ObjectColor is
    # useful in Wireframe/Arctic-style modes; RenderMaterial is what Rendered
    # mode actually consumes.
    mat = Rhino.DocObjects.Material(); mat.Name = 'ViewportFixture_' + name; mat.DiffuseColor = color; mat.ToPhysicallyBased()
    p = mat.PhysicallyBased
    p.BaseColor = Rhino.Display.Color4f(color.R/255.0, color.G/255.0, color.B/255.0, 1.0)
    p.Roughness = 0.28; p.Clearcoat = 0.15; p.ClearcoatRoughness = 0.1
    mi = sc.doc.Materials.Add(mat)
    render_mat = Rhino.Render.RenderMaterial.FromMaterial(mat, sc.doc)
    render_mat.Name = 'ViewportFixture_' + name
    sc.doc.RenderMaterials.Add(render_mat)
    box = G.Box(G.BoundingBox(a, b)).ToBrep()
    attrs = Rhino.DocObjects.ObjectAttributes(); attrs.Name = name; attrs.LayerIndex = sc.doc.Layers.CurrentLayerIndex; attrs.MaterialIndex = mi
    attrs.ObjectColor = color; attrs.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attrs.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
    oid = sc.doc.Objects.AddBrep(box, attrs)
    obj = sc.doc.Objects.FindId(oid); obj.RenderMaterial = render_mat; obj.CommitChanges(); ids.append(str(oid))
sc.doc.Views.Redraw()
result = {'fixture': 'six_color_orientation_cube', 'size': size, 'faces': [x[0] for x in faces], 'object_ids': ids}
