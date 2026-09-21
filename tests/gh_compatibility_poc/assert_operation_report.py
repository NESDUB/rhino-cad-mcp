"""Version-specific assertions for measured operation diagnostics, not universal GH rules."""
def check_operation_report(report):
    checks=[]
    def ck(name,condition):checks.append({'check':name,'passed':bool(condition)})
    def items(pin):return [v for branch in pin['tree'] for v in branch['items']]
    levels={'division_generic_by_zero':'Error','division_complex_by_zero':'Blank','loft_two_same_branch':'Blank','boundary_invalid_curve':'Warning','loft_single':'Error','loft_split_branches':'Error','loft_mixed_branches':'Error','circle_zero':'Blank','circle_negative':'Blank','divide_zero':'Blank','divide_negative':'Warning','interpolate_one_point':'Error','interpolate_bad_degree':'Warning','line_coincident':'Blank','list_out_of_range':'Warning','division_by_zero':'Blank','boundary_open':'Warning','boundary_nonplanar':'Warning','intersection_empty':'Blank','upstream_failure_cascade':'Blank'}
    ck('all 40 fixtures present',len(report['cases'])==40)
    ck('two repetitions of every fixture',sorted((r['case'],r['repeat']) for r in report['cases'])==sorted((k,i) for k in levels for i in range(2)))
    for row in report['cases']:
        name=row['case'];tag=name+' repeat '+str(row['repeat'])
        ck(tag+' no harness failure','harness_exception' not in row)
        if 'component' not in row:continue
        c=row['component'];out=c['outputs'];pin=c['inputs']
        ck(tag+' actual solution',row['solver']=='PostProcess' and c['phase']=='Computed')
        ck(tag+' measured severity',c['level']==levels[name])
        try:
            if name=='loft_two_same_branch':ck(tag+' valid output',out[0]['valid_count']==1)
            elif name=='loft_single':ck(tag+' operation error despite valid curve',pin[0]['valid_count']==1 and out[0]['null_count']==1 and c['errors']==['Loft could not be constructed.'])
            elif name=='loft_split_branches':ck(tag+' two failed list iterations',c['run_count']==2 and out[0]['null_count']==2 and len(c['errors'])==1)
            elif name=='loft_mixed_branches':
                ck(tag+' partial results retained',c['run_count']==3 and out[0]['valid_count']==1 and out[0]['null_count']==2)
                ck(tag+' messages are not failure counts',len(c['errors'])==1)
                ck(tag+' successful branch identifiable',out[0]['tree'][0]['path']=='{0}' and out[0]['tree'][0]['items'][0]['valid'])
            elif name in ['circle_zero','line_coincident']:
                expected='Circle radius is too small.' if name=='circle_zero' else 'Line is too short.'
                ck(tag+' invalid despite no messages',not c['errors'] and not c['warnings'] and out[0]['raw_count']==1 and out[0]['valid_count']==0)
                ck(tag+' detailed Goo reason',items(out[0])[0]['why_not']==expected)
            elif name=='circle_negative':ck(tag+' normalized radius',items(out[0])[0]['geometry']['radius']==5 and out[0]['valid_count']==1)
            elif name=='divide_zero':ck(tag+' empty without warning',all(p['raw_count']==0 for p in out) and not c['warnings'])
            elif name=='divide_negative':ck(tag+' specific constraint','The division count must be at least 0.' in c['warnings'])
            elif name=='interpolate_one_point':ck(tag+' specific failure','Insufficient interpolation points for a curve' in c['errors'])
            elif name=='interpolate_bad_degree':ck(tag+' corrected output despite warning','Curve degree must be higher than zero' in c['warnings'] and out[0]['valid_count']==1)
            elif name=='list_out_of_range':ck(tag+' specific list warning','Supplied index too high.' in c['warnings'] and out[0]['null_count']==1)
            elif name=='division_generic_by_zero':ck(tag+' current implementation reports zero division',not c['obsolete'] and c['errors']==['Division by zero'] and out[0]['null_count']==1)
            elif name=='division_by_zero':ck(tag+' obsolete finite sentinel',c['obsolete'] and items(out[0])[0]['native_number']['equals_double_max'] and items(out[0])[0]['native_number']['finite'] and out[0]['valid_count']==1)
            elif name=='division_complex_by_zero':ck(tag+' obsolete invalid infinity',c['obsolete'] and out[0]['valid_count']==0 and 'positive infinity' in items(out[0])[0]['why_not'])
            elif name.startswith('boundary_'):
                ck(tag+' shared vague warning',c['warnings']==['Planar surface routine returned no results'])
                value=items(pin[0])[0]
                if name=='boundary_invalid_curve':ck(tag+' deeper native explanation',value['native_validation_log']=='Line points are coincident.' and not value['valid'])
                elif name=='boundary_open':ck(tag+' valid planar but open',value['valid'] and value['geometry']['planar_at_0_01'] and not value['geometry']['closed'])
                else:ck(tag+' valid closed but nonplanar',value['valid'] and value['geometry']['closed'] and not value['geometry']['planar_at_0_01'])
            elif name=='intersection_empty':ck(tag+' legitimate no-intersection result',all(p['valid_count']==1 for p in pin) and all(p['raw_count']==0 for p in out))
            elif name=='upstream_failure_cascade':ck(tag+' upstream error not propagated',row['upstream']['level']=='Error' and not c['errors'] and not c['warnings'] and pin[0]['null_count']==1 and all(p['raw_count']==0 for p in out))
        except (KeyError,IndexError,TypeError):ck(tag+' complete diagnostic fields',False)
    ck('two repair fixtures',len(report['repairs'])==2)
    for repair in report['repairs']:
        tag='repair repeat '+str(repair['repeat']);ck(tag+' no harness failure','harness_exception' not in repair)
        if 'before' not in repair:continue
        a=repair['before'];b=repair['after']
        ck(tag+' same component corrected',a['instance_id']==b['instance_id'] and a['level']=='Error' and b['level']=='Blank' and not b['errors'] and b['outputs'][0]['valid_count']==1)
    ck('user documents unchanged',all(report['isolation'].values()))
    return {'passed':all(r['passed'] for r in checks),'count':len(checks),'checks':checks}

if __name__=='__main__':
    import json,sys
    result=check_operation_report(json.load(open(sys.argv[1])))
    print(json.dumps(result,indent=2));sys.exit(0 if result['passed'] else 1)
