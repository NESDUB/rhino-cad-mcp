import json,unittest
from pathlib import Path
from assert_mixed_items import check_mixed
class MixedGuardrails(unittest.TestCase):
    def setUp(self):self.r=json.loads((Path(__file__).parent/'mixed_items_1790030245480306000.json').read_text())
    def case(self,kind,op):return next(r for r in self.r['runs'] if r['kind']==kind and r['operation']==op)['state']
    def test_baseline(self):self.assertTrue(check_mixed(self.r)['passed'])
    def test_removed_slot_detected(self):
        self.case('mixed','Loft')['relay']['tree'][0]['items'].pop(1)
        self.assertFalse(check_mixed(self.r)['passed'])
    def test_suppressed_conversion_error_detected(self):
        self.case('incompatible','Loft')['relay']['errors']=[]
        self.assertFalse(check_mixed(self.r)['passed'])
    def test_damaged_control_branch_detected(self):
        self.case('invalid','Loft')['receiver']['outputs'][0]['tree'][1]['items']=[]
        self.assertFalse(check_mixed(self.r)['passed'])
    def test_invalid_input_not_assumed_rejected(self):
        self.case('invalid','Divide Curve')['receiver']['outputs'][0]['tree'][1]['items']=[]
        self.assertFalse(check_mixed(self.r)['passed'])
if __name__=='__main__':unittest.main()
