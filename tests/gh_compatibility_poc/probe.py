"""Isolated live GH compatibility POC. Execute inside Rhino via rhino_run.
Never edits the canvas document or Rhino geometry; all GH documents disposed.
Python 3.9 compatible. Raw evidence and assertions written before final result.
"""
import json, time, traceback
from pathlib import Path
import Rhino, System
import Grasshopper as GH
from Grasshopper.Kernel import GH_Document, GH_RuntimeMessageLevel as Level
from Grasshopper.Kernel.Data import GH_Path
from Grasshopper.Kernel import Types as T, Parameters as P

ROOT=Path('/Users/nes/bin/mcp/rhino-cad-mcp/tests/gh_compatibility_poc')
started=time.time()
GUIDS={'Circle':'807b86e3-be8d-4970-92b5-f8cdcb45b06b','Loft':'a7a41d0a-2188-4f7a-82cc-1a2c4e4ec850','Addition':'58669268-a825-4688-8072-7d3508fcf91c','Brep Edges':'0148a65d-6f42-414a-9db7-9a9b2eb78437'}

def values(param):
    return [{'type':str(g.GetType().FullName),'valid':bool(g.IsValid),'value':str(g)} for g in param.VolatileData.AllData(True) if g is not None]

def state(obj):
    r={'name':obj.Name,'level':str(obj.RuntimeMessageLevel),'warnings':list(obj.RuntimeMessages(Level.Warning)),'errors':list(obj.RuntimeMessages(Level.Error))}
    if hasattr(obj,'VolatileData'):
        r.update(declared_type=str(obj.TypeName),access=str(obj.Access),optional=bool(obj.Optional),sources=int(obj.SourceCount),count=int(obj.VolatileDataCount),data=values(obj),null_slots=sum(g is None for g in obj.VolatileData.AllData(False)),valid_count=sum(g is not None and g.IsValid for g in obj.VolatileData.AllData(False)))
    if hasattr(obj,'Params'):
        r['inputs']=[state(p) for p in obj.Params.Input];r['outputs']=[state(p) for p in obj.Params.Output]
    return r

def make(doc,name):
    obj=GH.Instances.ComponentServer.EmitObjectProxy(System.Guid(GUIDS[name])).CreateInstance()
    obj.CreateAttributes();doc.AddObject(obj,False)
    return obj

def persistent(doc,cls,items):
    p=cls();p.CreateAttributes()
    for item in items:p.PersistentData.Append(item,GH_Path(0))
    doc.AddObject(p,False)
    return p

active_canvas=GH.Instances.ActiveCanvas
before_canvas=None if active_canvas is None else active_canvas.Document
rhino_before=Rhino.RhinoDoc.ActiveDoc
rhino_ids_before=sorted(str(o.Id) for o in rhino_before.Objects if not o.IsDeleted) if rhino_before else []
report={'runtime':{'rhino':str(Rhino.RhinoApp.Version),'grasshopper':str(GH.Instances.ComponentServer.GetType().Assembly.FullName)},'component_guids':GUIDS,'cases':[],'casts':[]}

# Successful connection, compatible-but-insufficient input, missing data,
# and incompatible output-to-input. Repeat fresh document fixtures twice.
for repetition in range(2):
    for kind in ['two_circles_to_loft','one_circle_to_loft','missing_loft_curves','addition_to_brep_edges','circle_to_brep_edges']:
        doc=GH_Document()
        doc.Enabled=True
        try:
            wiring=[]
            if kind=='addition_to_brep_edges':
                source=make(doc,'Addition');receiver=make(doc,'Brep Edges')
                for i,value in enumerate([2.0,3.0]):
                    num=persistent(doc,P.Param_Number,[T.GH_Number(value)])
                    source.Params.Input[i].AddSource(num)
                receiver.Params.Input[0].AddSource(source.Params.Output[0])
                wiring.append({'source_type':source.Params.Output[0].TypeName,'target_type':receiver.Params.Input[0].TypeName,'accepted':receiver.Params.Input[0].SourceCount==1})
            elif kind=='circle_to_brep_edges':
                source=make(doc,'Circle');receiver=make(doc,'Brep Edges')
                receiver.Params.Input[0].AddSource(source.Params.Output[0])
                wiring.append({'source_type':source.Params.Output[0].TypeName,'target_type':receiver.Params.Input[0].TypeName,'accepted':receiver.Params.Input[0].SourceCount==1})
            elif kind=='missing_loft_curves':
                source=None;receiver=make(doc,'Loft')
            else:
                source=make(doc,'Circle');receiver=make(doc,'Loft')
                zs=[0.0,10.0] if kind=='two_circles_to_loft' else [0.0]
                planes=persistent(doc,P.Param_Plane,[T.GH_Plane(Rhino.Geometry.Plane(Rhino.Geometry.Point3d(0,0,z),Rhino.Geometry.Vector3d.ZAxis)) for z in zs])
                source.Params.Input[0].AddSource(planes)
                receiver.Params.Input[0].AddSource(source.Params.Output[0])
                wiring.append({'source_type':source.Params.Output[0].TypeName,'target_type':receiver.Params.Input[0].TypeName,'accepted':receiver.Params.Input[0].SourceCount==1})
            if not GH_Document.EnableSolutions:raise RuntimeError('Global GH solver disabled; not changing user setting')
            doc.NewSolution(False)
            report['cases'].append({'case':kind,'repetition':repetition,'solver_state':str(doc.SolutionState),'enabled':doc.Enabled,'wiring':wiring,'source':state(source) if source else None,'receiver':state(receiver)})
        except Exception:
            report['cases'].append({'case':kind,'repetition':repetition,'harness_exception':traceback.format_exc()})
        finally:doc.Dispose()

