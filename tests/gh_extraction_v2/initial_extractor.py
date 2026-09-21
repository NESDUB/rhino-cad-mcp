# -*- coding: utf-8 -*-
"""Standalone Rhino 8 / Python 3.9 Grasshopper extractor.
Run with rhinocode -r INSTANCE script /absolute/path/gh_extract_v2.py.
Final dataset: /tmp/grasshopper_master_v2.json; completion: /tmp/gh_extract_result.json.
Read progress.run_id and completion.run_id; never treat an old receipt as this run.
No subprocesses, commands, baking, canvas changes, or global solver toggles.
"""
import contextlib, io, json, time, traceback, uuid, math
from datetime import datetime, timezone
from pathlib import Path

OUTPUT=Path('/tmp/grasshopper_master_v2.json')
RESULT_PATH=Path('/tmp/gh_extract_result.json')
PROGRESS_PATH=Path('/tmp/gh_extract_progress.json')
INCLUDE_COMPATIBILITY=True
VERIFY_CORE_RECEIVERS=True
CHECKPOINT_EVERY=100
SCHEMA_VERSION='2.0.0'
RUN_ID=uuid.uuid4().hex
START=time.time()
BUF=io.StringIO()


def atomic(path,data):
    tmp=path.with_name(path.name+'.'+RUN_ID+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    tmp.replace(path)


def timestamp():return datetime.now(timezone.utc).isoformat()

def progress(stage,**kwargs):
    atomic(PROGRESS_PATH,dict(run_id=RUN_ID,stage=stage,updated=timestamp(),**kwargs))


def summarize_samples(samples):
    tested=[s for s in samples if isinstance(s.get('cast_from_ok'),bool)]
    yes=[s for s in tested if s['cast_from_ok']]
    no=[s for s in tested if not s['cast_from_ok']]
    errors=[s for s in samples if s.get('status')=='error']
    if yes and no:status='conditional_observed'
    elif yes:status='observed_success'
    elif no:status='observed_rejection'
    elif errors:status='error'
    else:status='untested'
    return {'status':status,'tested_samples':len(tested),'successful_samples':len(yes),
            'failed_samples':len(no),'error_samples':len(errors),
            'coverage_complete':bool(samples) and len(tested)==len(samples),
            'universal_compatibility':None}


def extract():
    import Rhino, System, Grasshopper as GH
    from Grasshopper.Kernel import Types as T, Parameters as P
    from Grasshopper.Kernel.Data import GH_Path
    G=Rhino.Geometry
    errors=[];goo_types={};target_params={};source_names={};target_names={}
    before=Rhino.RhinoDoc.ActiveDoc
    ids=sorted(str(o.Id) for o in before.Objects if not o.IsDeleted) if before else []
    canvas=None if GH.Instances.ActiveCanvas is None else GH.Instances.ActiveCanvas.Document
    global_solver=bool(GH.Kernel.GH_Document.EnableSolutions)

    def get(o,name,default=None):
        try:return getattr(o,name)
        except Exception as e:
            errors.append({'kind':'property_read','property':name,'owner':str(type(o)),'error':str(e)})
            return default

    def clean_enum(v):return None if v is None else str(v)
    def info_type(tp):return str(tp.FullName) if tp else None
    def find_goo(param_type):
        current=param_type;ancestry=[]
        while current is not None:
            ancestry.append(str(current.FullName))
            if current.IsGenericType:
                for arg in current.GetGenericArguments():
                    if any(i.FullName=='Grasshopper.Kernel.Types.IGH_Goo' for i in arg.GetInterfaces()):
                        return arg,ancestry
            current=current.BaseType
        return None,ancestry

    def pin(p,index,address,direction):
        tp=p.GetType();goo,ancestry=find_goo(tp);gn=info_type(goo)
        name=str(p.TypeName)
        if goo:
            goo_types[gn]=goo
            names=source_names if direction=='O' else target_names
            names.setdefault(gn,set()).add(name)
            if direction=='I':target_params.setdefault(gn,{})[str(tp.FullName)]=tp
        mapping=str(p.DataMapping)
        return {'index':index,'name':p.Name,'nickName':p.NickName,'typeName':name,
                'concrete_param_type':str(tp.FullName),'goo_type':gn,'type_ancestry':ancestry,
                'address':address+'.'+direction+('%02d'%(index+1)),
                'optional':bool(p.Optional),'access':str(p.Access),'description':p.Description,
                'dataMapping':mapping,'simplify':bool(p.Simplify),'reverse':bool(p.Reverse),
                'flatten':mapping=='Flatten','graft':mapping=='Graft',
                'sources':int(p.SourceCount),'recipients':len(list(p.Recipients)),
                'wireDisplay':str(p.WireDisplay),
                'persistent_defaults':snapshot_tree(get(p,'PersistentData')) if hasattr(p,'PersistentData') else None}

    def value(g):
        if g is None:return {'null':True}
        r={'null':False,'goo_type':str(g.GetType().FullName),'text':str(g),
           'valid':bool(g.IsValid),'why_not':str(g.IsValidWhyNot)}
        prop=g.GetType().GetProperty('Value')
        if prop:
            v=prop.GetValue(g)
            if isinstance(v,(int,float)):
                r['number_repr']=repr(v);r['finite']=math.isfinite(v)
            elif isinstance(v,G.Circle):r['radius']=v.Radius
            elif isinstance(v,G.GeometryBase):
                b=v.GetBoundingBox(True)
                if b.IsValid:r['bounds']={'min':[b.Min.X,b.Min.Y,b.Min.Z],'max':[b.Max.X,b.Max.Y,b.Max.Z]}
        return r

    def snapshot_tree(tree):
        if tree is None:return None
        return [{'path':str(tree.Paths[i]),'items':[value(g) for g in tree.Branches[i]]} for i in range(tree.PathCount)]

    def param_state(p):
        data=list(p.VolatileData.AllData(False))
        return {'level':str(p.RuntimeMessageLevel),'warnings':list(p.RuntimeMessages(GH.Kernel.GH_RuntimeMessageLevel.Warning)),
                'errors':list(p.RuntimeMessages(GH.Kernel.GH_RuntimeMessageLevel.Error)),
                'raw_count':int(p.VolatileDataCount),'valid_count':sum(g is not None and g.IsValid for g in data),
                'null_count':sum(g is None for g in data),'tree':snapshot_tree(p.VolatileData)}

    proxies=sorted(list(GH.Instances.ComponentServer.ObjectProxies),key=lambda p:str(p.Guid))
    components={};skipped=[];cats={}
    progress('components',total_proxies=len(proxies))
    for proxy in proxies:
        guid=str(proxy.Guid)
        try:
            obj=proxy.CreateInstance()
            if obj is None:raise RuntimeError('CreateInstance returned null')
            if not hasattr(obj,'Params'):
                skipped.append({'guid':guid,'reason':'not_component','type':str(obj.GetType().FullName)})
                continue
            # No AddToDocument / solve: inspect newly instantiated defaults only.
            n=len(components)+1;address='C%04d'%n;cat=str(obj.Category)
            cat_index=cats.get(cat,0)+1
            assembly=obj.GetType().Assembly;an=assembly.GetName();location=str(assembly.Location)
            # Installation provenance is a heuristic, not a semantic compatibility rule.
            native='/Rhino 8.app/' in location and '/ManagedPlugIns/' in location
            record={'guid':guid,'name':obj.Name,'nickName':obj.NickName,'description':obj.Description,
                    'category':cat,'subCategory':obj.SubCategory,'exposure':str(proxy.Exposure),
                    'kind':clean_enum(get(proxy,'Kind')),'obsolete':bool(proxy.Obsolete),
                    'sdkCompliant':get(proxy,'SDKCompliant'), 'concrete_type':str(obj.GetType().FullName),
                    'addresses':{'global':address,'category':cat+'.%03d'%cat_index},
                    'plugin':{'isNative':native,'native_classification':'bundled installation-path heuristic',
                              'assemblyName':str(an.Name),'location':location,'version':str(an.Version),
                              'libraryGuid':clean_enum(get(proxy,'LibraryGuid'))},
                    'inputs':[pin(p,i,address,'I') for i,p in enumerate(obj.Params.Input)],
                    'outputs':[pin(p,i,address,'O') for i,p in enumerate(obj.Params.Output)]}
            components[guid]=record;cats[cat]=cat_index
        except Exception:
            errors.append({'kind':'component_inspection','guid':guid,'traceback':traceback.format_exc()})
    # Derive type inventory only from retained records (failed inspections cannot add phantom pairs).
    source_names={};target_names={};used_targets={}
    for record in components.values():
        for direction,names in [('outputs',source_names),('inputs',target_names)]:
            for p in record[direction]:
                if p['goo_type']:
                    names.setdefault(p['goo_type'],set()).add(p['typeName'])
                    if direction=='inputs':used_targets.setdefault(p['goo_type'],set()).add(p['concrete_param_type'])

    def mesh():
        m=G.Mesh()
        for x,y,z in [(0,0,0),(10,0,0),(10,10,0),(0,10,0)]:m.Vertices.Add(x,y,z)
        m.Faces.AddFace(0,1,2,3);m.Normals.ComputeNormals();m.Compact();return m
    def surface():return G.NurbsSurface.CreateFromCorners(G.Point3d(0,0,0),G.Point3d(10,0,0),G.Point3d(10,10,0),G.Point3d(0,10,0))
    def box():return G.Box(G.Plane.WorldXY,G.Interval(0,10),G.Interval(0,10),G.Interval(0,10))
    def matrix():
        m=G.Matrix(3,3);m.SetDiagonal(1);return m
    recipes={}
    def recipe(name,label,fn):recipes.setdefault('Grasshopper.Kernel.Types.'+name,[]).append((label,fn))
    recipe('GH_Number','positive_fraction',lambda:T.GH_Number(42.5))
    recipe('GH_Number','negative_fraction',lambda:T.GH_Number(-42.5))
    recipe('GH_Integer','positive_integer',lambda:T.GH_Integer(2))
    recipe('GH_Boolean','true',lambda:T.GH_Boolean(True))
    recipe('GH_String','plain_text',lambda:T.GH_String('test'))
    recipe('GH_String','numeric_text',lambda:T.GH_String('42.5'))
    recipe('GH_Point','point_1_2_3',lambda:T.GH_Point(G.Point3d(1,2,3)))
    recipe('GH_Vector','unit_x',lambda:T.GH_Vector(G.Vector3d.XAxis))
    recipe('GH_Plane','world_xy',lambda:T.GH_Plane(G.Plane.WorldXY))
    recipe('GH_Line','length_10',lambda:T.GH_Line(G.Line(G.Point3d.Origin,G.Point3d(10,0,0))))
    recipe('GH_Circle','radius_5',lambda:T.GH_Circle(G.Circle(5)))
    recipe('GH_Arc','semicircle',lambda:T.GH_Arc(G.Arc(G.Circle(5),math.pi)))
    recipe('GH_Rectangle','10_by_5',lambda:T.GH_Rectangle(G.Rectangle3d(G.Plane.WorldXY,10,5)))
    recipe('GH_Curve','circle_nurbs',lambda:T.GH_Curve(G.Circle(5).ToNurbsCurve()))
    recipe('GH_Curve','line_curve',lambda:T.GH_Curve(G.LineCurve(G.Point3d.Origin,G.Point3d(10,0,0))))
    recipe('GH_Surface','planar_patch',lambda:T.GH_Surface(surface()))
    recipe('GH_Brep','planar_patch',lambda:T.GH_Brep(surface().ToBrep()))
    recipe('GH_Brep','closed_box',lambda:T.GH_Brep(box().ToBrep()))
    recipe('GH_Mesh','quad',lambda:T.GH_Mesh(mesh()))
    recipe('GH_Box','10_cube',lambda:T.GH_Box(box()))
    recipe('GH_Transform','identity',lambda:T.GH_Transform(G.Transform.Identity))
    recipe('GH_Colour','red',lambda:T.GH_Colour(System.Drawing.Color.Red))
    recipe('GH_Interval','zero_one',lambda:T.GH_Interval(G.Interval(0,1)))
    recipe('GH_Interval2D','unit_uv',lambda:T.GH_Interval2D(G.UVInterval(G.Interval(0,1),G.Interval(0,1))))
    recipe('GH_Time','fixed_2026_01_01',lambda:T.GH_Time(System.DateTime(2026,1,1)))
    recipe('GH_ComplexNumber','real_one',lambda:T.GH_ComplexNumber(GH.Kernel.Types.Complex(1,0)))
    recipe('GH_Matrix','identity_3',lambda:T.GH_Matrix(matrix()))
    # No blank/default custom Goo is silently treated as a representative payload.
    inventory=[]
    for gn in sorted(set(source_names)|set(target_names)):
        inventory.append({'goo_type':gn,'source_type_names':sorted(source_names.get(gn,[])),
                          'target_type_names':sorted(target_names.get(gn,[])),
                          'target_parameter_classes':sorted(used_targets.get(gn,[])),
                          'representative_labels':[x[0] for x in recipes.get(gn,[])],
                          'representative_status':'available' if gn in recipes else 'untested_no_recipe'})
    known=sorted({p['typeName'] for c in components.values() for d in ['inputs','outputs'] for p in c[d]})
    data={'metadata':{'schema_version':SCHEMA_VERSION,'run_id':RUN_ID,'generated':timestamp(),
                     'grasshopper_version':str(GH.Instances.ComponentServer.GetType().Assembly.GetName().Version),
                     'rhino_version':str(Rhino.RhinoApp.Version),'total_proxies':len(proxies),'total_components':len(components),
                     'current_components':sum(not c['obsolete'] for c in components.values()),
                     'obsolete_components':sum(c['obsolete'] for c in components.values()),
                     'address_note':'Assigned to successfully inspected components in GUID sort order; can change between extractions. GUID is stable identity.',
                     'extraction_flags':{'include_obsolete':True,'include_compatibility':INCLUDE_COMPATIBILITY,'include_concrete_types':True,'verify_core_receivers':VERIFY_CORE_RECEIVERS},
                     'complete':False},
          'components':components,'component_sets':{
              'current_exposed':[g for g,c in components.items() if not c['obsolete'] and 'hidden' not in c['exposure'].lower()],
              'current_hidden':[g for g,c in components.items() if not c['obsolete'] and 'hidden' in c['exposure'].lower()],
              'obsolete':[g for g,c in components.items() if c['obsolete']]},
          'known_types':known,'type_inventory':inventory,'skipped_proxies':skipped,'extraction_errors':errors,
          'type_compatibility':{'scope':'Output Goo classes x input Goo classes; empirical samples, not universal compatibility. CastFrom and receiver collection are separate evidence. No component operation is certified.',
                                'pair_count_expected':len(source_names)*len(target_names),'pairs':[]}}
    checkpoint=Path('/tmp/grasshopper_master_v2.'+RUN_ID+'.partial.json')
    atomic(checkpoint,data)

    def wire_test(source,gn):
        rows=[]
        if not VERIFY_CORE_RECEIVERS:return [{'status':'untested','reason':'disabled'}]
        for pn in sorted(used_targets.get(gn,[])):
            if not pn.startswith('Grasshopper.Kernel.Parameters.'):
                rows.append({'parameter_class':pn,'status':'untested','reason':'custom receiver constructor not safety-qualified'});continue
            if not global_solver:
                rows.append({'parameter_class':pn,'status':'untested','reason':'global solver disabled'});continue
            d=None;r={'parameter_class':pn}
            try:
                d=GH.Kernel.GH_Document();d.Enabled=True
                a=P.Param_GenericObject();a.CreateAttributes();a.PersistentData.Append(source,GH_Path(0));d.AddObject(a,False)
                b=System.Activator.CreateInstance(target_params[gn][pn]);b.CreateAttributes();d.AddObject(b,False)
                b.AddSource(a);d.NewSolution(False)
                if str(d.SolutionState)!='PostProcess':raise RuntimeError('Solve incomplete')
                sa=param_state(a);sb=param_state(b)
                if sa['raw_count']!=1 or sa['valid_count']!=1:raise RuntimeError('Source was not delivered as one valid sample')
                if sb['valid_count']==1 and not sb['errors']:status='observed_success'
                elif sb['errors']:status='observed_rejection'
                else:status='no_valid_output'
                r.update(status=status,wire_accepted=b.SourceCount==1,source=sa,receiver=sb,solver_state=str(d.SolutionState))
            except Exception:r.update(status='error',traceback=traceback.format_exc())
            finally:
                if d is not None:d.Dispose()
            rows.append(r)
        return rows

    pairs=data['type_compatibility']['pairs']
    if INCLUDE_COMPATIBILITY:
        for sn in sorted(source_names):
            for tn in sorted(target_names):
                row={'source_goo':sn,'target_goo':tn,'source_type_names':sorted(source_names[sn]),
                     'target_type_names':sorted(target_names[tn]),'samples':[]}
                entries=recipes.get(sn,[])
                if not entries:row['untested_reason']='no representative recipe for source Goo'
                for label,factory in entries:
                    sample={'label':label,'cast_from_ok':None,'cast_from_valid':None}
                    try:
                        source=factory();sample['source']=value(source)
                        if str(source.GetType().FullName)!=sn or not source.IsValid:
                            sample.update(status='untested',reason='representative wrong type or invalid')
                        else:
                            try:
                                target=System.Activator.CreateInstance(goo_types[tn])
                                ok=bool(target.CastFrom(source));sample.update(status='tested',cast_from_ok=ok,cast_from_valid=bool(target.IsValid) if ok else None,converted=value(target) if ok else None)
                            except Exception:sample.update(status='error',cast_exception=traceback.format_exc())
                            # Fresh source for the independent wire probe; do not reuse a cast-mutated value.
                            sample['receiver_tests']=wire_test(factory(),tn)
                    except Exception:sample.update(status='error',representative_exception=traceback.format_exc())
                    row['samples'].append(sample)
                row.update(summarize_samples(row['samples']));pairs.append(row)
                if len(pairs)%CHECKPOINT_EVERY==0:
                    atomic(checkpoint,data);progress('compatibility',processed_pairs=len(pairs),expected_pairs=data['type_compatibility']['pair_count_expected'],checkpoint=str(checkpoint))
    counts={status:sum(p['status']==status for p in pairs) for status in ['observed_success','observed_rejection','conditional_observed','untested','error']}
    data['type_compatibility'].update(counts=counts,pair_count=len(pairs),tested_pairs=sum(p['tested_samples']>0 for p in pairs),
                                      untested=sum(p['tested_samples']==0 for p in pairs),
                                      sample_casts=sum(p['tested_samples'] for p in pairs))
    isolation={'same_rhino_document':before==Rhino.RhinoDoc.ActiveDoc,
               'same_rhino_objects':ids==(sorted(str(o.Id) for o in before.Objects if not o.IsDeleted) if before else []),
               'same_canvas_document':canvas==(None if GH.Instances.ActiveCanvas is None else GH.Instances.ActiveCanvas.Document),
               'global_solver_unchanged':global_solver==bool(GH.Kernel.GH_Document.EnableSolutions)}
    data['metadata'].update(complete=True,elapsed_seconds=time.time()-START,isolation=isolation,
                            completion_note='Complete traversal, not complete compatibility knowledge; inspect skipped/error/untested coverage.')
    if not all(isolation.values()):
        data['metadata']['complete']=False;atomic(checkpoint,data);raise RuntimeError('Isolation check failed; see checkpoint')
    atomic(OUTPUT,data)
    return {'run_id':RUN_ID,'output':str(OUTPUT),'components':len(components),'known_type_names':len(known),
            'source_goo_classes':len(source_names),'target_goo_classes':len(target_names),
            'pair_count':len(pairs),'counts':counts,'sample_casts':data['type_compatibility']['sample_casts'],
            'extraction_errors':len(errors),'isolation':isolation}


def main():
    payload={'ok':False,'run_id':RUN_ID,'state':'running'}
    atomic(RESULT_PATH,payload);progress('starting')
    try:
        with contextlib.redirect_stdout(BUF),contextlib.redirect_stderr(BUF):out=extract()
        payload={'ok':True,'run_id':RUN_ID,'state':'completed','result':out}
    except Exception:
        payload={'ok':False,'run_id':RUN_ID,'state':'failed','traceback':traceback.format_exc()}
    finally:
        payload['console']=BUF.getvalue();payload['elapsed_ms']=round((time.time()-START)*1000,1)
        atomic(RESULT_PATH,payload);progress(payload['state'],receipt=str(RESULT_PATH))
    return payload

if __name__=='__main__':
    result=main()
