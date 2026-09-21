"""Probe 2: mixed payload handling, item positions and branch-local effects.
Private documents; no Rhino geometry or active canvas edits; Python 3.9.
"""
from pathlib import Path
import json,time,traceback
ROOT=Path('/Users/nes/bin/mcp/rhino-cad-mcp/tests/gh_compatibility_poc')
exec(compile((ROOT/'operation_errors_probe.py').read_text().split('\nbefore=Rhino.RhinoDoc.ActiveDoc')[0],'diagnostic_helpers','exec'))

def valid(z):return T.GH_Curve(G.Circle(G.Plane(G.Point3d(0,0,z),G.Vector3d.ZAxis),5).ToNurbsCurve())
def invalid():return T.GH_Curve(G.LineCurve(G.Point3d.Origin,G.Point3d.Origin))
def fixture(kind):
    a=valid(0);b=valid(10)
    if kind=='valid':return [a,b]
    if kind=='null':return [a,None,b]
    if kind=='incompatible':return [a,T.GH_String('NOT_A_CURVE'),b]
    if kind=='invalid':return [a,invalid(),b]
    mixed=[a,None,T.GH_String('NOT_A_CURVE'),invalid(),b]
    return list(reversed(mixed)) if kind=='mixed_reversed' else mixed

def tree_snapshot(tree):return [{'path':str(tree.Paths[i]),'items':[datum(g) for g in tree.Branches[i]]} for i in range(tree.PathCount)]

def snap(source,relay,receiver):return {'source':snapshot(source),'relay':snapshot(relay),'receiver':snapshot(receiver)}
before=Rhino.RhinoDoc.ActiveDoc;ids=sorted(str(o.Id) for o in before.Objects if not o.IsDeleted)
canvas=None if GH.Instances.ActiveCanvas is None else GH.Instances.ActiveCanvas.Document
report={'runtime':str(GH.Instances.ComponentServer.GetType().Assembly.FullName),'runs':[],'fixture_note':'Branch {0} varies; branch {7} always contains two valid circular curves at Z=30 and Z=40. Radius 5. Invalid curve is coincident-endpoint line. Incompatible string is NOT_A_CURVE.'}
for repetition in range(2):
 for kind in ['valid','null','incompatible','invalid','mixed','mixed_reversed']:
  for operation in ['Divide Curve','Loft']:
   d=GH_Document();d.Enabled=True
   row={'kind':kind,'operation':operation,'repeat':repetition}
   try:
    if not GH_Document.EnableSolutions:raise RuntimeError('Global solutions disabled')
    s=P.Param_GenericObject();s.CreateAttributes()
    raw=fixture(kind)
    row['intended']=[{'index':i,'value':datum(v)} for i,v in enumerate(raw)]
    for v in raw:s.PersistentData.Append(v,GH_Path(0))
    for v in [valid(30),valid(40)]:s.PersistentData.Append(v,GH_Path(7))
    row['persistent_before_solve']=tree_snapshot(s.PersistentData)
    d.AddObject(s,False)
    relay=P.Param_Curve();relay.CreateAttributes();d.AddObject(relay,False);relay.AddSource(s)
    receiver=comp(d,operation);receiver.Params.Input[0].AddSource(relay)
    if operation=='Divide Curve':feed(d,receiver,1,P.Param_Integer,[T.GH_Integer(2)])
    solve(d);row['state']=snap(s,relay,receiver);row['solver']=str(d.SolutionState)
   except Exception:row['harness_exception']=traceback.format_exc()
   finally:d.Dispose()
   report['runs'].append(row)
report['isolation']={'same_rhino':before==Rhino.RhinoDoc.ActiveDoc,'same_objects':ids==sorted(str(o.Id) for o in before.Objects if not o.IsDeleted),'same_canvas':canvas==(None if GH.Instances.ActiveCanvas is None else GH.Instances.ActiveCanvas.Document)}
p=ROOT/('mixed_items_'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,indent=2,default=str))
result={'path':str(p),'runs':len(report['runs']),'exceptions':[r for r in report['runs'] if 'harness_exception' in r],'isolation':report['isolation']}