# CastTo is generic and takes a by-reference output. Reflection captures its
# actual Boolean and updated output separately, avoiding Python tuple truthiness.
fixtures=[('circle_to_curve',T.GH_Circle(Rhino.Geometry.Circle(5.0)),T.GH_Curve),('circle_to_brep',T.GH_Circle(Rhino.Geometry.Circle(5.0)),T.GH_Brep),('number_to_brep',T.GH_Number(42.0),T.GH_Brep),('number_to_curve',T.GH_Number(42.0),T.GH_Curve),('line_to_circle',T.GH_Curve(Rhino.Geometry.LineCurve(Rhino.Geometry.Point3d.Origin,Rhino.Geometry.Point3d(10,0,0))),T.GH_Circle),('circular_curve_to_circle',T.GH_Curve(Rhino.Geometry.Circle(5.0).ToNurbsCurve()),T.GH_Circle),('boolean_to_number',T.GH_Boolean(True),T.GH_Number)]
for n in [42.1,42.5,42.9,43.5,-42.5]:fixtures.append(('number_%s_to_integer'%n,T.GH_Number(n),T.GH_Integer))
for name,source,cls in fixtures:
    row={'case':name,'source_type':str(source.GetType().FullName),'target_type':str(cls().GetType().FullName)}
    try:
        target=cls();row['cast_from_ok']=bool(target.CastFrom(source));row['cast_from_value']=str(target);row['cast_from_valid']=bool(target.IsValid)
    except Exception:row['cast_from_exception']=traceback.format_exc()
    try:
        target=cls()
        method=next(m for m in source.GetType().GetMethods() if m.Name=='CastTo' and m.IsGenericMethodDefinition and len(m.GetParameters())==1)
        method=method.MakeGenericMethod(System.Array[System.Type]([target.GetType()]))
        args=System.Array[System.Object]([target]);ok=method.Invoke(source,args);out=args[0]
        row.update(cast_to_ok=bool(ok),cast_to_value=str(out),cast_to_valid=bool(out.IsValid) if out is not None else None)
    except Exception:row['cast_to_exception']=traceback.format_exc()
    report['casts'].append(row)

# Value-dependent parameter-to-parameter conversion: same declared type pair,
# different payloads. This is separate from the component-pair experiments.
report['parameter_cases']=[]
for repetition in range(2):
    for name,source_class,target_class,goo in [
        ('circular_curve_to_circle',P.Param_Curve,P.Param_Circle,T.GH_Curve(Rhino.Geometry.Circle(5).ToNurbsCurve())),
        ('line_curve_to_circle',P.Param_Curve,P.Param_Circle,T.GH_Curve(Rhino.Geometry.LineCurve(Rhino.Geometry.Point3d.Origin,Rhino.Geometry.Point3d(10,0,0)))),
        ('number_42.5_to_integer',P.Param_Number,P.Param_Integer,T.GH_Number(42.5)),
        ('number_negative_42.5_to_integer',P.Param_Number,P.Param_Integer,T.GH_Number(-42.5))]:
        doc=GH_Document();doc.Enabled=True
        try:
            source=persistent(doc,source_class,[goo]);target=target_class();target.CreateAttributes();doc.AddObject(target,False);target.AddSource(source)
            if not GH_Document.EnableSolutions:raise RuntimeError('Global solver disabled')
            doc.NewSolution(False)
            report['parameter_cases'].append({'case':name,'repetition':repetition,'source':state(source),'receiver':state(target)})
        except Exception:report['parameter_cases'].append({'case':name,'repetition':repetition,'harness_exception':traceback.format_exc()})
        finally:doc.Dispose()

# Positive native-target controls prove that the reflection invocation works.
import clr
report['native_cast_controls']=[]
for name,source,target_type in [('circle_to_native_circle',T.GH_Circle(Rhino.Geometry.Circle(5)),clr.GetClrType(Rhino.Geometry.Circle)),('circle_to_native_curve',T.GH_Circle(Rhino.Geometry.Circle(5)),clr.GetClrType(Rhino.Geometry.Curve)),('number_to_native_double',T.GH_Number(42.5),clr.GetClrType(System.Double))]:
    row={'case':name}
    try:
        method=next(m for m in source.GetType().GetMethods() if m.Name=='CastTo' and m.IsGenericMethodDefinition and len(m.GetParameters())==1)
        method=method.MakeGenericMethod(System.Array[System.Type]([target_type]))
        args=System.Array[System.Object]([None]);ok=method.Invoke(source,args)
        row.update(ok=bool(ok),value=str(args[0]))
    except Exception:row['harness_exception']=traceback.format_exc()
    report['native_cast_controls'].append(row)

report['isolation']={'same_canvas_document':before_canvas==(None if GH.Instances.ActiveCanvas is None else GH.Instances.ActiveCanvas.Document),'same_rhino_document':rhino_before==Rhino.RhinoDoc.ActiveDoc,'rhino_object_ids_unchanged':rhino_ids_before==(sorted(str(o.Id) for o in rhino_before.Objects if not o.IsDeleted) if rhino_before else [])}
report['elapsed_seconds']=time.time()-started
path=ROOT/('run_'+str(time.time_ns())+'.json');path.write_text(json.dumps(report,indent=2))
exec(compile((ROOT/'assert_report.py').read_text(),'assert_report.py','exec'))
checks=check_report(report)
report['regression']=checks
path.write_text(json.dumps(report,indent=2))
result={'report':str(path),'regression':checks,'isolation':report['isolation']}
