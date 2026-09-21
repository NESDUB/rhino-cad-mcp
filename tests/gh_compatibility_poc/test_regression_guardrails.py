"""Ensure the regression cannot accidentally certify empty/unsolved results."""
import copy,json,unittest
from pathlib import Path
from assert_report import check_report

class Guardrails(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((Path(__file__).parent/'run_1790028542124498000.json').read_text())
    def test_verified_baseline(self):
        self.assertTrue(check_report(self.data)['passed'])
    def test_unsolved_document_fails(self):
        self.data['cases'][0]['solver_state']='PreProcess'
        self.assertFalse(check_report(self.data)['passed'])
    def test_output_slot_without_valid_geometry_fails(self):
        self.data['cases'][0]['receiver']['outputs'][0]['valid_count']=0
        self.assertFalse(check_report(self.data)['passed'])
    def test_generic_error_is_not_conversion_evidence(self):
        row=next(c for c in self.data['cases'] if c['case']=='addition_to_brep_edges')
        row['receiver']['inputs'][0]['errors']=['Unrelated algorithm failure']
        self.assertFalse(check_report(self.data)['passed'])
    def test_user_document_change_fails(self):
        self.data['isolation']['same_canvas_document']=False
        self.assertFalse(check_report(self.data)['passed'])
    def test_truncation_is_not_recorded_rounding(self):
        row=next(c for c in self.data['parameter_cases'] if c['case']=='number_42.5_to_integer')
        row['receiver']['data'][0]['value']='42'
        self.assertFalse(check_report(self.data)['passed'])

if __name__=='__main__':unittest.main()
