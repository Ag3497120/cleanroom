import tempfile,unittest
from pathlib import Path
from precedent.harness_audit import assert_harness_logic,checked_harness
from precedent.store import sha

class HarnessLogic(unittest.TestCase):
 def test_assertion_boolean_misuse_is_contested(self):
  for source in ['self.assertIs(a,b) or self.assertEqual(a,b)','self.assertEqual(a,b) and self.assertEqual(c,d)']:
   with self.assertRaisesRegex(ValueError,'CONTESTED_TEST'):assert_harness_logic(source)
 def test_boolean_expression_inside_assertion_is_valid(self):
  assert_harness_logic('self.assertTrue(a == b or a == c)\nself.assertEqual(a,b)\nself.assertEqual(c,d)')
 def test_saved_bad_harness_cannot_be_reused(self):
  with tempfile.TemporaryDirectory() as temporary:
   folder=Path(temporary);source='self.assertIs(a,b) or self.assertEqual(a,b)';(folder/'task-frozen-tests.py').write_text(source)
   with self.assertRaisesRegex(ValueError,'CONTESTED_TEST'):checked_harness(folder,'task',sha(source))
