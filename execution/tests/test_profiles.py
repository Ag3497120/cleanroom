import tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from precedent.engine import Engine
from precedent.profiles import DEFAULT,validate,evaluate,activate,reset,active

class Profiles(unittest.TestCase):
 def setUp(self):
  self.identity_patch=patch('precedent.profiles.model_fingerprint',return_value='a'*64);self.identity=self.identity_patch.start()
  self.tmp=tempfile.TemporaryDirectory();self.e=Engine(Path(self.tmp.name)/'state');self.e.store.run('r',{'local_model':'model','usage':{'local_calls':0,'cloud_calls':0,'tokens_observed':0,'model_seconds':0},'limits':{'local_calls':8,'cloud_calls':7},'deadline':time.time()+1000,'bindings':{}})
 def tearDown(self):self.e.close();self.tmp.cleanup();self.identity_patch.stop()
 def test_bounded_settings(self):
  for change in [{'num_ctx':999999},{'temperature':float('nan')},{'num_predict':True},{'shell':'bad'}]:
   with self.assertRaises(ValueError):validate({**DEFAULT,**change})
 def trial(self,bad=False):
  answers=[{'files':{'specimen.py':'def f(x): return '+expression+'\n'}} for expression in ['x','-x','x','0' if bad else '-x']]
  with patch.object(self.e,'check_main'),patch.object(self.e,'model',side_effect=answers):return evaluate(self.e,'r',{**DEFAULT,'num_ctx':12288})
 def test_trial_then_activate_and_reset(self):
  trial=self.trial();self.assertTrue(trial['eligible']);self.assertEqual(active(self.e.store,'model'),DEFAULT)
  activate(self.e,trial['id']);self.assertEqual(active(self.e.store,'model')['num_ctx'],12288)
  with self.assertRaisesRegex(ValueError,'changed'):activate(self.e,trial['id'])
  reset(self.e,'model');self.assertEqual(active(self.e.store,'model'),DEFAULT)
 def test_failed_candidate_never_activates(self):
  trial=self.trial(True);self.assertFalse(trial['eligible'])
  with self.assertRaises(ValueError):activate(self.e,trial['id'])
 def test_next_call_uses_active_settings_and_preserves_budget(self):
  trial=self.trial();activate(self.e,trial['id'])
  with patch('precedent.adapters.require_inference'),patch('precedent.engine.invoke',return_value=('{"files":{"x.py":"pass"}}',{'tokens':5,'elapsed_seconds':.1})) as invoke:self.e.model('r','ollama','generate')
  self.assertEqual(invoke.call_args.args[0]['options']['num_ctx'],12288);self.assertEqual(self.e.store.run('r')['usage']['local_calls'],1)
 def test_insufficient_budget_does_not_start_probes(self):
  state=self.e.store.run('r');state['usage']['local_calls']=5;self.e.store.run('r',state)
  with patch.object(self.e,'model') as model:
   with self.assertRaises(ValueError):evaluate(self.e,'r',DEFAULT)
  model.assert_not_called()

 def test_model_replacement_blocks_activation_and_active_use(self):
  trial=self.trial();self.identity.return_value='b'*64
  with self.assertRaisesRegex(ValueError,'model changed'):activate(self.e,trial['id'])
  self.identity.return_value='a'*64;activate(self.e,trial['id']);self.identity.return_value='b'*64
  with self.assertRaisesRegex(ValueError,'Model changed'):active(self.e.store,'model')
  reset(self.e,'model');self.assertEqual(active(self.e.store,'model'),DEFAULT)
 def test_model_change_during_trial_cannot_be_eligible(self):
  self.identity.side_effect=['a'*64]+['b'*64]*8
  trial=self.trial();self.assertFalse(trial['eligible'])
 def test_changed_model_does_not_spend_next_call(self):
  trial=self.trial();activate(self.e,trial['id']);self.identity.return_value='b'*64
  before=self.e.store.run('r')
  with patch('precedent.adapters.require_inference'),patch('precedent.engine.invoke') as invoke:
   with self.assertRaises(ValueError):self.e.model('r','ollama','generate')
  invoke.assert_not_called();self.assertEqual(self.e.store.run('r'),before)

class ModelIdentity(unittest.TestCase):
 def test_metadata_digest_and_latest_alias(self):
  import json
  from unittest.mock import MagicMock
  from precedent.profiles import model_fingerprint
  response=MagicMock();response.__enter__.return_value=response
  response.read.return_value=json.dumps({'models':[{'name':'model:latest','digest':'sha256:'+'A'*64}]}).encode()
  with patch('urllib.request.urlopen',return_value=response):self.assertEqual(model_fingerprint('model'),'a'*64)
 def test_missing_invalid_and_ambiguous_identity_are_rejected(self):
  import json
  from unittest.mock import MagicMock
  from precedent.profiles import model_fingerprint
  response=MagicMock();response.__enter__.return_value=response
  for entries in [[],[{'name':'model','digest':'bad'}],[{'name':'model','digest':'a'*64},{'name':'model:latest','digest':'b'*64}]]:
   response.read.return_value=json.dumps({'models':entries}).encode()
   with patch('urllib.request.urlopen',return_value=response):
    with self.assertRaises(ValueError):model_fingerprint('model')
