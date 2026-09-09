import tempfile,unittest
from pathlib import Path
from precedent.store import Store
from precedent.profiles import DEFAULT,suggest

class ProfileSuggestion(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name));self.store.run('r',{'local_model':'m','usage':{'local_calls':2}})
 def tearDown(self):self.store.close();self.tmp.cleanup()
 def record(self,**changes):self.store.event('model_call',{'run':'r','provider':'ollama','model':'m','profile_options':DEFAULT,'done_reason':'length','response_rejected':True,**changes})
 def test_two_recent_matching_failures_propose_without_applying(self):
  self.record();self.record();before=self.store.db.total_changes;body=suggest(self.store,'r');self.assertTrue(body['proposed']);self.assertEqual(body['options']['num_predict'],8192);self.assertEqual(before,self.store.db.total_changes);self.assertEqual(self.store.run('r')['usage']['local_calls'],2)
 def test_success_or_insufficient_matching_history_does_not_propose(self):
  self.record();self.assertFalse(suggest(self.store,'r')['proposed']);self.record(done_reason='stop',response_rejected=False);self.assertFalse(suggest(self.store,'r')['proposed'])
 def test_other_model_settings_runs_and_probes_are_excluded(self):
  for changes in ({'run':'other'},{'model':'other'},{'profile_options':dict(DEFAULT,num_predict=512)},{'owner':'profile:trial'}):self.record(**changes)
  self.assertEqual(suggest(self.store,'r')['evidence'],[])
 def test_maximum_output_is_not_increased(self):
  options=dict(DEFAULT,num_predict=8192);self.store.event('profile_activated',{'model':'m','options':options,'trial':None})
  self.record(profile_options=options);self.record(profile_options=options);self.assertFalse(suggest(self.store,'r')['proposed'])
