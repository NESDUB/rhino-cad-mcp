"""Rhino-side operations; Python 3.9 only. No subprocesses or interactive commands."""
import json, os, math, uuid, time
from pathlib import Path
import Rhino
import scriptcontext as sc
import System
G = Rhino.Geometry

def doc_id(d): return str(os.getpid())+':'+str(d.RuntimeSerialNumber)
def live(d): return [o for o in d.Objects if o is not None and not o.IsDeleted]
def vec(v): return [v.X,v.Y,v.Z]
def accurate_bbox(g):
    # Headless document-owned Breps can return seam-only tight bounds on Rhino 8 Mac.
    # A detached duplicate avoids that cached/document-dependent result.
    detached=g.Duplicate()
    try:return detached.GetBoundingBox(True)
    finally:detached.Dispose()

def bounds(g):
    b=accurate_bbox(g)
    return {'min':vec(b.Min),'max':vec(b.Max)} if b.IsValid else None

def document_info(d):
    obs=live(d)
    return {'document_id':doc_id(d),'name':d.Name,'path':d.Path,'headless':d.IsHeadless,
            'units':str(d.ModelUnitSystem),'absolute_tolerance':d.ModelAbsoluteTolerance,
            'relative_tolerance':d.ModelRelativeTolerance,'angle_tolerance_degrees':d.ModelAngleToleranceDegrees,
            'live_object_count':len(obs),'object_count':len(obs),'object_table_count':d.Objects.Count,
            'layers':[{'index':l.Index,'id':str(l.Id),'name':l.Name,'full_path':l.FullPath,'parent_id':str(l.ParentLayerId),'visible':l.IsVisible,'locked':l.IsLocked} for l in d.Layers if not l.IsDeleted],
            'groups':[{'index':g.Index,'id':str(g.Id),'name':g.Name,'object_count':d.Groups.GroupObjectCount(g.Index),'object_ids':[str(o.Id) for o in d.Groups.GroupMembers(g.Index)]} for g in d.Groups],
            'objects':[{'id':str(o.Id),'name':o.Attributes.Name,'type':str(o.ObjectType),'layer_index':o.Attributes.LayerIndex,'selected':bool(o.IsSelected(False)),'bbox':bounds(o.Geometry)} for o in obs]}

def _layer_effective_state(d, index):
    visible=True; locked=False; seen=set(); cur=index
    while cur>=0 and cur not in seen:
        seen.add(cur); layer=d.Layers[cur]
        visible=visible and bool(layer.IsVisible); locked=locked or bool(layer.IsLocked)
        parent=layer.ParentLayerId
        if parent==System.Guid.Empty: break
        p=d.Layers.FindId(parent); cur=p.Index if p else -1
    return visible,locked

def inspect_hierarchy():
    d=sc.doc
    layers=[]
    for l in d.Layers:
        if l.IsDeleted: continue
        ev,el=_layer_effective_state(d,l.Index)
        layers.append({'index':l.Index,'id':str(l.Id),'name':l.Name,'full_path':l.FullPath,'parent_id':str(l.ParentLayerId),'visible':l.IsVisible,'locked':l.IsLocked,'effective_visible':ev,'effective_locked':el,'children':[{'index':c.Index,'id':str(c.Id),'name':c.Name} for c in d.Layers if not c.IsDeleted and c.ParentLayerId==l.Id]})
    objects=[{'id':str(o.Id),'name':o.Attributes.Name,'layer_index':o.Attributes.LayerIndex,'effective_visible':_layer_effective_state(d,o.Attributes.LayerIndex)[0] and bool(o.Attributes.Visible),'effective_locked':_layer_effective_state(d,o.Attributes.LayerIndex)[1] or bool(o.Attributes.Locked)} for o in live(d)]
    return {'document_id':doc_id(d),'layers':layers,'objects':objects,'groups':[{'index':g.Index,'id':str(g.Id),'name':g.Name,'members':[{'id':str(o.Id),'name':o.Attributes.Name,'layer_index':o.Attributes.LayerIndex,'group_indices':list(o.Attributes.GetGroupList())} for o in d.Groups.GroupMembers(g.Index)]} for g in d.Groups]}

def hierarchy_regression():
    d=Rhino.RhinoDoc.CreateHeadless(None); old=sc.doc; sc.doc=d
    try:
        p=d.Layers.Add('Regression Parent',System.Drawing.Color.Gray); c=d.Layers.Add('Regression Child',System.Drawing.Color.Gray); d.Layers[c].ParentLayerId=d.Layers[p].Id
        gid=d.Objects.AddBrep(G.Sphere(G.Point3d.Origin,1).ToBrep()); o=d.Objects.FindId(gid); o.Attributes.LayerIndex=c; d.Objects.ModifyAttributes(gid,o.Attributes,True)
        before=_layer_effective_state(d,c); d.Layers[p].IsVisible=False; hidden=_layer_effective_state(d,c); d.Layers[p].IsVisible=True; d.Layers[p].IsLocked=True; locked=_layer_effective_state(d,c)
        passed=before==(True,False) and hidden==(False,False) and locked==(True,True)
        return {'passed':passed,'child_local':{'visible':d.Layers[c].IsVisible,'locked':d.Layers[c].IsLocked},'before':before,'after_parent_hidden':hidden,'after_parent_locked':locked}
    finally: d.Dispose(); sc.doc=old

