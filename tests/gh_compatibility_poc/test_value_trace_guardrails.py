import json,unittest
from pathlib import Path
from assert_value_trace import check_trace
class TraceGuardrails(unittest.TestCase):
    def setUp(self):self.r=json.loads((Path(__file__).parent/'value_trace_1790030057004713000.json').read_text())
    def stage(self,case,label):
        row=next(r for r in self.r['runs'] if r['case']==case and r['mode']=='staged')
        return next(s['state'] for s in row['stages'] if s['label']==label)
    def test_baseline(self):self.assertTrue(check_trace(self.r)['passed'])
    def test_conversion_error_not_moved_to_computation(self):
        self.stage('addition_to_brep_edges','receiver_collect')['receiver']['inputs'][0]['errors']=[]
        self.assertFalse(check_trace(self.r)['passed'])
    def test_collection_not_mistaken_for_operation_failure(self):
        self.stage('circle_to_loft_insufficient','receiver_collect')['receiver']['errors']=['Loft could not be constructed.']
        self.assertFalse(check_trace(self.r)['passed'])
    def test_wrong_geometry_not_validated_by_type_alone(self):
        p=self.stage('circle_to_loft_success','receiver_compute')['receiver']['outputs'][0]
        p['tree'][0]['items'][0]['measurements']['area']=1
        self.assertFalse(check_trace(self.r)['passed'])
    def test_staged_normal_difference_detected(self):
        self.stage('circle_to_brep_edges','receiver_compute')['receiver']['warnings']=['Injected mismatch']
        self.assertFalse(check_trace(self.r)['passed'])
if __name__=='__main__':unittest.main()
