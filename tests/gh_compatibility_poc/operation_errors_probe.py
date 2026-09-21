"""Operation diagnostics, partial results, tree topology and repair lifecycle.
Rhino Python 3.9; private GH documents only; no subprocesses or UI commands.
"""
import json,time,traceback,math
from pathlib import Path
import System,Rhino,Grasshopper as GH
from Grasshopper.Kernel import GH_Document,GH_RuntimeMessageLevel as L
from Grasshopper.Kernel.Data import GH_Path
from Grasshopper.Kernel import Types as T,Parameters as P
G=Rhino.Geometry
ROOT=Path('/Users/nes/bin/mcp/rhino-cad-mcp/tests/gh_compatibility_poc')
IDS={'Loft':'a7a41d0a-2188-4f7a-82cc-1a2c4e4ec850','Circle':'807b86e3-be8d-4970-92b5-f8cdcb45b06b','Divide Curve':'2162e72e-72fc-4bf8-9459-d4d82fa8aa14','List Item':'59daf374-bc21-4a5e-8282-5504fb7ae9ae','Interpolate':'2b2a4145-3dff-41d4-a8de-1ea9d29eef33','Line':'4c4e56eb-2f04-43f9-95a3-cc46a14f495a','Curve | Curve':'84627490-0fb2-4498-8138-ad134ee4cb36','Division':'ec875825-61e4-4c1c-a343-0e0cee0b321b','Boundary Surfaces':'d51e9b65-aa4e-4fd6-976c-cef35d421d05','Division Generic':'9c85271f-89fa-4e9f-9f4a-d75802120ccc','Division Complex':'cb4ec4a1-f48e-4685-b58c-72ed27b53681','Brep Edges':'0148a65d-6f42-414a-9db7-9a9b2eb78437'}

def datum(g):
    if g is None:return {'null':True}
    r={'null':False,'type':str(g.GetType().FullName),'text':str(g),'valid':bool(g.IsValid),'why_not':g.IsValidWhyNot}
    try:
        prop=g.GetType().GetProperty('Value');native=prop.GetValue(g) if prop else None
        if isinstance(native,(float,int)):
            r['native_number']={'representation':repr(native),'finite':math.isfinite(native),'equals_double_max':native==System.Double.MaxValue}
        if isinstance(native,G.Circle):r['geometry']={'radius':native.Radius,'valid':native.IsValid}
        if isinstance(native,G.Line):r['geometry']={'length':native.Length,'valid':native.IsValid}
        if isinstance(native,G.Curve):r['geometry']={'closed':native.IsClosed,'planar_at_0_01':native.IsPlanar(.01),'length':native.GetLength(),'valid':native.IsValid}
        if isinstance(native,G.GeometryBase) and not native.IsValid:
            args=System.Array[System.Object]([None]);method=native.GetType().GetMethod('IsValidWithLog')
            if method:r['native_valid']=bool(method.Invoke(native,args));r['native_validation_log']=str(args[0])
    except Exception as e:r['native_log_probe_error']=str(e)
    return r

def snapshot(o):
    r={'name':o.Name,'instance_id':str(o.InstanceGuid),'level':str(o.RuntimeMessageLevel),'remarks':list(o.RuntimeMessages(L.Remark)),'warnings':list(o.RuntimeMessages(L.Warning)),'errors':list(o.RuntimeMessages(L.Error)),'phase':str(o.Phase),'processor_ms':o.ProcessorTime.TotalMilliseconds}
    if hasattr(o,'Params'):
        r.update(component_guid=str(o.ComponentGuid),component_type=str(o.GetType().FullName),assembly=str(o.GetType().Assembly.FullName),obsolete=bool(o.Obsolete) if hasattr(o,'Obsolete') else None,exposure=str(o.Exposure),run_count=int(o.RunCount),message=o.Message,inputs=[snapshot(p) for p in o.Params.Input],outputs=[snapshot(p) for p in o.Params.Output])
    if hasattr(o,'VolatileData'):
        tree=o.VolatileData
        r.update(declared_type=o.TypeName,access=str(o.Access),optional=o.Optional,sources=int(o.SourceCount),raw_count=int(o.VolatileDataCount),tree=[{'path':str(tree.Paths[i]),'items':[datum(g) for g in tree.Branches[i]]} for i in range(tree.PathCount)])
        data=[g for g in tree.AllData(False)];r['null_count']=sum(g is None for g in data);r['valid_count']=sum(g is not None and g.IsValid for g in data)
    return r