def documents():
    return {'documents':[dict(document_id=doc_id(d),name=d.Name,path=d.Path,headless=d.IsHeadless,
                              current_script_document=d==sc.doc,gui_active=d==Rhino.RhinoDoc.ActiveDoc)
                         for d in Rhino.RhinoDoc.OpenDocuments(True)]}

def new_document(units='Millimeters',absolute_tolerance=.01,headless=False):
    if absolute_tolerance<=0 or not math.isfinite(absolute_tolerance):raise ValueError('Positive finite tolerance required')
    if not hasattr(Rhino.UnitSystem,units):raise ValueError('Unknown Rhino unit system')
    if headless:
        d=Rhino.RhinoDoc.CreateHeadless(None)
        if d is None:raise RuntimeError('Document creation failed')
        d.ModelUnitSystem=getattr(Rhino.UnitSystem,units);d.ModelAbsoluteTolerance=absolute_tolerance
        d.ModelRelativeTolerance=.01;d.ModelAngleToleranceDegrees=1
        sc.doc=d
        return document_info(d)
    # GUI documents: Create() makes an invisible in-memory doc. OpenFile() is
    # the only reliable way to get a visible Rhino window/tab.  Strategy:
    # build a headless doc with the requested settings, save to a temp .3dm,
    # dispose the headless doc, then OpenFile the temp file.
    tmp=Rhino.RhinoDoc.CreateHeadless(None)
    if tmp is None:raise RuntimeError('Document creation failed')
    tmp.ModelUnitSystem=getattr(Rhino.UnitSystem,units);tmp.ModelAbsoluteTolerance=absolute_tolerance
    tmp.ModelRelativeTolerance=.01;tmp.ModelAngleToleranceDegrees=1
    tp=str(Path(os.environ.get('TMPDIR','/tmp'))/('rhino-new-'+uuid.uuid4().hex+'.3dm'))
    f3dm=Rhino.FileIO.File3dm();f3dm.Settings.ModelUnitSystem=getattr(Rhino.UnitSystem,units)
    f3dm.Settings.ModelAbsoluteTolerance=absolute_tolerance;f3dm.Write(tp,8)
    tmp.Dispose()
    if not Rhino.RhinoDoc.OpenFile(tp):raise RuntimeError('OpenFile failed for new document')
    d=Rhino.RhinoDoc.ActiveDoc
    if d is None:raise RuntimeError('ActiveDoc is None after OpenFile')
    d.ModelUnitSystem=getattr(Rhino.UnitSystem,units);d.ModelAbsoluteTolerance=absolute_tolerance
    d.ModelRelativeTolerance=.01;d.ModelAngleToleranceDegrees=1
    sc.doc=d;Rhino.RhinoApp.SetFocusToMainWindow()
    return document_info(d)

def open_document(path,headless=False):
    path=str(Path(path).expanduser().resolve())
    if not Path(path).is_file() or Path(path).suffix.lower()!='.3dm':raise ValueError('Existing .3dm file required')
    if headless:
        d=Rhino.RhinoDoc.OpenHeadless(path)
        if d is None:raise RuntimeError('Open failed')
        sc.doc=d
        return document_info(d)
    # GUI: OpenFile produces a visible window/tab; Open() often does not.
    if not Rhino.RhinoDoc.OpenFile(path):raise RuntimeError('OpenFile failed')
    d=Rhino.RhinoDoc.ActiveDoc
    if d is None:raise RuntimeError('ActiveDoc is None after OpenFile')
    sc.doc=d;Rhino.RhinoApp.SetFocusToMainWindow()
    return document_info(d)

def save_as_active(path, overwrite=False, verify=True):
    d=sc.doc; path=str(Path(path).expanduser().resolve())
    if Path(path).suffix.lower()!='.3dm': raise ValueError('Save-as path must end in .3dm')
    if Path(path).exists() and not overwrite: raise ValueError('File exists; set overwrite=True explicitly')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if not d.SaveAs(path): raise RuntimeError('Rhino SaveAs failed')
    out=verified_save(path, True, verify); out['save_mode']='SaveAs'; out['active_document_path_after']=d.Path
    return out

def close_document(force=False):
    d=sc.doc
    if not d.IsHeadless:
        raise ValueError('GUI document closing is not supported safely by RhinoCommon; Dispose does not close the GUI window. Close it through Rhino UI.')
    ident=doc_id(d); name=d.Name; headless=True; d.Dispose()
    return {'closed':True,'document_id':ident,'name':name,'headless':headless}

