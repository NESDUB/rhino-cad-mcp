"""Observable pipeline boundaries; staged calls compared with a normal solve.
Private GH documents; Python 3.9; does not intercept internal casting calls.
"""
import json,time,traceback
from pathlib import Path
ROOT=Path('/Users/nes/bin/mcp/rhino-cad-mcp/tests/gh_compatibility_poc')
# Reuse the preserved diagnostic serializer and fixture helpers, not its tests.
helper=(ROOT/'operation_errors_probe.py').read_text().split('\nbefore=Rhino.RhinoDoc.ActiveDoc')[0]
exec(compile(helper,'operation_errors_probe_helpers','exec'))
original_datum=datum
def datum(g):
    r=original_datum(g)
    if g is None:return r
    prop=g.GetType().GetProperty('Value');v=prop.GetValue(g) if prop else None
    if isinstance(v,G.Circle):
        r['measurements']={'radius':v.Radius,'center':[v.Center.X,v.Center.Y,v.Center.Z]}
    elif isinstance(v,G.GeometryBase):
        b=v.GetBoundingBox(True)
        if b.IsValid:r['measurements']={'bounds_min':[b.Min.X,b.Min.Y,b.Min.Z],'bounds_max':[b.Max.X,b.Max.Y,b.Max.Z]}
        if isinstance(v,G.Brep):
            r['measurements']['faces']=v.Faces.Count
            amp=G.AreaMassProperties.Compute(v)
            if amp:r['measurements']['area']=amp.Area;amp.Dispose()
    return r
IDS['Addition']='58669268-a825-4688-8072-7d3508fcf91c'
before=Rhino.RhinoDoc.ActiveDoc
before_ids=sorted(str(o.Id) for o in before.Objects if not o.IsDeleted)
canvas=None if GH.Instances.ActiveCanvas is None else GH.Instances.ActiveCanvas.Document
report={'runtime':str(GH.Instances.ComponentServer.GetType().Assembly.FullName),'runs':[],'scope':'Observable boundaries only; no internal cast-order or generic item-lineage claim'}
def observe(s,r):return {'source':snapshot(s),'receiver':snapshot(r)}
for repeat in range(2):
 for case in ['circle_to_loft_success','circle_to_loft_insufficient','circle_to_brep_edges','addition_to_brep_edges']:
  for mode in ['staged','normal']:
   d=GH_Document();d.Enabled=True
   row={'case':case,'repeat':repeat,'mode':mode,'stages':[]}
   try:
    if not GH_Document.EnableSolutions:raise RuntimeError('Global solver disabled')
    if case=='addition_to_brep_edges':
     s=comp(d,'Addition');r=comp(d,'Brep Edges')
     feed(d,s,0,P.Param_Number,[T.GH_Number(2)]);feed(d,s,1,P.Param_Number,[T.GH_Number(3)])
    else:
     s=comp(d,'Circle');r=comp(d,'Brep Edges' if case=='circle_to_brep_edges' else 'Loft')
     zs=[0,10] if case=='circle_to_loft_success' else [0]
     feed(d,s,0,P.Param_Plane,[T.GH_Plane(G.Plane(G.Point3d(0,0,z),G.Vector3d.ZAxis)) for z in zs])
     feed(d,s,1,P.Param_Number,[T.GH_Number(5)])
    r.Params.Input[0].AddSource(s.Params.Output[0])
    row['connection']={'source_component':str(s.InstanceGuid),'source_pin':str(s.Params.Output[0].InstanceGuid),'receiver_component':str(r.InstanceGuid),'receiver_pin':str(r.Params.Input[0].InstanceGuid),'source_index':0,'target_index':0}
    def capture(label):row['stages'].append({'label':label,'state':observe(s,r)})
    capture('wired_unsolved')
    if mode=='staged':
     s.CollectData();capture('source_collect')
     s.ComputeData();capture('source_compute')
     r.CollectData();capture('receiver_collect')
     r.ComputeData();capture('receiver_compute')
    else:
     solve(d);capture('normal_solution')
    row['document_solution_state']=str(d.SolutionState)
   except Exception:row['harness_exception']=traceback.format_exc()
   finally:d.Dispose()
   report['runs'].append(row)
report['isolation']={'same_rhino':before==Rhino.RhinoDoc.ActiveDoc,'same_objects':before_ids==sorted(str(o.Id) for o in before.Objects if not o.IsDeleted),'same_canvas':canvas==(None if GH.Instances.ActiveCanvas is None else GH.Instances.ActiveCanvas.Document)}
p=ROOT/('value_trace_'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,indent=2,default=str))
result={'path':str(p),'runs':len(report['runs']),'exceptions':[r for r in report['runs'] if 'harness_exception' in r],'isolation':report['isolation']}
