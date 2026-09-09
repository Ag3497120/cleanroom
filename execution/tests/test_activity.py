import tempfile,unittest
from pathlib import Path
from precedent.store import Store
from precedent.activity import report,describe

class Activity(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name))
  self.store.run('r',{'status':{'held':'deferred','done':'ready'},'decisions':{'held':{'reason':'dependency needs selection'}},'usage':{'local_calls':2,'cloud_calls':3}})
 def tearDown(self):self.store.close();self.tmp.cleanup()
 def test_distinguishes_operations_automation_and_unknown_human_time(self):
  for kind,body in [('adapter_replaced',{'role':'reviewer'}),('adapter_auto_replaced',{}),('handoff_response_received',{'origin':'inference_transport_return'}),('handoff_response_received',{'origin':'operator_supplied_unverified'}),('transport_observation',{'outcome':'contract_error','provider':'ollama'}),('transport_observation',{'outcome':'valid_response'}),('operator_selected',{'candidate':'c'})]:self.store.event(kind,{'run':'r',**body})
  self.store.event('adapter_replaced',{'run':'other'});self.store.event('profile_activated',{'model':'m'})
  before=self.store.db.total_changes;body=report(self.store,'r')
  self.assertEqual(body['recorded_control_operations'],3);self.assertEqual(len(body['automatic_switches']),1);self.assertEqual(len(body['transport_failures']),1)
  self.assertIsNone(body['human_interventions']);self.assertIsNone(body['human_monitoring_seconds']);self.assertIsNone(body['savings_percent']);self.assertEqual(before,self.store.db.total_changes)
  self.assertEqual(body['current_task_attention'][0]['reason'],'dependency needs selection');self.assertIn('人間の介入回数とは異なります',describe(body))
  first=body['control_operations'][0];self.assertEqual(first['ledger_hash'],self.store.db.execute('SELECT hash FROM ledger WHERE seq=?',(first['seq'],)).fetchone()[0])
 def test_empty_history_not_claimed_as_no_human_work(self):
  body=report(self.store,'r');self.assertEqual(body['recorded_control_operations'],0);self.assertIn('人間の介入がゼロだったことを意味しません',describe(body))
  with self.assertRaises(ValueError):report(self.store,'missing')
 def test_current_candidate_state_and_repeated_records_preserved(self):
  for _ in range(2):self.store.event('review_resumed',{'run':'r','candidate':'c','state':'review_required'})
  self.store.candidate('c','r',{'id':'c','task':'held','state':'review_required','review_error':'bad format'})
  self.store.candidate('v','r',{'id':'v','task':'done','state':'verified'})
  body=report(self.store,'r');self.assertEqual(body['recorded_control_operations'],2);self.assertEqual(len(body['current_candidate_attention']),1);self.assertIn('bad format',describe(body))