def comp(d,name):
    o=GH.Instances.ComponentServer.EmitObjectProxy(System.Guid(IDS[name])).CreateInstance();o.CreateAttributes();d.AddObject(o,False);return o

def source(d,cls,branches):
    p=cls();p.CreateAttributes()
    for index,items in branches:
        for item in items:p.PersistentData.Append(item,GH_Path(index))
    d.AddObject(p,False);return p

def feed(d,c,index,cls,items):
    p=source(d,cls,[(0,items)]);c.Params.Input[index].AddSource(p);return p

def circle(z=0,x=0):return T.GH_Curve(G.Circle(G.Plane(G.Point3d(x,0,z),G.Vector3d.ZAxis),5).ToNurbsCurve())
def point(x,y,z):return T.GH_Point(G.Point3d(x,y,z))
def solve(d):
    if not GH_Document.EnableSolutions:raise RuntimeError('Global solver disabled; leaving it untouched')
    d.NewSolution(False)
    if str(d.SolutionState)!='PostProcess':raise RuntimeError('Solve did not finish')

before=Rhino.RhinoDoc.ActiveDoc
before_ids=sorted(str(o.Id) for o in before.Objects if not o.IsDeleted)
canvas_before=None if GH.Instances.ActiveCanvas is None else GH.Instances.ActiveCanvas.Document
report={'runtime':{'rhino':str(Rhino.RhinoApp.Version),'gh':str(GH.Instances.ComponentServer.GetType().Assembly.FullName)},'ids':IDS,'cases':[],'repairs':[]}
cases=['division_generic_by_zero','division_complex_by_zero','loft_two_same_branch','boundary_invalid_curve','loft_single','loft_split_branches','loft_mixed_branches','circle_zero','circle_negative','divide_zero','divide_negative','interpolate_one_point','interpolate_bad_degree','line_coincident','list_out_of_range','division_by_zero','boundary_open','boundary_nonplanar','intersection_empty','upstream_failure_cascade']
for repetition in range(2):
    for case in cases:
        d=GH_Document();d.Enabled=True
        try:
            upstream=None
            if case.startswith('loft_') or case=='upstream_failure_cascade':
                c=comp(d,'Loft')
                branches=[(0,[circle()])]
                if case=='loft_two_same_branch':branches=[(0,[circle(),circle(10)])]
                if case=='loft_split_branches':branches=[(0,[circle()]),(1,[circle(10)])]
                if case=='loft_mixed_branches':branches=[(0,[circle(),circle(10)]),(1,[circle(20)]),(2,[circle(30)])]
                s=source(d,P.Param_Curve,branches);c.Params.Input[0].AddSource(s)
                if case=='upstream_failure_cascade':
                    upstream=c;c=comp(d,'Brep Edges');c.Params.Input[0].AddSource(upstream.Params.Output[0])
            elif case.startswith('circle_'):
                c=comp(d,'Circle');feed(d,c,1,P.Param_Number,[T.GH_Number(0 if case=='circle_zero' else -5)])
            elif case.startswith('divide_'):
                c=comp(d,'Divide Curve');feed(d,c,0,P.Param_Curve,[circle()]);feed(d,c,1,P.Param_Integer,[T.GH_Integer(0 if case=='divide_zero' else -2)])
            elif case.startswith('interpolate_'):
                c=comp(d,'Interpolate');pts=[point(0,0,0)] if case=='interpolate_one_point' else [point(0,0,0),point(1,2,0),point(3,1,0),point(5,0,0)]
                feed(d,c,0,P.Param_Point,pts)
                if case=='interpolate_bad_degree':feed(d,c,1,P.Param_Integer,[T.GH_Integer(0)])
            elif case=='line_coincident':
                c=comp(d,'Line');feed(d,c,0,P.Param_Point,[point(0,0,0)]);feed(d,c,1,P.Param_Point,[point(0,0,0)])
            elif case=='list_out_of_range':
                c=comp(d,'List Item');feed(d,c,0,P.Param_Number,[T.GH_Number(7)]);feed(d,c,1,P.Param_Integer,[T.GH_Integer(99)]);feed(d,c,2,P.Param_Boolean,[T.GH_Boolean(False)])
            elif case in ['division_by_zero','division_generic_by_zero','division_complex_by_zero']:
                key={'division_by_zero':'Division','division_generic_by_zero':'Division Generic','division_complex_by_zero':'Division Complex'}[case]
                c=comp(d,key);feed(d,c,0,P.Param_Number,[T.GH_Number(1)]);feed(d,c,1,P.Param_Number,[T.GH_Number(0)])
            elif case=='boundary_invalid_curve':
                c=comp(d,'Boundary Surfaces');feed(d,c,0,P.Param_Curve,[T.GH_Curve(G.LineCurve(G.Point3d.Origin,G.Point3d.Origin))])
            elif case=='boundary_open':
                c=comp(d,'Boundary Surfaces');feed(d,c,0,P.Param_Curve,[T.GH_Curve(G.LineCurve(G.Point3d.Origin,G.Point3d(10,0,0)))])
            elif case=='boundary_nonplanar':
                c=comp(d,'Boundary Surfaces');ps=[G.Point3d(0,0,0),G.Point3d(10,0,0),G.Point3d(10,10,3),G.Point3d(0,10,0),G.Point3d(0,0,0)];feed(d,c,0,P.Param_Curve,[T.GH_Curve(G.PolylineCurve(ps))])
            elif case=='intersection_empty':
                c=comp(d,'Curve | Curve');feed(d,c,0,P.Param_Curve,[circle()]);feed(d,c,1,P.Param_Curve,[circle(0,30)])
            solve(d)
            report['cases'].append({'case':case,'repeat':repetition,'solver':str(d.SolutionState),'component':snapshot(c),'upstream':snapshot(upstream) if upstream else None})
        except Exception:report['cases'].append({'case':case,'repeat':repetition,'harness_exception':traceback.format_exc()})
        finally:d.Dispose()
    # Same objects, repaired persistent data, explicitly expire and re-solve.
    d=GH_Document();d.Enabled=True
    try:
        c=comp(d,'Loft');s=feed(d,c,0,P.Param_Curve,[circle()]);solve(d);bad=snapshot(c)
        s.PersistentData.Append(circle(10),GH_Path(0));s.ExpireSolution(False);solve(d);good=snapshot(c)
        report['repairs'].append({'repeat':repetition,'before':bad,'after':good})
    except Exception:report['repairs'].append({'repeat':repetition,'harness_exception':traceback.format_exc()})
    finally:d.Dispose()
report['isolation']={'same_rhino_document':Rhino.RhinoDoc.ActiveDoc==before,'same_rhino_object_ids':before_ids==sorted(str(o.Id) for o in before.Objects if not o.IsDeleted),'same_canvas_document':canvas_before==(None if GH.Instances.ActiveCanvas is None else GH.Instances.ActiveCanvas.Document)}
path=ROOT/('operation_errors_'+str(time.time_ns())+'.json');path.write_text(json.dumps(report,indent=2,default=str))
result={'path':str(path),'cases':len(report['cases']),'harness_errors':[r for r in report['cases'] if 'harness_exception' in r],'isolation':report['isolation']}
