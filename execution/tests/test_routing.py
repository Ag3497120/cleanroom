import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from precedent.engine import Engine
from precedent.routing import configure,choose

ENTRIES=[{'id':x,'automatic_inference':True} for x in ['claude-cli','codex-cli','ollama','pi']]
class Routing(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.e=Engine(Path(self.tmp.name)/'state')
  self.e.store.run('r',{'local_model':'model','limits':{'local_calls':10,'cloud_calls':10},'usage':{'local_calls':0,'cloud_calls':0,'tokens_observed':0,'model_seconds':0},'deadline':time.time()+1000,'bindings':{}})
  self.config={'reviewer':{'allowed':['claude-cli','codex-cli'],'min_valid_responses':2,'max_switches':1}}
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def observe(self,provider,outcome):self.e.emit('r','transport_observation',{'provider':provider,'role':'reviewer','requested_model':'configured-default','outcome':outcome})
 def enable(self):
  with patch('precedent.adapters.require_inference'):return configure(self.e,'r',self.config)
 def choice(self):
  with patch('precedent.adapters.discover',return_value=ENTRIES):return choose(self.e,'r','reviewer','claude-cli')
 def history(self):
  self.observe('codex-cli','valid_response');self.observe('codex-cli','valid_response');self.observe('claude-cli','contract_error')
 def test_opt_in_and_failure_required(self):
  self.history();self.assertEqual(self.choice(),'claude-cli');self.enable()
  self.observe('claude-cli','valid_response');self.assertEqual(self.choice(),'claude-cli')
 def test_next_call_switches_once_without_retry_or_budget_reset(self):
  self.history();self.enable();before=self.e.store.run('r')
  with patch('precedent.adapters.discover',return_value=ENTRIES),patch('precedent.adapters.require_inference'),patch('precedent.engine.invoke',return_value=('{"verdict":"PASS","findings":[]}',{'tokens':3,'elapsed_seconds':.1})) as invoke:
   self.e.model('r','claude-cli','review',owner='candidate:x')
  self.assertEqual(invoke.call_count,1);self.assertEqual(invoke.call_args.args[0]['provider'],'codex-cli')
  after=self.e.store.run('r');self.assertEqual(after['usage']['cloud_calls'],1);self.assertEqual(after['deadline'],before['deadline']);self.assertEqual(after['limits'],before['limits']);self.assertEqual(len(after['routing_switches']),1)
  self.assertEqual(self.choice(),'claude-cli') # exhausted switch cap; caller-supplied current retained
 def test_explicit_dispatch_does_not_get_rerouted(self):
  self.history();self.enable()
  with patch('precedent.adapters.require_inference'),patch('precedent.engine.invoke',side_effect=RuntimeError('offline')) as invoke:
   with self.assertRaises(RuntimeError):self.e.model('r','claude-cli','review',adapter='claude-cli')
  self.assertEqual(invoke.call_count,1);self.assertEqual(self.e.store.run('r')['bindings'],{});self.assertEqual(self.e.store.run('r')['usage']['cloud_calls'],1)
 def test_reconfiguration_does_not_reset_switch_history(self):
  self.history();self.enable();self.assertEqual(self.choice(),'codex-cli')
  with patch('precedent.adapters.require_inference'):configure(self.e,'r',{})
  self.assertEqual(len(self.e.store.run('r')['routing_switches']),1)
 def test_policy_cannot_cross_budgets_or_add_desktop(self):
  self.config['reviewer']['allowed']=['claude-cli','ollama']
  with self.assertRaisesRegex(ValueError,'cross'):self.enable()
  self.config['reviewer']['allowed']=['claude-cli','codex-cli'];self.config['reviewer']['max_switches']=True
  with self.assertRaises(ValueError):self.enable()
  self.config['reviewer']['max_switches']=1;self.config['reviewer']['allowed']=['claude-cli','claude-desktop']
  with patch('precedent.adapters.require_inference',side_effect=RuntimeError('desktop unavailable')):
   with self.assertRaises(RuntimeError):configure(self.e,'r',self.config)
 def test_no_switch_after_deadline_or_exhaustion(self):
  self.history();self.enable();state=self.e.store.run('r');state['deadline']=1;self.e.store.run('r',state)
  with patch('precedent.engine.invoke') as invoke:
   with self.assertRaises(RuntimeError):self.e.model('r','claude-cli','review')
  invoke.assert_not_called();self.assertEqual(self.e.store.run('r')['bindings'],{})
