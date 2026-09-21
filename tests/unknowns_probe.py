"""Read-only Rhino capability probes; output is captured by mcp_client."""
import Rhino, scriptcontext as sc, System, clr
G = Rhino.Geometry

def methods(t, names):
    return [str(m) for m in t.GetMethods() if any(n in m.Name for n in names)]

result = {}
result['doc'] = {
    'serial': int(sc.doc.RuntimeSerialNumber),
    'headless': bool(sc.doc.IsHeadless),
    'path': sc.doc.Path,
    'has_active_view': sc.doc.Views.ActiveView is not None,
    'objects': int(sc.doc.Objects.Count),
}
result['api'] = {}
for key, typ, names in [
    ('brep_boolean', G.Brep, ['Boolean', 'CreateBoolean']),
    ('brep_offset', G.Brep, ['Offset']),
    ('brep_fillet', G.Brep, ['Fillet']),
    ('curve_offset', G.Curve, ['Offset']),
    ('viewport_capture', getattr(Rhino.Display, 'RhinoViewport', None), ['Capture', 'SetCamera', 'ChangeTo']),
    ('object_attrs', Rhino.DocObjects.ObjectAttributes, ['ToJSON', 'UserString', 'DataCRC']),
]:
    try: result['api'][key] = methods(clr.GetClrType(typ), names)
    except Exception as exc: result['api'][key] = {'error': str(exc)}
s = G.Sphere(G.Point3d.Origin, 5).ToBrep()
result['geometry'] = {
    'sphere_valid': bool(s.IsValid),
    'sphere_solid': bool(s.IsSolid),
    'sphere_bbox_true': str(s.GetBoundingBox(True)),
    'sphere_bbox_false': str(s.GetBoundingBox(False)),
    'sphere_volume': float(G.VolumeMassProperties.Compute(s).Volume),
    'duplicate_geometry_equals': bool(G.GeometryBase.GeometryEquals(s, s.DuplicateBrep())),
}
result['units'] = {
    'model': str(sc.doc.ModelUnitSystem),
    'absolute': float(sc.doc.ModelAbsoluteTolerance),
    'relative': float(sc.doc.ModelRelativeTolerance),
    'angle_degrees': float(sc.doc.ModelAngleToleranceDegrees),
}
if sc.doc.Views.ActiveView:
    v = sc.doc.Views.ActiveView.ActiveViewport
    result['viewport'] = {
        'name': v.Name, 'display_mode': v.DisplayMode.EnglishName,
        'parallel': bool(v.IsParallelProjection),
        'camera': [v.CameraLocation.X, v.CameraLocation.Y, v.CameraLocation.Z],
        'target': [v.CameraTarget.X, v.CameraTarget.Y, v.CameraTarget.Z],
    }
