"""Pure Python regression assertions. No Rhino dependency.
CLI: python3 assert_report.py run_TIMESTAMP.json
"""
def check_report(report):
    checks=[]
    def record(name,passed):checks.append({'check':name,'passed':bool(passed)})
    cases=report['cases']
    record('ten component fixtures executed',len(cases)==10)
    for c in cases:
        tag=c['case']+' repeat '+str(c['repetition'])
        record(tag+' no harness exception','harness_exception' not in c)
        if 'receiver' not in c:continue
        r=c['receiver'];pin=r['inputs'][0];out=r['outputs'];kind=c['case']
        record(tag+' solver completed',c['enabled'] and c['solver_state']=='PostProcess')
        if c['wiring']:record(tag+' wire accepted',all(w['accepted'] for w in c['wiring']))
        if kind=='two_circles_to_loft':
            record(tag+' successful conversion and geometry',pin['valid_count']==2 and r['level']=='Blank' and out[0]['valid_count']==1)
        elif kind=='one_circle_to_loft':
            record(tag+' conversion success but operation failure',pin['valid_count']==1 and not pin['errors'] and r['level']=='Error' and 'Loft could not be constructed.' in r['errors'] and out[0]['valid_count']==0)
        elif kind=='missing_loft_curves':
            record(tag+' missing-data warning',pin['valid_count']==0 and pin['sources']==0 and r['level']=='Warning' and bool(pin['warnings']))
        elif kind=='addition_to_brep_edges':
            record(tag+' upstream value exists',c['source']['outputs'][0]['valid_count']==1)
            record(tag+' conversion error diagnosed',r['level']=='Error' and pin['valid_count']==0 and 'Data conversion failed from Complex to Brep' in pin['errors'])
        elif kind=='circle_to_brep_edges':
            record(tag+' implicit geometric conversion',pin['valid_count']==1 and r['level']=='Blank' and out[0]['valid_count']==1)
    casts={r['case']:r for r in report['casts']}
    record('CastFrom succeeds where CastTo GH wrapper fails',casts['circle_to_curve']['cast_from_ok'] and not casts['circle_to_curve']['cast_to_ok'])
    record('curve conversion depends on geometry',casts['circular_curve_to_circle']['cast_from_ok'] and not casts['line_to_circle']['cast_from_ok'])
    record('cast tests free of interop exceptions',not any('exception' in k for row in report['casts'] for k in row))
    for r in report['parameter_cases']:
        tag=r['case']+' repeat '+str(r['repetition'])
        record(tag+' parameter harness succeeded','harness_exception' not in r)
        if 'receiver' not in r:continue
        p=r['receiver'];name=r['case']
        if name=='circular_curve_to_circle':record(tag+' converted',p['level']=='Blank' and p['valid_count']==1)
        elif name=='line_curve_to_circle':record(tag+' rejected',p['level']=='Error' and p['valid_count']==0)
        else:
            expected='-43' if 'negative' in name else '43'
            record(tag+' rounding is not truncation',p['level']=='Blank' and p['valid_count']==1 and p['data'][0]['value']==expected)
    for r in report['native_cast_controls']:
        expected=r['case']!='circle_to_native_curve'
        record(r['case']+' measured conversion behavior',r.get('ok') is expected and 'harness_exception' not in r)
    record('user documents unchanged',all(report['isolation'].values()))
    return {'passed':all(c['passed'] for c in checks),'count':len(checks),'checks':checks}

if __name__=='__main__' and '__file__' in globals() and __file__.endswith('assert_report.py'):
    import sys,json
    result=check_report(json.load(open(sys.argv[1])))
    print(json.dumps(result,indent=2))
    sys.exit(0 if result['passed'] else 1)
