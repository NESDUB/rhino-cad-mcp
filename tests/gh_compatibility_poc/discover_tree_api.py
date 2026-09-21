import Grasshopper as GH,System,json
from pathlib import Path
found=[]
for proxy in GH.Instances.ComponentServer.ObjectProxies:
 if proxy.Desc and proxy.Desc.Name in ['Addition','Tree Statistics','Tree Statistics (Topology)','Param Viewer','Flip Matrix','Tree Branch']:
  o=proxy.CreateInstance()
  if hasattr(o,'Params'):
   found.append({'name':o.Name,'guid':str(proxy.Guid),'obsolete':o.Obsolete,'inputs':[(p.Name,p.TypeName,str(p.Access)) for p in o.Params.Input],'outputs':[(p.Name,p.TypeName,str(p.Access)) for p in o.Params.Output]})
p=GH.Kernel.Parameters.Param_Number()
props=[]
for prop in p.GetType().GetProperties():
 if prop.Name in ['DataMapping','Reverse','Simplify','Access']:
  props.append({'name':prop.Name,'type':str(prop.PropertyType.FullName),'enum':list(System.Enum.GetNames(prop.PropertyType)) if prop.PropertyType.IsEnum else None})
result={'components':found,'properties':props}
Path('/Users/nes/bin/mcp/rhino-cad-mcp/tests/gh_compatibility_poc/tree_api_inventory.json').write_text(json.dumps(result,indent=2))