def inspect_brep(o):
    g=o.Geometry;r={'id':str(o.Id),'name':o.Attributes.Name,'valid':bool(g.IsValid),'bbox':bounds(g),'type':str(o.ObjectType)}
    if isinstance(g,G.Brep):
        r.update(solid=bool(g.IsSolid),manifold=bool(g.IsManifold),naked_edges=sum(e.Valence==G.EdgeAdjacency.Naked for e in g.Edges),faces=g.Faces.Count)
    return r

def validate_assembly(object_ids=None,require_solids=True,check_intersections=False,
                      overlap_tolerance=.03,minimum_intersection_volume=.2,max_pairs=5000):
    d=sc.doc;wanted=set(object_ids or []);obs=[o for o in live(d) if not wanted or str(o.Id) in wanted]
    missing=sorted(wanted-set(str(o.Id) for o in obs))
    rows=[inspect_brep(o) for o in obs];bad=[r['id'] for r in rows if not r['valid'] or ('solid' in r and (not r['manifold'] or (require_solids and not r['solid'])))]
    meta=[];dupes=[];clashes=[];errors=[];tested=0;candidate_count=0
    for o in obs:
        absent=[k for k in ['role','created_by','revision','parent'] if not o.Attributes.GetUserString(k)]
        if absent:meta.append({'id':str(o.Id),'missing':absent})
    for i,a in enumerate(obs):
        ba=a.Geometry.GetBoundingBox(False)
        if not ba.IsValid:continue
        for b in obs[i+1:]:
            bb=b.Geometry.GetBoundingBox(False)
            if not bb.IsValid:continue
            if ba.Min.DistanceTo(bb.Min)<d.ModelAbsoluteTolerance and ba.Max.DistanceTo(bb.Max)<d.ModelAbsoluteTolerance:
                if G.GeometryBase.GeometryEquals(a.Geometry,b.Geometry):dupes.append([str(a.Id),str(b.Id)])
            if not check_intersections or not isinstance(a.Geometry,G.Brep) or not isinstance(b.Geometry,G.Brep):continue
            if not a.Geometry.IsSolid or not b.Geometry.IsSolid:continue
            overlaps=[min(ba.Max[k],bb.Max[k])-max(ba.Min[k],bb.Min[k]) for k in range(3)]
            if min(overlaps)<=overlap_tolerance:continue
            candidate_count+=1
            if tested>=max_pairs:continue
            tested+=1
            try:
                result=G.Brep.CreateBooleanIntersection(a.Geometry,b.Geometry,d.ModelAbsoluteTolerance)
                # No result can mean disjoint surfaces OR Boolean failure; do not certify it.
                if result is None:
                    errors.append({'pair':[str(a.Id),str(b.Id)],'reason':'Boolean returned None; inconclusive'})
                    continue
                volume=0
                for g in result:
                    v=G.VolumeMassProperties.Compute(g)
                    if v:volume+=abs(v.Volume);v.Dispose()
                if volume>minimum_intersection_volume:clashes.append({'pair':[str(a.Id),str(b.Id)],'volume':volume})
            except Exception as exc:errors.append({'pair':[str(a.Id),str(b.Id)],'reason':str(exc)})
    return {'document_id':doc_id(d),'object_count':len(obs),'objects':rows,'missing_ids':missing,
            'geometry_pass':not bad and not missing,'invalid_or_non_solid_ids':bad,
            'duplicates':dupes,'metadata_incomplete':meta,'intersections':clashes,
            'intersection_check':{'requested':check_intersections,'tested_pairs':tested,'candidate_pairs':candidate_count,
             'complete':check_intersections and tested==candidate_count and not errors,'errors':errors,
             'broad_phase_axis_overlap':overlap_tolerance,'minimum_reported_volume':minimum_intersection_volume,
             'scope':'Modeled-pose Boolean screening; not continuous motion, clearance or manufacturability certification.'}}

def verified_save(path='',overwrite=False,verify=True):
    d=sc.doc;path=str(Path(path or d.Path or '').expanduser().resolve())
    if Path(path).suffix.lower()!='.3dm':raise ValueError('Explicit .3dm path required for unnamed documents')
    if Path(path).exists() and not overwrite:raise ValueError('File exists; set overwrite=True explicitly')
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    opts=Rhino.FileIO.FileWriteOptions();opts.SuppressDialogBoxes=True;opts.SuppressAllInput=True
    if not d.Write3dmFile(path,opts):raise RuntimeError('Rhino write failed')
    r={'written_path':path,'active_document_path':d.Path,'active_document_name':d.Name,'document_id':doc_id(d),
       'saved':True,'bytes':Path(path).stat().st_size,'verified':False}
    if verify:
        f=Rhino.FileIO.File3dm.Read(path)
        if f is None:raise RuntimeError('Saved file cannot be read back')
        try:
            src=live(d);written=list(f.Objects);valid=all(o.Geometry.IsValid for o in written)
            same_count=len(src)==len(written);same_units=str(d.ModelUnitSystem)==str(f.Settings.ModelUnitSystem)
            src_map={str(o.Id):o for o in src};mismatch=[]
            for o in written:
                original=src_map.get(str(o.Id))
                if original is None:mismatch.append(str(o.Id));continue
                a=accurate_bbox(original.Geometry);b=accurate_bbox(o.Geometry)
                if original.Attributes.Name!=o.Attributes.Name or a.Min.DistanceTo(b.Min)>d.ModelAbsoluteTolerance or a.Max.DistanceTo(b.Max)>d.ModelAbsoluteTolerance:mismatch.append(str(o.Id))
            r.update(verified=bool(valid and same_count and same_units and not mismatch),readback={'live_count':len(src),'file_count':len(written),'all_valid':valid,'units_match':same_units,'identity_name_bbox_mismatches':mismatch,'checks':'IDs, names, counts, validity, units, bounding boxes; not bitwise equivalence'})
            if not r['verified']:raise RuntimeError('Readback verification failed: '+json.dumps(r))
        finally:f.Dispose()
    return r

