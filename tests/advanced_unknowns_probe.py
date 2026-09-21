"""Isolated, failure-tolerant RhinoCommon probes for undocumented behavior."""
import Rhino, scriptcontext as sc, System, traceback
G = Rhino.Geometry

old = sc.doc
d = Rhino.RhinoDoc.CreateHeadless(None)
sc.doc = d
results = {}

def probe(name, fn):
    try:
        results[name] = {'ok': True, 'value': fn()}
    except Exception as exc:
        results[name] = {'ok': False, 'error': str(exc), 'traceback': traceback.format_exc()}

try:
    box = G.Box(G.BoundingBox(G.Point3d(-5,-5,-5), G.Point3d(5,5,5))).ToBrep()
    sphere = G.Sphere(G.Point3d(3,0,0), 4).ToBrep()
    box_id = d.Objects.AddBrep(box)
    sphere_id = d.Objects.AddBrep(sphere)

    probe('transform_duplicate', lambda: {
        'equals_before': bool(G.GeometryBase.GeometryEquals(box, box.DuplicateBrep())),
        'moved_bbox': str((lambda g: (g.Transform(G.Transform.Translation(20,0,0)), g.GetBoundingBox(False))[1])(box.DuplicateBrep()))
    })
    probe('boolean_intersection', lambda: {
        'count': len(G.Brep.CreateBooleanIntersection(box, sphere, d.ModelAbsoluteTolerance) or []),
        'volume': sum(abs(G.VolumeMassProperties.Compute(x).Volume) for x in (G.Brep.CreateBooleanIntersection(box, sphere, d.ModelAbsoluteTolerance) or []))
    })
    probe('mesh_conversion', lambda: {
        'meshes': len(G.Mesh.CreateFromBrep(box, G.MeshingParameters.Default) or []),
        'parts_closed': [bool(m.IsClosed) for m in (G.Mesh.CreateFromBrep(box, G.MeshingParameters.Default) or [])],
        'joined': (lambda ms: (lambda j: {'vertices': j.Vertices.Count, 'faces': j.Faces.Count, 'closed': bool(j.IsClosed), 'manifold': bool(j.IsManifold), 'valid': bool(j.IsValid)})( (lambda j: ( [j.Append(m) for m in ms], j.Vertices.CombineIdentical(True,True), j.UnifyNormals(), j.Normals.ComputeNormals(), j.Compact(), j)[-1])(G.Mesh()) ))(G.Mesh.CreateFromBrep(box, G.MeshingParameters.Default) or [])
    })
    probe('brep_offset', lambda: {
        'overload_return': str(type(G.Brep.CreateOffsetBrep(box, 0.5, False, True, True, d.ModelAbsoluteTolerance))),
        'count': len(G.Brep.CreateOffsetBrep(box, 0.5, False, True, True, d.ModelAbsoluteTolerance)[0] or []),
        'flags': {'solid': False, 'extend': True, 'smooth': True}
    })
    probe('curve_offset', lambda: {
        'count': len(G.LineCurve(G.Point3d(-2,0,0), G.Point3d(2,0,0)).Offset(G.Plane.WorldXY, 1.0, d.ModelAbsoluteTolerance, G.CurveOffsetCornerStyle.Sharp) or [])
    })
    probe('groups_and_layers', lambda: {
        'layer': d.Layers.Add('Probe Layer', System.Drawing.Color.Orange),
        'group': d.Groups.Add('Probe Group'),
    })
    probe('object_attributes', lambda: {
        'set_user_string': bool(d.Objects.FindId(box_id).Attributes.SetUserString('probe', 'yes')),
        'group_membership': bool(d.Groups.AddToGroup(0, box_id)) if d.Groups.Count else False,
    })
    probe('render_material_simulation', lambda: {
        'legacy_material_count': int(d.Materials.Count),
        'render_material_count': int(d.RenderMaterials.Count),
    })
    result = {'document': {'headless': bool(d.IsHeadless), 'serial': int(d.RuntimeSerialNumber), 'units': str(d.ModelUnitSystem), 'tolerance': d.ModelAbsoluteTolerance}, 'object_ids': [str(box_id), str(sphere_id)], 'probes': results}
finally:
    d.Dispose()
    sc.doc = old
