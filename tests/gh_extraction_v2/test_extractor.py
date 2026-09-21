import ast,importlib.util,unittest
from pathlib import Path
SCRIPT=Path('/Users/nes/Downloads/gh_extract_v2.py')
spec=importlib.util.spec_from_file_location('extractor_under_test',SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ExtractorTests(unittest.TestCase):
    def test_py39(self):ast.parse(SCRIPT.read_text(),feature_version=(3,9))
    def test_no_process_or_interactive_calls(self):
        tree=ast.parse(SCRIPT.read_text())
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=[a.name for a in node.names];self.assertNotIn('subprocess',names)
            if isinstance(node,ast.Call):
                func=node.func
                self.assertFalse(isinstance(func,ast.Attribute) and func.attr in ['system','RunScript','Command','Popen'])
    def test_empty_is_untested(self):self.assertEqual(m.summarize_samples([])['status'],'untested')
    def test_exception_not_incompatible(self):self.assertEqual(m.summarize_samples([{'status':'error'}])['status'],'error')
    def test_mixed_values_conditional(self):
        r=m.summarize_samples([{'cast_from_ok':True},{'cast_from_ok':False}]);self.assertEqual(r['status'],'conditional_observed');self.assertIsNone(r['universal_compatibility'])
    def test_partial_error_kept(self):
        r=m.summarize_samples([{'cast_from_ok':True},{'status':'error'}]);self.assertEqual(r['error_samples'],1);self.assertFalse(r['coverage_complete'])
    def test_observed_rejection_is_not_universal(self):
        r=m.summarize_samples([{'cast_from_ok':False}]);self.assertEqual(r['status'],'observed_rejection');self.assertIsNone(r['universal_compatibility'])
if __name__=='__main__':unittest.main()