def _properties(obj):
    if obj is None:return None
    out={}
    for p in obj.GetType().GetProperties():
        if not p.CanRead or p.GetIndexParameters().Length:continue
        try:
            v=p.GetValue(obj,None)
            if v is None or isinstance(v,(str,bool,int,float)):out[p.Name]=v
            else:out[p.Name]=str(v)
        except Exception:pass
    return out

def capture(width=1920,height=1080,output_path='',archive_scene=True,preset=None,square=False):
    d=sc.doc;v=d.Views.ActiveView
    if v is None:raise RuntimeError('Target document has no viewport (possibly headless)')
    vp=v.ActiveViewport
    if preset:
        if preset.get('camera') and preset.get('target'):vp.SetCameraLocations(G.Point3d(*preset['target']),G.Point3d(*preset['camera']))
        if preset.get('up'):vp.SetCameraUp(G.Vector3d(*preset['up']),True)
        if 'parallel' in preset:
            if preset['parallel']:vp.ChangeToParallelProjection(True)
            else:vp.ChangeToPerspectiveProjection(True,preset.get('lens_mm',50))
        if preset.get('display_mode'):
            mode=Rhino.Display.DisplayModeDescription.FindByName(preset['display_mode'])
            if mode is None:raise ValueError('Unknown display mode')
            vp.DisplayMode=mode
    width=max(64,min(int(width),4096));height=width if square else max(64,min(int(height),4096))
    folder=Path(os.environ.get('TMPDIR','/tmp'))/'rhino-cad-captures';folder.mkdir(parents=True,exist_ok=True)
    p=Path(output_path).expanduser().resolve() if output_path else folder/('view-'+uuid.uuid4().hex+'.png')
    if p.suffix.lower()!='.png':raise ValueError('Capture path must end in .png')
    if p.exists():raise ValueError('Capture destination already exists')
    p.parent.mkdir(parents=True,exist_ok=True);d.Views.Redraw()
    bmp=v.CaptureToBitmap(System.Drawing.Size(width,height))
    if bmp is None:raise RuntimeError('Viewport capture failed')
    try:bmp.Save(str(p),System.Drawing.Imaging.ImageFormat.Png)
    finally:bmp.Dispose()
    manifest={'document_id':doc_id(d),'document_path':d.Path,'width':width,'height':height,'aspect_ratio':round(float(width)/float(height),8),'square_requested':bool(square),'view':vp.Name,
              'camera':vec(vp.CameraLocation),'target':vec(vp.CameraTarget),'direction':vec(vp.CameraDirection),'up':vec(vp.CameraUp),
              'parallel':vp.IsParallelProjection,'lens_mm':vp.Camera35mmLensLength,'display_mode':vp.DisplayMode.EnglishName,
              'display_mode_id':str(vp.DisplayMode.Id),'render_settings':_properties(d.RenderSettings),
              'lighting':[{'id':str(o.Id),'settings':_properties(o.LightGeometry)} for o in d.Lights],
              'environments':[{'id':str(e.Id),'name':e.Name,'type':e.TypeName} for e in d.RenderEnvironments],
              'exposure_note':'Render settings are recorded verbatim where exposed. Scene archive retains materials/environments; renderer convergence is not guaranteed by viewport capture.'}
    if archive_scene:manifest['scene_archive']=verified_save(str(p.with_suffix('.3dm')),False,True)['written_path']
    side=p.with_suffix('.json');side.write_text(json.dumps(manifest,default=str,indent=2))
    return {'path':str(p),'manifest_path':str(side),'width':width,'height':height,'view':vp.Name,'scene_archive':manifest.get('scene_archive')}

