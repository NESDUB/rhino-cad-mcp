"""Probe 3: unequal lists, tree matching, transformations, multiple sources,
and item/list/tree access. Private GH docs; Python 3.9 compatible.
"""
from pathlib import Path
import json,time,traceback
ROOT=Path('/Users/nes/bin/mcp/rhino-cad-mcp/tests/gh_compatibility_poc')
exec(compile((ROOT/'operation_errors_probe.py').read_text().split('\nbefore=Rhino.RhinoDoc.ActiveDoc')[0],'diagnostic_helpers','exec'))
IDS.update({'Addition Current':'a0d62394-a118-422d-abb3-6af115c75b25','Tree Statistics':'99bee19d-588c-41a0-b9b9-1d00fb03ea1a','Flip Matrix':'41aa4112-9c9b-42f4-847e-503b9d90e4c7'})
def src(d,branches,curve=False):
    p=P.Param_Curve() if curve else P.Param_Number();p.CreateAttributes()
    for path,items in branches:
        for v in items:p.PersistentData.Append(v if curve else T.GH_Number(v),GH_Path(System.Array[System.Int32](path)))
    d.AddObject(p,False);return p

def options(p):return {'mapping':str(p.DataMapping),'reverse':bool(p.Reverse),'simplify':bool(p.Simplify),'source_ids':[str(s.InstanceGuid) for s in p.Sources]}
base=[([0],[1,2,3])];short=[([0],[10,20])]
cases=['branch_counts_swapped','reverse_multibranch','loft_baseline','unequal','unequal_swapped','scalar','same_paths','different_paths','different_branch_counts','flatten_A','graft_A','graft_both','reverse_A','simplify_A','sources_AB','sources_BA','sources_disjoint','sources_reverse','loft_flatten','loft_graft','tree_statistics','flip_matrix','flip_ragged']
before=Rhino.RhinoDoc.ActiveDoc;ids=sorted(str(o.Id) for o in before.Objects if not o.IsDeleted)
canvas=None if GH.Instances.ActiveCanvas is None else GH.Instances.ActiveCanvas.Document
report={'runtime':str(GH.Instances.ComponentServer.GetType().Assembly.FullName),'runs':[],'component_ids':IDS}
for repeat in range(2):
 for case in cases:
  d=GH_Document();d.Enabled=True;row={'case':case,'repeat':repeat}
  try:
   sources=[]
   if case.startswith('loft_'):
    c=comp(d,'Loft')
    a=[([0],[circle(),circle(10)]),([7],[circle(30),circle(40)])]
    s=src(d,a,True);sources.append(s);c.Params.Input[0].AddSource(s)
    if case!='loft_baseline':c.Params.Input[0].DataMapping=GH.Kernel.GH_DataMapping.Flatten if case=='loft_flatten' else GH.Kernel.GH_DataMapping.Graft
   elif case in ['tree_statistics','flip_matrix','flip_ragged']:
    c=comp(d,'Tree Statistics' if case=='tree_statistics' else 'Flip Matrix')
    a=[([0],[1,2]),([7],[10] if case=='flip_ragged' else [10,20])]
    s=src(d,a);sources.append(s);c.Params.Input[0].AddSource(s)
   else:
    c=comp(d,'Addition Current');a=base;b=short
    if case=='unequal_swapped':a,b=short,base
    if case=='scalar':b=[([0],[10])]
    if case in ['same_paths','different_paths','different_branch_counts','flatten_A']:
     a=[([0],[1,2]),([7],[3,4])]
     b=[([0],[10]),([7],[100])]
     if case=='different_paths':b=[([2],[10]),([9],[100])]
     if case=='different_branch_counts':b=[([2],[10]),([9],[100]),([12],[1000])]
    if case=='branch_counts_swapped':a=[([2],[10]),([9],[100]),([12],[1000])];b=[([0],[1,2]),([7],[3,4])]
    if case=='reverse_multibranch':a=[([0],[1,2]),([7],[3,4])];b=[([0],[10])]
    if case=='simplify_A':a=[([5,0],[1,2]),([5,7],[3,4])];b=[([0],[10]),([7],[100])]
    if case.startswith('sources_'):
     a=[([0],[1,2])];other=[([7] if case=='sources_disjoint' else [0],[100,200])];b=[([0],[10])]
     ss=[src(d,a),src(d,other)]
     if case=='sources_BA':ss.reverse()
     sources.extend(ss)
     for s in ss:c.Params.Input[0].AddSource(s)
    else:
     s=src(d,a);sources.append(s);c.Params.Input[0].AddSource(s)
    s=src(d,b);sources.append(s);c.Params.Input[1].AddSource(s)
    if case=='flatten_A':c.Params.Input[0].DataMapping=GH.Kernel.GH_DataMapping.Flatten
    if case in ['graft_A','graft_both']:c.Params.Input[0].DataMapping=GH.Kernel.GH_DataMapping.Graft
    if case=='graft_both':c.Params.Input[1].DataMapping=GH.Kernel.GH_DataMapping.Graft
    if case in ['reverse_A','sources_reverse','reverse_multibranch']:c.Params.Input[0].Reverse=True
    if case=='simplify_A':c.Params.Input[0].Simplify=True
   row['settings']=[options(p) for p in c.Params.Input]
   solve(d);row['sources']=[snapshot(s) for s in sources];row['component']=snapshot(c);row['solver']=str(d.SolutionState)
  except Exception:row['harness_exception']=traceback.format_exc()
  finally:d.Dispose()
  report['runs'].append(row)
report['isolation']={'same_rhino':before==Rhino.RhinoDoc.ActiveDoc,'same_objects':ids==sorted(str(o.Id) for o in before.Objects if not o.IsDeleted),'same_canvas':canvas==(None if GH.Instances.ActiveCanvas is None else GH.Instances.ActiveCanvas.Document)}
p=ROOT/('tree_matching_'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,indent=2,default=str))
result={'path':str(p),'runs':len(report['runs']),'exceptions':[r for r in report['runs'] if 'harness_exception' in r],'isolation':report['isolation']}
