import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from precedent.engine import Engine
from precedent.transport_health import recommendations

class Health(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.e=Engine(Path(self.tmp.name)/'state')
  self.e.store.run('r',{'local_model':'test-model','limits':{'local_calls':10,'cloud_calls':10},'usage':{'local_calls':0,'cloud_calls':0,'tokens_observed':0,'model_seconds':0},'deadline':time.time()+1000,'bindings':{}})
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def call(self,raw,provider='claude-cli',error=None):
  with patch('precedent.adapters.require_inference'),patch('precedent.engine.invoke',side_effect=error,return_value=(raw,{'tokens':8,'elapsed_seconds':.1,'model':'observed'})):
   return self.e.model('r',provider,'test',owner='candidate:test')
 def rows(self):return [json.loads(r[0]) for r in self.e.store.db.execute("SELECT body FROM ledger WHERE kind='transport_observation'")]
 def test_verdict_fail_is_valid_transport_not_a_failure(self):
  self.assertEqual(self.call('{"verdict":"FAIL","findings":["wrong code"]}')['verdict'],'FAIL')
  self.assertEqual(self.rows()[0]['outcome'],'valid_response')
 def test_error_classes_and_failed_calls_still_charged(self):
  for raw,error,kind in [('x',RuntimeError('offline'),'transport_error'),('not json',None,'json_error'),('{"verdict":"PASS"}',None,'contract_error')]:
   with self.assertRaises((RuntimeError,ValueError)):self.call(raw,error=error)
   self.assertEqual(self.rows()[-1]['outcome'],kind)
  self.assertEqual(self.e.store.run('r')['usage']['cloud_calls'],3)
  self.assertEqual(self.e.store.run('r')['usage']['tokens_observed'],16)
 def test_recommendation_is_role_scoped_and_does_not_change_budget(self):
  self.call('{"verdict":"PASS","findings":[]}',provider='codex-cli')
  before=self.e.store.run('r')
  entries=[{'id':p,'automatic_inference':True} for p in ['claude-cli','codex-cli','ollama']]
  r=recommendations(self.e.store,'r','reviewer',entries)
  self.assertEqual(r['suggested'],'codex-cli');self.assertNotIn('ollama',[x['adapter'] for x in r['alternatives']]);self.assertEqual(self.e.store.run('r'),before)
  self.assertEqual(recommendations(self.e.store,'r','test_designer',entries)['suggested'],'claude-cli')
  self.assertEqual(recommendations(self.e.store,'r','reviewer',entries,now=time.time()+8*86400)['suggested'],'claude-cli')
 def test_no_unavailable_or_unobserved_replacement(self):
  with self.assertRaises(RuntimeError):self.call('',error=RuntimeError('offline'))
  entries=[{'id':p,'automatic_inference':True} for p in ['claude-cli','codex-cli']]
  self.assertEqual(recommendations(self.e.store,'r','reviewer',entries)['suggested'],'claude-cli')
  self.assertIsNone(recommendations(self.e.store,'r','reviewer',[])['suggested'])
 def test_recent_twenty_only_and_local_model_scoped(self):
  state=self.e.store.run('r');state['limits']['local_calls']=30;self.e.store.run('r',state)
  for i in range(22):self.call('{"files":{"x.py":"pass"}}',provider='ollama')
  entries=[{'id':'ollama','automatic_inference':True}]
  self.assertEqual(recommendations(self.e.store,'r','builder',entries)['alternatives'][0]['samples'],20)
  state=self.e.store.run('r');state['local_model']='different-model';self.e.store.run('r',state)
  self.assertEqual(recommendations(self.e.store,'r','builder',entries)['alternatives'][0]['samples'],0)