def capture_views(views=None,width=640,height=480,output_path='',display_mode='Rendered',parallel=True,archive_scene=False,columns=3,square=False):
    """Capture arbitrary camera directions into individual PNGs plus a labeled contact sheet."""
    d=sc.doc; v=d.Views.ActiveView
    if v is None: raise RuntimeError('Target document has no viewport')
    vp=v.ActiveViewport; views=views or []
    if not views: raise ValueError('At least one view preset is required')
    if not 1<=columns<=8: raise ValueError('columns must be 1..8')
    width=max(64,min(int(width),2048)); height=width if square else max(64,min(int(height),2048))
    all_live=live(d)
    if not all_live: raise ValueError('Cannot frame an empty document')
    bb=None
    for o in all_live:
        b=accurate_bbox(o.Geometry); bb=b if bb is None else Rhino.Geometry.BoundingBox.Union(bb,b)
    center=bb.Center; diag=max(bb.Diagonal.Length, d.ModelAbsoluteTolerance*100)
    folder=Path(output_path).expanduser().resolve().parent if output_path else Path(os.environ.get('TMPDIR','/tmp'))/'rhino-cad-captures'
    folder.mkdir(parents=True,exist_ok=True)
    sheet=Path(output_path).expanduser().resolve() if output_path else folder/('contact-'+uuid.uuid4().hex+'.png')
    if sheet.suffix.lower()!='.png': raise ValueError('output_path must end in .png')
    if sheet.exists(): raise ValueError('Capture destination already exists')
    original={'loc':vp.CameraLocation,'target':vp.CameraTarget,'up':vp.CameraUp,'parallel':vp.IsParallelProjection,'lens':vp.Camera35mmLensLength,'display':vp.DisplayMode}
    mode=Rhino.Display.DisplayModeDescription.FindByName(display_mode)
    if mode is None: raise ValueError('Unknown display mode: '+str(display_mode))
    cells=[]; manifest=[]
    try:
        for idx,item in enumerate(views):
            if not isinstance(item,dict) or not item.get('direction'): raise ValueError('Each view needs a direction vector')
            name=str(item.get('name','view_%02d'%idx)); direction=G.Vector3d(*[float(x) for x in item['direction']])
            if not direction.Unitize(): raise ValueError('View direction cannot be zero: '+name)
            up=G.Vector3d(*[float(x) for x in item.get('up',[0,0,1])]);
            if not up.Unitize(): up=G.Vector3d(0,0,1)
            if abs(G.Vector3d.Multiply(direction,up))>.98: up=G.Vector3d(0,1,0)
            vp.SetCameraLocations(center-direction*(diag*2.5),center); vp.CameraUp=up
            use_parallel=bool(item.get('parallel',parallel))
            if use_parallel: vp.ChangeToParallelProjection(True)
            else: vp.ChangeToPerspectiveProjection(True,float(item.get('lens_mm',50)))
            vp.DisplayMode=mode; vp.ZoomBoundingBox(bb); d.Views.Redraw()
            bmp=v.CaptureToBitmap(System.Drawing.Size(width,height))
            if bmp is None: raise RuntimeError('Capture failed: '+name)
            ip=folder/(sheet.stem+'-'+name.replace(' ','_')+'.png')
            bmp.Save(str(ip),System.Drawing.Imaging.ImageFormat.Png); cells.append((name,bmp,ip))
            manifest.append({'name':name,'direction':[direction.X,direction.Y,direction.Z],'up':[up.X,up.Y,up.Z],'parallel':use_parallel,'lens_mm':vp.Camera35mmLensLength,'path':str(ip),'camera':[vp.CameraLocation.X,vp.CameraLocation.Y,vp.CameraLocation.Z],'target':[vp.CameraTarget.X,vp.CameraTarget.Y,vp.CameraTarget.Z]})
        rows=(len(cells)+columns-1)//columns; label_h=28; sheet_bmp=System.Drawing.Bitmap(columns*width,rows*(height+label_h),System.Drawing.Imaging.PixelFormat.Format24bppRgb)
        g=System.Drawing.Graphics.FromImage(sheet_bmp); g.Clear(System.Drawing.Color.White); font=System.Drawing.Font('Arial',12)
        try:
            for i,(name,bmp,_) in enumerate(cells):
                x=(i%columns)*width; y=(i//columns)*(height+label_h); g.DrawImage(bmp,x,y); g.DrawString(name,font,System.Drawing.Brushes.Black,x+8,y+height+5)
        finally: g.Dispose()
        sheet_bmp.Save(str(sheet),System.Drawing.Imaging.ImageFormat.Png); sheet_bmp.Dispose()
    finally:
        for _,bmp,_ in cells: bmp.Dispose()
        vp.SetCameraLocations(original['loc'],original['target']); vp.CameraUp=original['up']
        if original['parallel']: vp.ChangeToParallelProjection(True)
        else: vp.ChangeToPerspectiveProjection(True,original['lens'])
        vp.DisplayMode=original['display']; d.Views.Redraw()
    side=sheet.with_suffix('.json'); side.write_text(json.dumps({'document_id':doc_id(d),'display_mode':display_mode,'width':width,'height':height,'aspect_ratio':round(float(width)/float(height),8),'square_requested':bool(square),'columns':columns,'sheet':str(sheet),'views':manifest,'restored':True},indent=2))
    return {'path':str(sheet),'manifest_path':str(side),'view_count':len(manifest),'individual_paths':[x['path'] for x in manifest],'restored':True}

def visual_qa(view_presets=None, output_path='', width=640, height=640, display_mode='Rendered', require_solids=False, check_intersections=True):
    """Produce visual-review artifacts plus deterministic geometry/material/composition warnings."""
    d=sc.doc; obs=live(d)
    if not obs: raise ValueError('Visual QA requires at least one live object')
    info=document_info(d); validation=validate_assembly(require_solids=require_solids,check_intersections=check_intersections)
    ext=[]
    for o in obs:
        b=accurate_bbox(o.Geometry)
        if b.IsValid: ext.append((b.Max.X-b.Min.X,b.Max.Y-b.Min.Y,b.Max.Z-b.Min.Z))
    overall=accurate_bbox(obs[0].Geometry)
    for o in obs[1:]: overall=Rhino.Geometry.BoundingBox.Union(overall,accurate_bbox(o.Geometry))
    dims=[overall.Max.X-overall.Min.X,overall.Max.Y-overall.Min.Y,overall.Max.Z-overall.Min.Z]
    warnings=[]
    if max(dims)>0 and min(x for x in dims if x>0)>0 and max(dims)/min(x for x in dims if x>0)>20: warnings.append({'category':'proportion','severity':'warning','message':'Overall envelope aspect ratio exceeds 20:1; review scale or intended slenderness.'})
    missing_material=[o.Attributes.Name or str(o.Id) for o in obs if o.RenderMaterial is None]
    if missing_material: warnings.append({'category':'material','severity':'warning','objects':missing_material,'message':'Objects lack effective render materials; rendered shading may fall back to legacy/layer behavior.'})
    if validation.get('intersections'): warnings.append({'category':'intersection','severity':'error','pairs':validation['intersections'],'message':'Solid interference detected in modeled pose.'})
    if validation.get('invalid_or_non_solid_ids'): warnings.append({'category':'silhouette','severity':'error','objects':validation['invalid_or_non_solid_ids'],'message':'Invalid or non-solid geometry may produce broken silhouettes.'})
    if validation.get('metadata_incomplete'): warnings.append({'category':'seams','severity':'info','objects':validation['metadata_incomplete'],'message':'Semantic metadata is incomplete; seam/service intent cannot be audited for these objects.'})
    if not view_presets: view_presets=[{'name':'hero_iso','direction':[1,-1,1]},{'name':'front','direction':[0,-1,0]},{'name':'rear_iso','direction':[-1,1,1]}]
    cap=capture_views(view_presets,width,height,output_path,display_mode,True,False,3,True)
    manifest=json.loads(Path(cap['manifest_path']).read_text())
    for v in manifest['views']:
        t=v['target']; delta=math.sqrt((t[0]-overall.Center.X)**2+(t[1]-overall.Center.Y)**2+(t[2]-overall.Center.Z)**2)
        if delta>max(dims)*.25: warnings.append({'category':'composition','severity':'warning','view':v['name'],'message':'Camera target is materially off the assembly center.'})
    if display_mode=='Rendered' and missing_material: warnings.append({'category':'shading','severity':'warning','message':'Rendered QA includes fallback-material objects; inspect highlights and transitions after assigning PBR materials.'})
    warnings.append({'category':'silhouette','severity':'info','message':'Silhouette was framed from the computed assembly bounds; pixel-level contour comparison requires an image reference.'})
    warnings.append({'category':'seams','severity':'info','message':'No automatic seam-gap measurement is claimed; geometry/topology and metadata checks are reported instead.'})
    return {'document_id':doc_id(d),'capture':cap,'manifest':manifest,'assembly':validation,'bounds':{'min':vec(overall.Min),'max':vec(overall.Max),'dimensions':dims},'warnings':warnings,'scope':'Deterministic CAD/material/interference heuristics plus rendered captures; not a ray-traced or learned visual-quality judgment.'}

def activate_document():
    d=sc.doc
    if d.IsHeadless:raise ValueError('A headless document cannot be GUI-activated')
    Rhino.RhinoDoc.ActiveDoc=d;Rhino.RhinoApp.SetFocusToMainWindow()
    return {'document_id':doc_id(d),'gui_active':Rhino.RhinoDoc.ActiveDoc==d,'name':d.Name}

def _pbr_values(m):
    if not m.IsPhysicallyBased or m.PhysicallyBased is None:
        return {'is_pbr':False,'name':m.Name}
    p=m.PhysicallyBased;c=p.BaseColor
    return {'is_pbr':True,'name':m.Name,'base_color':[c.R,c.G,c.B,c.A],
            'metallic':p.Metallic,'roughness':p.Roughness,'clearcoat':p.Clearcoat,
            'clearcoat_roughness':p.ClearcoatRoughness,'opacity':p.Opacity,
            'ior':p.OpacityIOR,'specular':p.Specular,'anisotropic':p.Anisotropic}

def material_read(object_id):
    o=sc.doc.Objects.FindId(System.Guid(object_id))
    if o is None:raise ValueError('Object not found')
    rm=o.RenderMaterial
    r={'object_id':object_id,'material_source':str(o.Attributes.MaterialSource),'material_index':o.Attributes.MaterialIndex}
    if rm is not None:
        m=rm.SimulatedMaterial(Rhino.Render.RenderTexture.TextureGeneration.Allow)
        r.update(render_material_id=str(rm.Id),render_type=rm.TypeName,values=_pbr_values(m))
    else:r['values']=_pbr_values(sc.doc.Materials[o.Attributes.MaterialIndex]) if o.Attributes.MaterialIndex>=0 else {'is_pbr':False}
    return r

def material_apply(object_ids,name,base_color,metallic=0,roughness=.3,clearcoat=0,
                   clearcoat_roughness=.1,opacity=1,ior=1.5,specular=.5,anisotropic=0):
    if len(base_color)!=3 or any(not isinstance(x,int) or not 0<=x<=255 for x in base_color):raise ValueError('base_color must be three integers 0..255')
    for x in [metallic,roughness,clearcoat,clearcoat_roughness,opacity,specular,anisotropic]:
        if not math.isfinite(x) or not 0<=x<=1:raise ValueError('PBR weights must be finite, within 0..1')
    if not math.isfinite(ior) or not 1<=ior<=3:raise ValueError('ior must be 1..3')
    d=sc.doc;obs=[d.Objects.FindId(System.Guid(s)) for s in object_ids]
    if not obs or any(o is None for o in obs):raise ValueError('All target object IDs must exist')
    m=Rhino.DocObjects.Material();m.Name=name;m.DiffuseColor=System.Drawing.Color.FromArgb(*base_color);m.ToPhysicallyBased();p=m.PhysicallyBased
    p.BaseColor=Rhino.Display.Color4f(base_color[0]/255.,base_color[1]/255.,base_color[2]/255.,1)
    p.Metallic=metallic;p.Roughness=roughness;p.Clearcoat=clearcoat;p.ClearcoatRoughness=clearcoat_roughness
    p.Opacity=opacity;p.OpacityIOR=ior;p.Specular=specular;p.Anisotropic=anisotropic
    # FromMaterial preserves the physical shader. CreateBasicMaterial can downgrade it.
    rm=Rhino.Render.RenderMaterial.FromMaterial(m,d)
    if rm is None:raise RuntimeError('PBR render content creation failed')
    sim=rm.SimulatedMaterial(Rhino.Render.RenderTexture.TextureGeneration.Allow)
    wanted=_pbr_values(m);got=_pbr_values(sim)
    if not got['is_pbr']:raise RuntimeError('Render material was downgraded; nothing assigned')
    for key in ['metallic','roughness','clearcoat','clearcoat_roughness','opacity','ior','specular','anisotropic']:
        if abs(got[key]-wanted[key])>1e-5:raise RuntimeError('PBR readback mismatch: '+key)
    if max(abs(a-b) for a,b in zip(got['base_color'],wanted['base_color']))>1e-5:raise RuntimeError('Base color readback mismatch')
    rm.Name=name;d.RenderMaterials.Add(rm)
    old=[(o.Id,o.Attributes.Duplicate(),o.RenderMaterial) for o in obs]
    try:
        for o in obs:
            a=o.Attributes.Duplicate();a.MaterialSource=Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
            a.ColorSource=Rhino.DocObjects.ObjectColorSource.ColorFromObject;a.ObjectColor=System.Drawing.Color.FromArgb(*base_color)
            a.SetUserString('finish',name);d.Objects.ModifyAttributes(o.Id,a,True)
            o=d.Objects.FindId(o.Id);o.RenderMaterial=rm;o.CommitChanges()
            check=material_read(str(o.Id))
            if check.get('render_material_id')!=str(rm.Id) or not check['values']['is_pbr']:raise RuntimeError('Assigned material failed readback')
        d.Views.Redraw()
    except Exception:
        for oid,a,previous in old:
            d.Objects.ModifyAttributes(oid,a,True);o=d.Objects.FindId(oid)
            if previous is not None:o.RenderMaterial=previous;o.CommitChanges()
        raise
    return {'render_material_id':str(rm.Id),'render_type':rm.TypeName,'verified':True,'values':got,'object_ids':object_ids}

def _object_stamp(d):
    return sorted((str(o.Id),int(o.Geometry.DataCRC(0)),str((o.Attributes.Name,o.Attributes.LayerIndex,o.Attributes.MaterialIndex,str(o.Attributes.ObjectColor),o.Attributes.GetUserStrings()))) for o in live(d))

def _table_stamp(d):
    return {'layers':[(str(l.Id),l.Index,l.Name,str(l.ParentLayerId),str(l.Color),l.IsVisible,l.IsLocked) for l in d.Layers if not l.IsDeleted],
            'materials':[(str(m.Id),m.MaterialIndex,int(m.DataCRC(0))) for m in d.Materials if not m.IsDeleted],
            'units':str(d.ModelUnitSystem),'tolerance':d.ModelAbsoluteTolerance,
            'strings':[(d.Strings.GetKey(i),d.Strings.GetValue(i)) for i in range(d.Strings.Count)],
            'relative_tolerance':d.ModelRelativeTolerance,'angle_tolerance':d.ModelAngleToleranceRadians,
            'groups':[(str(g.Id),g.Name) for g in d.Groups if not g.IsDeleted],
            'dimstyles':[(str(g.Id),int(g.DataCRC(0))) for g in d.DimStyles if not g.IsDeleted],
            'linetypes':[(str(g.Id),int(g.DataCRC(0))) for g in d.Linetypes if not g.IsDeleted],
            'render_materials':[(str(g.Id),g.Xml) for g in d.RenderMaterials] }

def transaction(code,require_solids=True,dry_run=False):
    """Trusted geometry/object-attribute edits only. This is not a Python sandbox."""
    target=sc.doc;stamp=_object_stamp(target)
    backup=Path(os.environ.get('TMPDIR','/tmp'))/('rhino-transaction-'+uuid.uuid4().hex+'.3dm')
    verified_save(str(backup),False,True)
    staged=Rhino.RhinoDoc.OpenHeadless(str(backup))
    if staged is None:raise RuntimeError('Could not open isolated staging document')
    old=[(o.Id,o.Geometry.Duplicate(),o.Attributes.Duplicate()) for o in live(target)]
    namespace={'Rhino':Rhino,'sc':sc,'result':None};committed=False;rollback=None
    try:
        baseline=_table_stamp(staged);sc.doc=staged
        exec(compile(code,'<rhino_geometry_transaction>','exec'),namespace)
        if sc.doc!=staged:raise RuntimeError('Transaction changed script document; unsupported')
        if _table_stamp(staged)!=baseline:raise RuntimeError('Transactions may not change document tables, materials, units, tolerances or document strings')
        report=validate_assembly(require_solids=require_solids)
        if not report['geometry_pass']:raise RuntimeError('Staged geometry failed validation: '+str(report['invalid_or_non_solid_ids']))
        if _object_stamp(target)!=stamp:raise RuntimeError('Target changed during staging; refusing commit')
        if dry_run:return {'committed':False,'dry_run':True,'result':namespace.get('result'),'validation':report,'backup_path':str(backup)}
        # Remap staged table indices by stable layer/material IDs from the snapshot.
        layer_map={l.Index:next((t.Index for t in target.Layers if t.Id==l.Id),-1) for l in staged.Layers if not l.IsDeleted}
        material_map={m.MaterialIndex:next((t.MaterialIndex for t in target.Materials if t.Id==m.Id),-1) for m in staged.Materials if not m.IsDeleted}
        desired=[]
        for o in live(staged):
            a=o.Attributes.Duplicate();a.LayerIndex=layer_map.get(a.LayerIndex,-1)
            if a.LayerIndex<0:raise RuntimeError('Layer mapping failed')
            if a.MaterialIndex>=0:
                a.MaterialIndex=material_map.get(a.MaterialIndex,-1)
                if a.MaterialIndex<0:raise RuntimeError('Material mapping failed')
            desired.append((o.Id,o.Geometry.Duplicate(),a))
        sc.doc=target
        try:
            wanted=set(str(row[0]) for row in desired)
            for o in live(target):
                if str(o.Id) not in wanted and not target.Objects.Delete(o.Id,True):raise RuntimeError('Commit deletion failed')
            for oid,g,a in desired:
                if target.Objects.FindId(oid):
                    if not target.Objects.Replace(oid,g):raise RuntimeError('Commit replacement failed')
                    if not target.Objects.ModifyAttributes(oid,a,True):raise RuntimeError('Commit attributes failed')
                else:
                    a.ObjectId=oid
                    new_id=target.Objects.Add(g,a)
                    if new_id==System.Guid.Empty:raise RuntimeError('Commit addition failed')
            checked=validate_assembly(require_solids=require_solids)
            if not checked['geometry_pass']:raise RuntimeError('Committed geometry failed validation')
            committed=True
        except Exception as commit_error:
            # Explicit restoration rather than unreliable programmatic Rhino Undo.
            rollback_errors=[]
            try:
                for o in live(target):
                    if not target.Objects.Delete(o.Id,True):rollback_errors.append('delete '+str(o.Id))
                for oid,g,a in old:
                    a.ObjectId=oid
                    if target.Objects.Add(g,a)==System.Guid.Empty:rollback_errors.append('restore '+str(oid))
                if _object_stamp(target)!=stamp:rollback_errors.append('restored object stamp differs')
            except Exception as exc:rollback_errors.append(str(exc))
            raise RuntimeError('Commit failed: %s; rollback_errors=%s; recovery_snapshot=%s' % (commit_error,rollback_errors,backup))
        target.Views.Redraw()
        return {'committed':True,'result':namespace.get('result'),'validation':checked,'backup_path':str(backup),'scope':'geometry and object attributes; no external side-effect rollback'}
    finally:
        sc.doc=target;staged.Dispose()

def inspect_document():return document_info(sc.doc)
