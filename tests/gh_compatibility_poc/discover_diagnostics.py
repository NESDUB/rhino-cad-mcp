import Grasshopper as GH, System, json
from pathlib import Path
names=['Loft','Circle','Line','Interpolate','Divide Curve','List Item','Division','Boundary Surfaces','Curve | Curve']
found=[]
for proxy in GH.Instances.ComponentServer.ObjectProxies:
    if proxy.Desc and proxy.Desc.Name in names:
        obj=proxy.CreateInstance()
        if not hasattr(obj,'Params'):continue
        found.append({'name':obj.Name,'category':obj.Category,'subcategory':obj.SubCategory,'guid':str(proxy.Guid),'type':str(obj.GetType().FullName),'inputs':[{'name':p.Name,'nickname':p.NickName,'type':p.TypeName,'access':str(p.Access),'optional':p.Optional,'description':p.Description} for p in obj.Params.Input],'outputs':[{'name':p.Name,'type':p.TypeName} for p in obj.Params.Output], 'diagnostic_properties':[{'name':p.Name,'type':str(p.PropertyType.FullName)} for p in obj.GetType().GetProperties() if any(k in p.Name.lower() for k in ['error','warning','runtime','message','phase','count','time','solution','exception'])], 'diagnostic_methods':[str(m) for m in obj.GetType().GetMethods() if any(k in m.Name.lower() for k in ['error','warning','runtime','exception'])]})
path=Path('/Users/nes/bin/mcp/rhino-cad-mcp/tests/gh_compatibility_poc/diagnostic_api_inventory.json');path.write_text(json.dumps(found,indent=2));result={'path':str(path),'components':found}
