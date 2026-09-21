import ast, asyncio, json, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bridge
from tool_support import check_code

INSTANCE={'pid':123,'instance_id':'rhinocode_remotepipe_123','document_hint':''}
DISCOVERY={'ok':True,'instances':[INSTANCE]}
class BridgeTests(unittest.TestCase):
    def test_header_is_not_instance(self):
        self.assertEqual(bridge.parse_instances('PID ID DOC PATH\n'),[])
        with patch.object(bridge,'_run_cli',return_value=subprocess.CompletedProcess([],0,'PID ID DOC PATH\n','')):
            self.assertFalse(bridge.discover()['ok'])
    def test_real_instances_and_spaces(self):
        rows=bridge.parse_instances('PID ID DOC PATH\n 123 rhinocode_remotepipe_123 My Model.3dm /a path/model.3dm\n')
        self.assertEqual(rows[0]['pid'],123);self.assertIn('My Model',rows[0]['document_hint'])
    def test_ambiguous_target_rejected(self):
        with self.assertRaises(ValueError):bridge._choose([INSTANCE,dict(INSTANCE,pid=124,instance_id='another')])
    def test_pid_scoped_document(self):
        self.assertEqual(bridge._choose([INSTANCE],'123:77'),INSTANCE)
        with self.assertRaises(ValueError):bridge._choose([INSTANCE],'999:77')
        with self.assertRaises(ValueError):bridge._choose([INSTANCE],'77')
    def test_environment_repair(self):
        with tempfile.TemporaryDirectory() as t,patch.dict('os.environ',{},clear=True),patch('os.confstr',return_value=t):
            env,repaired=bridge.cli_environment();self.assertEqual(env['TMPDIR'],t);self.assertTrue(repaired)
    def test_environment_getconf_fallback(self):
        with tempfile.TemporaryDirectory() as t,patch.dict('os.environ',{},clear=True),patch('os.confstr',side_effect=ValueError),patch.object(bridge.sys,'platform','darwin'),patch.object(bridge.subprocess,'run',return_value=subprocess.CompletedProcess([],0,t+'\n','')):
            env,repaired=bridge.cli_environment();self.assertEqual(env['TMPDIR'],t);self.assertTrue(repaired)
    def test_status_requires_pong(self):
        with patch.object(bridge,'discover',return_value=dict(DISCOVERY)),patch.object(bridge,'execute',return_value={'ok':True,'pending':True}):self.assertFalse(bridge.status()['ok'])
    def test_late_result_and_idempotency(self):
        with tempfile.TemporaryDirectory() as t,patch.object(bridge,'JOBS',Path(t)),patch.object(bridge,'_run_cli',return_value=subprocess.CompletedProcess([],0,'','')) as cli:
            r=bridge.execute('result=1',timeout=0,_discovery=DISCOVERY,idempotency_key='once')
            self.assertTrue(r['pending']);p=Path(t)/r['job_id'];self.assertTrue((p/'script.py').exists())
            again=bridge.execute('result=1',timeout=0,_discovery=DISCOVERY,idempotency_key='once')
            self.assertEqual(r['job_id'],again['job_id']);self.assertEqual(cli.call_count,1)
            conflict=bridge.execute('result=2',timeout=0,_discovery=DISCOVERY,idempotency_key='once')
            self.assertEqual(conflict['kind'],'idempotency_conflict')
            (p/'result.json').write_text(json.dumps({'ok':True,'result':1}))
            self.assertEqual(bridge.wait_job(r['job_id'],0)['state'],'completed')
            self.assertTrue((p/'script.py').exists())
    def test_submission_uncertainty_retains_job(self):
        with tempfile.TemporaryDirectory() as t,patch.object(bridge,'JOBS',Path(t)),patch.object(bridge,'_run_cli',side_effect=subprocess.TimeoutExpired('rhinocode',10)):
            r=bridge.execute('result=1',timeout=0,_discovery=DISCOVERY)
            self.assertTrue(r['submission']['uncertain']);self.assertTrue((Path(t)/r['job_id']/'script.py').exists())
    def test_job_path_traversal(self):
        with self.assertRaises(ValueError):bridge.job_status('../foo')
    def test_harness_python39(self):
        ast.parse(bridge._make_harness('result=1',Path('/tmp/result.json'),'abc','test','123:4'),feature_version=(3,9))
    def test_runtime_python39(self):
        ast.parse((Path(bridge.__file__).parent/'runtime_ops.py').read_text(),feature_version=(3,9))
    def test_process_spawn_rejected(self):
        for code in ['import subprocess','from multiprocessing import Process','import os;os.system("hi")']:
            with self.assertRaises(ValueError):check_code(code)
    def test_new_python_syntax_rejected(self):
        with self.assertRaises(SyntaxError):check_code('match x:\n case 1: pass')
    def test_schema_compatibility(self):
        import server
        ts=asyncio.run(server.mcp.list_tools());schemas={t.name:t.inputSchema for t in ts}
        self.assertIn('document_id',schemas['rhino_run']['properties'])
        self.assertIn('idempotency_key',schemas['rhino_run']['properties'])
        for name in ['rhino_transaction','rhino_apply_material','rhino_list_documents','rhino_job_status','rhino_validate_assembly']:
            self.assertIn(name,schemas)
        self.assertIn('guid',schemas['rhino_validate']['properties'])
if __name__=='__main__':unittest.main()
