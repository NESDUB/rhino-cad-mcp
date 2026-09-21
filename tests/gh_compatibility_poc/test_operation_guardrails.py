import json,unittest
from pathlib import Path
from assert_operation_report import check_operation_report

class OperationGuardrails(unittest.TestCase):
    def setUp(self):self.report=json.loads((Path(__file__).parent/'operation_errors_1790029324894962000.json').read_text())
    def case(self,name):return next(r for r in self.report['cases'] if r['case']==name)['component']
    def test_baseline(self):self.assertTrue(check_operation_report(self.report)['passed'])
    def test_silent_invalidity_not_success(self):
        self.case('circle_zero')['outputs'][0]['valid_count']=1
        self.assertFalse(check_operation_report(self.report)['passed'])
    def test_partial_failure_does_not_erase_good_output(self):
        self.case('loft_mixed_branches')['outputs'][0]['valid_count']=0
        self.assertFalse(check_operation_report(self.report)['passed'])
    def test_same_name_cannot_hide_obsolete_variant(self):
        self.case('division_generic_by_zero')['obsolete']=True
        self.assertFalse(check_operation_report(self.report)['passed'])
    def test_stale_errors_after_repair_fail(self):
        self.report['repairs'][0]['after']['errors']=['Old error']
        self.assertFalse(check_operation_report(self.report)['passed'])
    def test_missing_native_detail_fails(self):
        self.case('boundary_invalid_curve')['inputs'][0]['tree'][0]['items'][0]['native_validation_log']=''
        self.assertFalse(check_operation_report(self.report)['passed'])

if __name__=='__main__':unittest.main()
