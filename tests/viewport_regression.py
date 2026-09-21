"""End-to-end viewport regression runner for the six-color orientation cube."""
import argparse, asyncio, json, os, sys, time
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
EXPECTED = {'+X_RIGHT': [220,20,30], '-X_LEFT': [20,60,220], '+Y_BACK': [20,170,45], '-Y_FRONT': [240,210,20], '+Z_TOP': [220,30,210], '-Z_BOTTOM': [20,210,220]}

async def main():
    parser=argparse.ArgumentParser(description='Run viewport regression against any open Rhino document')
    parser.add_argument('--path',default='viewport_orientation_cube.3dm',help='Open document filename/path suffix')
    parser.add_argument('--prefix',default='',help='Output filename prefix')
    args=parser.parse_args()
    receipts=[]
    params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'server.py')],env=dict(os.environ))
    async with stdio_client(params) as (rd,wr):
        async with ClientSession(rd,wr) as session:
            await session.initialize()
            async def call(name,args):
                res=await session.call_tool(name,args)
                raw=''.join(getattr(c,'text','') for c in res.content)
                try: data=json.loads(raw)
                except Exception: data={'ok':False,'kind':'non_json_response','raw':raw}
                receipts.append({'tool':name,'args':args,'data':data})
                if res.isError or data.get('ok') is False: raise RuntimeError('%s failed: %s'%(name,data))
                return data
            docs=(await call('rhino_list_documents',{}))['result']['documents']
            target=next((d for d in docs if (d.get('path') or '').endswith(args.path) and not d.get('headless')),None)
            if target is None: raise RuntimeError('Open a GUI document matching '+args.path+' before running this regression')
            did=target['document_id']; info=(await call('rhino_inspect_document',{'document_id':did}))['result']
            if info['live_object_count']==0: raise RuntimeError('Target document is empty')
            verify_code="""import Rhino,scriptcontext as sc
expected=%s
rows=[]
for o in list(sc.doc.Objects):
 a=o.Attributes; rm=o.RenderMaterial; sim=None if rm is None else rm.SimulatedMaterial(Rhino.Render.RenderTexture.TextureGeneration.Allow); p=None if sim is None else sim.PhysicallyBased; c=None if p is None else p.BaseColor
 base=None if c is None else [round(c.R*255),round(c.G*255),round(c.B*255)]
 rows.append({'name':a.Name,'color_source':str(a.ColorSource),'has_render_material':rm is not None,'render_type':None if rm is None else rm.TypeName,'pbr':bool(sim is not None and sim.IsPhysicallyBased),'base_color':base,'expected':expected.get(a.Name)})
result={'faces':rows,'pass':len(rows)==6 and all(x['name'] in expected and x['color_source']=='ColorFromObject' and x['has_render_material'] and x['render_type']=='Physically Based' and x['pbr'] and x['base_color']==x['expected'] for x in rows)}""" % json.dumps(EXPECTED)
            color=None
            names={o.get('name') for o in info['objects']}
            if set(EXPECTED).issubset(names):
                color=(await call('rhino_run',{'document_id':did,'code':verify_code}))['result']
                if not color.get('pass'): raise RuntimeError('Color verification failed: '+json.dumps(color))
            views=[{'name':'front','direction':[0,-1,0]},{'name':'back','direction':[0,1,0]},{'name':'left','direction':[-1,0,0]},{'name':'right','direction':[1,0,0]},{'name':'top','direction':[0,0,1]},{'name':'bottom','direction':[0,0,-1]},{'name':'iso_upper_right','direction':[1,-1,1]},{'name':'iso_lower_left','direction':[-1,-1,-1]}]
            modes=['Wireframe','Shaded','Rendered','Arctic','Technical','Ghosted']
            for mode in modes:
                stem=args.prefix or Path(target.get('path') or 'rhino_model').stem
                p=OUT/(stem+'_regression_'+mode.lower()+'.png')
                if p.exists(): p.unlink()
                r=(await call('rhino_capture_views',{'document_id':did,'views':views,'width':256,'height':192,'square':True,'output_path':str(p),'display_mode':mode,'parallel':True,'columns':4}))['result']
                assert r['view_count']==8 and r['restored'] and Path(r['manifest_path']).exists()
                manifest=json.loads(Path(r['manifest_path']).read_text()); assert manifest['aspect_ratio']==1.0 and manifest['square_requested']
            receipt={'passed':True,'document_id':did,'target_path':target.get('path'),'object_count':info['live_object_count'],'face_verification':color,'modes':modes,'receipts':receipts,'timestamp':time.time()}
            receipt_path=OUT/((args.prefix or Path(target.get('path') or 'rhino_model').stem)+'_viewport_regression_receipt.json')
            receipt_path.write_text(json.dumps(receipt,indent=2))
            print(json.dumps({'passed':True,'document_id':did,'object_count':info['live_object_count'],'modes':modes,'receipt':str(receipt_path)}))

if __name__=='__main__': asyncio.run(main())
