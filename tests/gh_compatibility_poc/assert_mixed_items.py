"""Fixture-specific mixed-payload assertions, not universal component rules."""
def check_mixed(r):
    checks=[]
    def ck(n,v):checks.append({'check':n,'passed':bool(v)})
    def branch(pin,path):return next(b['items'] for b in pin['tree'] if b['path']==path)
    def sig(v):return 'null' if v['null'] else ('invalid' if not v['valid'] else ('text' if v['type'].endswith('GH_String') else 'valid'))
    ck('24 fixtures',len(r['runs'])==24)
    ck('complete repeated case grid',sorted((x['kind'],x['operation'],x['repeat']) for x in r['runs'])==sorted((k,o,i) for k in ['valid','null','incompatible','invalid','mixed','mixed_reversed'] for o in ['Divide Curve','Loft'] for i in range(2)))
    for row in r['runs']:
        tag='%s %s %s'%(row['kind'],row['operation'],row['repeat'])
        ck(tag+' harness succeeded','harness_exception' not in row)
        if 'state' not in row:continue
        try:
            s=row['state']['source'];p=row['state']['relay'];c=row['state']['receiver'];expected=[sig(i['value']) for i in row['intended']]
            converted=['null' if v=='text' else v for v in expected]
            ck(tag+' source preserves payload slots',[sig(v) for v in branch(s,'{0}')]==expected)
            ck(tag+' conversion preserves order and substitutes null',[sig(v) for v in branch(p,'{0}')]==converted)
            ck(tag+' receiver input retains collected slots',[sig(v) for v in branch(c['inputs'][0],'{0}')]==converted)
            ck(tag+' source branch matches persistent data',s['tree']==row['persistent_before_solve'])
            ck(tag+' control branch preserved',[sig(v) for v in branch(p,'{7}')]==['valid','valid'])
            ck(tag+' conversion error iff text present',('Data conversion failed from Text to Curve' in p['errors'])==('text' in expected))
            ck(tag+' solved',row['solver']=='PostProcess')
            out=c['outputs'][0]
            if row['operation']=='Divide Curve':
                ck(tag+' no downstream messages',c['level']=='Blank' and not c['errors'] and not c['warnings'])
                ck(tag+' runs include null slots',c['run_count']==len(expected)+2)
                for i,kind in enumerate(converted):
                    values=branch(out,'{0;%s}'%i)
                    ck(tag+' item '+str(i),len(values)==(0 if kind=='null' else 3 if kind=='invalid' else 2))
                    if kind=='invalid':ck(tag+' degenerate input yields duplicate valid points',all(v['valid'] and v['text']=='{0, 0, 0}' for v in values))
                ck(tag+' control output intact',all(len(branch(out,path))==2 for path in ['{7;0}','{7;1}']))
            else:
                ck(tag+' list operation runs per branch',c['run_count']==2)
                ck(tag+' valid control output',len(branch(out,'{7}'))==1 and branch(out,'{7}')[0]['valid'])
                bad='invalid' in converted;values=branch(out,'{0}')
                ck(tag+' branch outcome depends on invalid not null',len(values)==1 and (values[0]['null'] if bad else values[0]['valid']))
                ck(tag+' null removal warning',('Null profile curve was removed' in c['warnings'])==('null' in converted))
                ck(tag+' invalid warning',('Invalid profile curve in loft, this may cause problems.' in c['warnings'])==bad)
                ck(tag+' error matches heterogeneous closure',('Loft only works if all curves are open, or all curves are closed.' in c['errors'])==bad)
        except (KeyError,IndexError,StopIteration,TypeError):ck(tag+' complete diagnostic structure',False)
    ck('user documents unchanged',all(r['isolation'].values()))
    return {'passed':all(c['passed'] for c in checks),'count':len(checks),'checks':checks}
if __name__=='__main__':
    import sys,json
    result=check_mixed(json.load(open(sys.argv[1])));print(json.dumps(result,indent=2));sys.exit(0 if result['passed'] else 1)
