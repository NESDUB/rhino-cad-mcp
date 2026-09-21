"""Check observable trace boundaries and equivalence to normal solves."""
import math

def check_trace(report):
    checks=[]
    def ck(n,v):checks.append({'check':n,'passed':bool(v)})
    def clean(v):
        if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if k not in ['instance_id','processor_ms']}
        if isinstance(v,list):return [clean(x) for x in v]
        return v
    def first(pin):return pin['tree'][0]['items'][0]
    ck('16 runs',len(report['runs'])==16)
    for row in report['runs']:
        tag=row['case']+' '+row['mode']+' '+str(row['repeat'])
        ck(tag+' no harness exception','harness_exception' not in row)
        if 'harness_exception' in row:continue
        stages={s['label']:s['state'] for s in row['stages']}
        initial=stages['wired_unsolved']
        ck(tag+' initially unsolved',initial['source']['outputs'][0]['raw_count']==0 and initial['receiver']['outputs'][0]['raw_count']==0)
        if row['mode']=='normal':
            ck(tag+' normal solution finished',row['document_solution_state']=='PostProcess');continue
        try:
            source=stages['source_compute']['source']['outputs'][0]
            collected=stages['receiver_collect']['receiver'];pin=collected['inputs'][0]
            final=stages['receiver_compute']['receiver']
            ck(tag+' source really produced data',source['valid_count']>0)
            ck(tag+' source collection alone has no output',stages['source_collect']['source']['outputs'][0]['raw_count']==0)
            ck(tag+' receiver not computed during collection',collected['phase']=='Collected' and collected['outputs'][0]['raw_count']==0)
            ck(tag+' source unaffected by receiver',clean(source)==clean(stages['receiver_compute']['source']['outputs'][0]))
            normal=next(r for r in report['runs'] if r['case']==row['case'] and r['repeat']==row['repeat'] and r['mode']=='normal')
            ck(tag+' staged matches normal observable final state',clean(stages['receiver_compute'])==clean(normal['stages'][-1]['state']))
            if row['case']=='addition_to_brep_edges':
                ck(tag+' conversion fails at collection',pin['null_count']==1 and pin['valid_count']==0 and pin['errors']==['Data conversion failed from Complex to Brep'])
                ck(tag+' upstream numeric result retained',first(source)['text']=='{5, 0}')
                ck(tag+' computed does not imply usable output',final['phase']=='Computed' and final['run_count']==1 and all(p['valid_count']==0 for p in final['outputs']))
            else:
                ck(tag+' circle exists before conversion',first(source)['type'].endswith('GH_Circle') and first(source)['measurements']['radius']==5)
                target='GH_Brep' if row['case']=='circle_to_brep_edges' else 'GH_Curve'
                ck(tag+' target conversion visible during collection',first(pin)['type'].endswith(target) and pin['valid_count']==source['valid_count'] and not pin['errors'])
                if row['case']=='circle_to_loft_insufficient':
                    ck(tag+' error arises only at computation',not collected['errors'] and final['errors']==['Loft could not be constructed.'] and final['outputs'][0]['null_count']==1)
                elif row['case']=='circle_to_loft_success':
                    m=first(final['outputs'][0])['measurements']
                    ck(tag+' expected loft geometry',abs(m['area']-100*math.pi)<.01 and abs(m['bounds_max'][2]-10)<.001 and abs(m['bounds_min'][2])<.001)
                else:
                    m=first(pin)['measurements']
                    ck(tag+' circle converted to planar face',m['faces']==1 and abs(m['area']-25*math.pi)<.01 and abs(m['bounds_max'][2]-m['bounds_min'][2])<.001)
                    ck(tag+' expected extracted circumference',abs(first(final['outputs'][0])['geometry']['length']-10*math.pi)<.001)
        except (KeyError,IndexError,StopIteration,TypeError):ck(tag+' complete evidence',False)
    ck('user documents preserved',all(report['isolation'].values()))
    return {'passed':all(c['passed'] for c in checks),'count':len(checks),'checks':checks}

if __name__=='__main__':
    import json,sys
    result=check_trace(json.load(open(sys.argv[1])));print(json.dumps(result,indent=2));sys.exit(0 if result['passed'] else 1)
