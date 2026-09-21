import unittest,json
from pathlib import Path
from assert_tree_matching import check_tree
class TreeGuardrails(unittest.TestCase):
    def setUp(self):self.r=json.loads((Path(__file__).parent/'tree_matching_1790030526715230000.json').read_text())
    def case(self,n):return next(r for r in self.r['runs'] if r['case']==n)
    def test_baseline(self):self.assertTrue(check_tree(self.r)['passed'])
    def test_generated_path_not_assumed_input_path(self):
        self.case('different_branch_counts')['component']['outputs'][0]['tree'][2]['path']='{12}'
        self.assertFalse(check_tree(self.r)['passed'])
    def test_shortest_list_truncation_not_accepted(self):
        self.case('unequal')['component']['outputs'][0]['tree'][0]['items'].pop()
        self.assertFalse(check_tree(self.r)['passed'])
    def test_source_order_is_significant(self):
        self.case('sources_AB')['settings'][0]['source_ids'].reverse()
        self.assertFalse(check_tree(self.r)['passed'])
    def test_grafting_cannot_be_assumed_harmless(self):
        self.case('loft_graft')['component']['level']='Blank'
        self.assertFalse(check_tree(self.r)['passed'])
    def test_ragged_padding_retained(self):
        self.case('flip_ragged')['component']['outputs'][0]['tree'][1]['items'].pop()
        self.assertFalse(check_tree(self.r)['passed'])
if __name__=='__main__':unittest.main()
