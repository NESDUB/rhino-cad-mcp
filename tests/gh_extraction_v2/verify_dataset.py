"""Host-side structural/evidence checks; pass explicit dataset path."""
import json,sys,collections,math
from pathlib import Path

def verify(data):
    c=data['components'];compat=data['type_compatibility'];pairs=compat['pairs'];checks=[]
    def ck(n,v):checks.append({'check':n,'passed':bool(v)})
    ck('completed traversal',data['metadata']['complete'])
    ck('component count',len(c)==data['metadata']['total_components'])
    addresses=[v['addresses']['global'] for v in c.values()]
    ck('unique addresses',len(addresses)==len(set(addresses)))
    ck('GUID sorted addresses',addresses==['C%04d'%(i+1) for i in range(len(c))] and list(c)==sorted(c))
    sn={p['goo_type'] for r in c.values() for p in r['outputs'] if p['goo_type']}
    tn={p['goo_type'] for r in c.values() for p in r['inputs'] if p['goo_type']}
    keys=[(p['source_goo'],p['target_goo']) for p in pairs]
    ck('complete directional pair universe',len(keys)==len(sn)*len(tn) and set(keys)=={(s,t) for s in sn for t in tn})
    ck('no duplicate pair rows',len(keys)==len(set(keys)))
    sets=data['component_sets'];partition=sets['current_exposed']+sets['current_hidden']+sets['obsolete']
    ck('component partition',len(partition)==len(set(partition))==len(c) and set(partition)==set(c))
    ck('classification counts',sum(compat['counts'].values())==len(pairs))
    ck('isolation',all(data['metadata']['isolation'].values()))
    ck('known types reconciled',data['known_types']==sorted({p['typeName'] for r in c.values() for k in ['inputs','outputs'] for p in r[k]}))
    ck('constructor skips not rejections',all(not (s.get('reason','').startswith('target Goo') and isinstance(s.get('cast_from_ok'),bool)) for p in pairs for s in p['samples']))
    ck('no unsupported universal claims',all(p['universal_compatibility'] is None for p in pairs))
    def pair(s,t):return next(p for p in pairs if p['source_goo']=='Grasshopper.Kernel.Types.'+s and p['target_goo']=='Grasshopper.Kernel.Types.'+t)
    cp=pair('GH_Curve','GH_Circle');samples={s['label']:s for s in cp['samples']}
    ck('value-dependent curve-circle reproduced',cp['status']=='conditional_observed' and samples['circle_nurbs']['cast_from_ok'] and not samples['line_curve']['cast_from_ok'])
    circle=pair('GH_Circle','GH_Curve')['samples'][0]
    ck('circle to curve cast reproduced',circle['cast_from_ok'] and circle['cast_from_valid'])
    ck('circle to curve wire reproduced',any(w['status']=='observed_success' for w in circle.get('receiver_tests',[])))
    ck('number to brep negative control',all(s['cast_from_ok'] is False for s in pair('GH_Number','GH_Brep')['samples']))
    wr=[w for p in pairs for s in p['samples'] for w in s.get('receiver_tests',[])]
    counts=collections.Counter(w['status'] for w in wr)
    ck('successful wire trials actually solved',all(w.get('solver_state')=='PostProcess' and w['source']['valid_count']==1 and w['receiver']['valid_count']==1 for w in wr if w['status']=='observed_success'))
    return {'passed':all(x['passed'] for x in checks),'checks':checks,'wire_sample_counts':dict(counts),'cast_sample_errors':sum(s.get('status')=='error' for p in pairs for s in p['samples'])}
if __name__=='__main__':
    result=verify(json.loads(Path(sys.argv[1]).read_text()));print(json.dumps(result,indent=2));sys.exit(0 if result['passed'] else 1)
