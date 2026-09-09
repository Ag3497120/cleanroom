import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from precedent.capabilities import check,require_compatible,model_context
from precedent.engine import Engine
from precedent.adapters import bind

class Capabilities(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.e=Engine(Path(self.tmp.name)/'state')
  self.e.store.run('r',{'repository':self.tmp.name,'base':'base','local_model':'small','bindings':{},'limits':{'local_calls':8,'cloud_calls':7},'usage':{'local_calls':0,'cloud_calls':0},'deadline':time.time()+1000})
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def test_declared_threshold_and_unknown(self):
  for length,status in [(32768,'incompatible'),(64000,'compatible'),(262144,'compatible')]:
   with patch('precedent.capabilities.model_context',return_value=length):self.assertEqual(check('hermes','m')['status'],status)
  with patch('precedent.capabilities.model_context',side_effect=ValueError('no metadata')):
   self.assertEqual(check('hermes','m')['status'],'unverified')
   with self.assertRaises(ValueError):require_compatible('hermes','m')
 def test_metadata_matches_architecture_and_rejects_bool(self):
  response=MagicMock();response.__enter__.return_value=response
  for value in [True,0,-1,'262144']:
   response.read.return_value=json.dumps({'model_info':{'general.architecture':'a','a.context_length':value,'b.context_length':999999}}).encode()
   with patch('urllib.request.urlopen',return_value=response):
    with self.assertRaises(ValueError):model_context('m')
 def test_model_preflight_does_not_charge_or_invoke(self):
  before=self.e.store.run('r')
  with patch('precedent.adapters.require_inference'),patch('precedent.capabilities.model_context',return_value=32768),patch('precedent.engine.invoke') as invoke:
   with self.assertRaises(ValueError):self.e.model('r','ollama','test',adapter='hermes')
  invoke.assert_not_called();self.assertEqual(self.e.store.run('r'),before)
 def test_binding_preserved_if_model_incompatible(self):
  before=self.e.store.run('r')
  with patch('precedent.adapters.require_inference'),patch('precedent.capabilities.model_context',return_value=32768):
   with self.assertRaises(ValueError):bind(self.e.store,'r','builder','hermes')
  self.assertEqual(self.e.store.run('r'),before)
 def test_builder_rejected_before_cloud_harness(self):
  state=self.e.store.run('r');state['bindings']={'builder':'hermes'};self.e.store.run('r',state)
  with patch('precedent.capabilities.model_context',return_value=32768),patch.object(self.e,'model') as model:
   with self.assertRaises(ValueError):self.e.build_task('r',{'id':'task'},'STAGE')
  model.assert_not_called()
 def test_other_adapters_do_not_probe_unneeded_metadata(self):
  with patch('precedent.capabilities.model_context') as metadata:require_compatible('ollama','small')
  metadata.assert_not_called()

 def test_unknown_adapter_is_not_reported_as_supported(self):
  with self.assertRaises(ValueError):check('invented','model')
