"""Explicit measured tree outcomes. No universal GH path-matching claims."""
EXPECTED={
'branch_counts_swapped':(6,[('{2}',['11','12']),('{9}',['103','104']),('{12}',['1003','1004'])]),
'reverse_multibranch':(4,[('{0}',['12','11']),('{7}',['14','13'])]),
'loft_baseline':(2,[('{0}',['Untrimmed Surface']),('{7}',['Untrimmed Surface'])]),
'unequal':(3,[('{0}',['11','22','23'])]),'unequal_swapped':(3,[('{0}',['11','22','23'])]),
'scalar':(3,[('{0}',['11','12','13'])]),
'same_paths':(4,[('{0}',['11','12']),('{7}',['103','104'])]),
'different_paths':(4,[('{0}',['11','12']),('{7}',['103','104'])]),
'different_branch_counts':(6,[('{0}',['11','12']),('{7}',['103','104']),('{8}',['1003','1004'])]),
'flatten_A':(8,[('{0}',['11','12','13','14']),('{7}',['101','102','103','104'])]),
'graft_A':(6,[('{0;0}',['11','21']),('{0;1}',['12','22']),('{0;2}',['13','23'])]),
'graft_both':(3,[('{0;0}',['11']),('{0;1}',['22']),('{0;2}',['23'])]),
'reverse_A':(3,[('{0}',['13','22','21'])]),
'simplify_A':(4,[('{0}',['11','12']),('{7}',['103','104'])]),
'sources_AB':(4,[('{0}',['11','12','110','210'])]),
'sources_BA':(4,[('{0}',['110','210','11','12'])]),
'sources_disjoint':(4,[('{0}',['11','12']),('{7}',['110','210'])]),
'sources_reverse':(4,[('{0}',['210','110','12','11'])]),
'loft_flatten':(1,[('{0}',['Untrimmed Surface'])]),
'loft_graft':(4,[('{0;0}',[None]),('{0;1}',[None]),('{7;0}',[None]),('{7;1}',[None])]),
 'tree_statistics':(1,[('{0}',['{0}','{7}'])]),
 'flip_matrix':(1,[('{0}',['1','10']),('{1}',['2','20'])]),
 'flip_ragged':(1,[('{0}',['1','10']),('{1}',['2',None])])}
def tree(pin):return [(b['path'],[None if v['null'] else v['text'] for v in b['items']]) for b in pin['tree']]
def check_tree(report):
    checks=[]
    def ck(n,v):checks.append({'check':n,'passed':bool(v)})
    ck('46 runs',len(report['runs'])==46)
    ck('complete repeated fixtures',sorted((r['case'],r['repeat']) for r in report['runs'])==sorted((n,i) for n in EXPECTED for i in range(2)))
    for r in report['runs']:
        tag=r['case']+' '+str(r['repeat']);ck(tag+' no exception','harness_exception' not in r)
        if 'component' not in r:continue
        try:
            c=r['component'];name=r['case'];runs,expected=EXPECTED[name]
            ck(tag+' solve finished',r['solver']=='PostProcess' and c['phase']=='Computed')
            ck(tag+' current component',not c['obsolete'])
            ck(tag+' iteration count',c['run_count']==runs)
            ck(tag+' exact output paths values and null positions',tree(c['outputs'][0])==expected)
            ck(tag+' severity',c['level']==('Error' if name=='loft_graft' else 'Blank'))
            if name.startswith('sources_'):
                ck(tag+' source order recorded',r['settings'][0]['source_ids']==[s['instance_id'] for s in r['sources'][:2]])
                if name=='sources_reverse':ck(tag+' reverse after merging',tree(c['inputs'][0])==[('{0}',['200','100','2','1'])])
            if name=='simplify_A':ck(tag+' prefix removed in collected input only',tree(r['sources'][0])[0][0]=='{5;0}' and tree(c['inputs'][0])[0][0]=='{0}')
            if name=='reverse_multibranch':ck(tag+' paths not reversed',tree(c['inputs'][0])==[('{0}',['2','1']),('{7}',['4','3'])])
            if name=='tree_statistics':
                ck(tag+' whole tree one call',c['inputs'][0]['access']=='tree' and len(c['inputs'][0]['tree'])==2 and c['run_count']==1)
                ck(tag+' lengths and branch count',tree(c['outputs'][1])==[('{0}',['2','2'])] and tree(c['outputs'][2])==[('{0}',['2'])])
            if name.startswith('loft_'):ck(tag+' list input',c['inputs'][0]['access']=='list')
            if name=='different_branch_counts':ck(tag+' generated path not in inputs','{8}' not in [b['path'] for p in c['inputs'] for b in p['tree']])
        except (KeyError,IndexError,TypeError):ck(tag+' complete evidence',False)
    ck('user documents unchanged',all(report['isolation'].values()))
    return {'passed':all(x['passed'] for x in checks),'count':len(checks),'checks':checks}
if __name__=='__main__':
    import json,sys
    r=check_tree(json.load(open(sys.argv[1])));print(json.dumps(r,indent=2));sys.exit(0 if r['passed'] else 1)
