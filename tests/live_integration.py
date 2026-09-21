"""Opt-in live MCP tests. Uses disposable documents; restores original GUI document."""
import asyncio,json,os,sys,tempfile,time,uuid
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
async def main():
 receipts=[];created=[];original=None;fail=None
 async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'server.py')],env=dict(os.environ))) as (rd,wr):
  async with ClientSession(rd,wr) as s:
   await s.initialize()
   async def call(name,args=None,expected_failure=False):
    res=await s.call_tool(name,args or {});texts=[c.text for c in res.content if hasattr(c,'text')]
    try:data=json.loads(texts[0])
    except Exception:data={'ok':False,'error':texts}
    receipts.append({'tool':name,'args':args,'data':data});print(name,json.dumps(data)[:1800],flush=True)
    if data.get('pending'):
     for _ in range(30):
      await asyncio.sleep(.2)
      q=await s.call_tool('rhino_job_wait',{'job_id':data['job_id'],'timeout_seconds':10});data=json.loads(q.content[0].text)
      if not data.get('pending'):break
    if not expected_failure and (res.isError or data.get('ok') is False):raise RuntimeError(str(data))
    if expected_failure:assert data.get('ok') is False or res.isError
    return data
   try:
    await call('rhino_status')
    docs=(await call('rhino_list_documents'))['result']['documents']
    original=next((d['document_id'] for d in docs if d['gui_active']),None)
    d=(await call('rhino_create_document',{'headless':True}))['result']['document_id'];created.append(d)
    code="""import Rhino,scriptcontext as sc
G=Rhino.Geometry
a=G.Sphere(G.Point3d(0,0,0),5).ToBrep();b=G.Sphere(G.Point3d(7,0,0),5).ToBrep()
x=sc.doc.Objects.AddBrep(a);y=sc.doc.Objects.AddBrep(b);z=sc.doc.Objects.AddBrep(a.DuplicateBrep());sc.doc.Objects.Delete(z,True)
result={'ids':[str(x),str(y)],'live':len(list(sc.doc.Objects))}
"""
    ids=(await call('rhino_run',{'code':code,'document_id':d}))['result']['ids']
    info=(await call('rhino_inspect_document',{'document_id':d}))['result'];assert info['live_object_count']==2
    await call('rhino_apply_material',{'document_id':d,'object_ids':[ids[0]],'name':'MCP test cherry enamel','base_color':[174,15,34],'roughness':.22,'clearcoat':.8})
    values=(await call('rhino_read_material',{'document_id':d,'object_id':ids[0]}))['result']['values'];assert values['is_pbr'] and abs(values['clearcoat']-.8)<1e-5
    report=(await call('rhino_validate_assembly',{'document_id':d,'check_intersections':True}))['result'];assert report['geometry_pass'];assert report['intersections']
    unchanged=(await call('rhino_transaction',{'document_id':d,'code':"import Rhino,scriptcontext as sc\nsc.doc.Objects.AddBrep(Rhino.Geometry.Sphere(Rhino.Geometry.Point3d(30,0,0),3).ToBrep())\nresult='staged'",'dry_run':True}))['result'];assert not unchanged['committed']
    assert (await call('rhino_inspect_document',{'document_id':d}))['result']['live_object_count']==2
    await call('rhino_transaction',{'document_id':d,'code':"import scriptcontext as sc\nfor o in list(sc.doc.Objects):sc.doc.Objects.Delete(o.Id,True)\nraise RuntimeError('injected staging failure')"},expected_failure=True)
    assert (await call('rhino_inspect_document',{'document_id':d}))['result']['live_object_count']==2
    committed=(await call('rhino_transaction',{'document_id':d,'code':"import Rhino,scriptcontext as sc\nsc.doc.Objects.AddBrep(Rhino.Geometry.Sphere(Rhino.Geometry.Point3d(30,0,0),3).ToBrep())\nresult='committed'"}))['result'];assert committed['committed']
    assert (await call('rhino_inspect_document',{'document_id':d}))['result']['live_object_count']==3
    path=str(Path(tempfile.mkdtemp(prefix='rhino-mcp-integration-'))/'verified.3dm')
    assert (await call('rhino_save',{'document_id':d,'file_path':path,'overwrite':False}))['result']['verified']
    key='live-'+uuid.uuid4().hex
    args={'document_id':d,'code':"result={'once':True}",'wait':False,'idempotency_key':key}
    one=await call('rhino_run',args);two=await call('rhino_run',args);assert one['job_id']==two['job_id']
    gui=(await call('rhino_open_document',{'file_path':path}))['result']['document_id'];created.append(gui)
    await call('rhino_activate_document',{'document_id':gui})
    await call('rhino_run',{'document_id':gui,'code':"import Rhino,scriptcontext as sc\nv=next(v for v in sc.doc.Views if v.ActiveViewport.Name=='Perspective');sc.doc.Views.ActiveView=v;v.ActiveViewport.ZoomExtents();sc.doc.Views.Redraw()\nresult=True"})
    cap=(await call('rhino_capture_viewport',{'document_id':gui,'width':640,'height':480,'preset':{'display_mode':'Rendered'}}))['result'];assert Path(cap['manifest_path']).exists();assert Path(cap['scene_archive']).exists()
    await call('rhino_inspect_document',{'document_id':'999999:1'},expected_failure=True)
   except Exception as exc:fail=repr(exc)
   finally:
    if original:
     try:await call('rhino_activate_document',{'document_id':original})
     except Exception as exc:receipts.append({'cleanup_error':str(exc)})
    # Dispose only the headless scratch document; leave GUI scratch open rather
    # than invoking a possibly interactive close or affecting user's documents.
    if created:
     try:await call('rhino_run',{'document_id':created[0],'code':"import scriptcontext as sc\nsc.doc.Dispose()\nresult={'disposed':True}"})
     except Exception as exc:receipts.append({'cleanup_error':str(exc)})
    (ROOT/'tests/live_receipt.json').write_text(json.dumps({'passed':fail is None,'failure':fail,'created_documents':created,'original_document':original,'calls':receipts},indent=2))
 if fail is not None:raise RuntimeError(fail)
 print('LIVE INTEGRATION PASSED')
asyncio.run(main())
