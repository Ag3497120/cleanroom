import io,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from precedent.models import invoke,ollama_result,ModelResponseError
from precedent.engine import Engine

class OllamaCompletion(unittest.TestCase):
 def envelope(self,**changes):return {'response':'{"files":{"x.py":"pass"}}','done':True,'done_reason':'stop','model':'m','prompt_eval_count':9,'eval_count':4,**changes}
 def test_completed_response_and_unknown_usage(self):
  result,tokens,metadata,error=ollama_result(self.envelope());self.assertEqual(tokens,13);self.assertIsNone(error)
  for count in (None,True,-1,'4'):
   self.assertIsNone(ollama_result(self.envelope(eval_count=count))[1])
 def test_incomplete_valid_json_rejected_with_usage(self):
  for changes in ({'done_reason':'length'},{'done':False},{'done_reason':None},{'response':''},{'response':{}},{'error':'problem'}):
   with self.subTest(changes=changes),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(self.envelope(**changes)).encode())):
    with self.assertRaises(ModelResponseError) as caught:invoke({'provider':'ollama','model':'m'},'test')
    self.assertEqual(caught.exception.usage['tokens'],13)
 def test_response_size_bounded(self):
  with patch('urllib.request.urlopen',return_value=io.BytesIO(b' '*160001)):
   with self.assertRaisesRegex(RuntimeError,'size limit'):invoke({'provider':'ollama','model':'m'},'test')
 def test_engine_charges_rejected_response_once_without_retry(self):
  with tempfile.TemporaryDirectory() as temp:
   engine=Engine(Path(temp));engine.store.run('r',{'local_model':'m','usage':{'local_calls':0,'cloud_calls':0,'tokens_observed':0,'model_seconds':0},'limits':{'local_calls':3,'cloud_calls':3},'deadline':time.time()+60})
   with patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(self.envelope(done_reason='length')).encode())) as request,patch('precedent.adapters.require_inference'):
    with self.assertRaises(ModelResponseError):engine.model('r','ollama','test')
   self.assertEqual(request.call_count,1);usage=engine.store.run('r')['usage'];self.assertEqual(usage['local_calls'],1);self.assertEqual(usage['tokens_observed'],13)
   events=[(kind,json.loads(raw)) for kind,raw in engine.store.db.execute('SELECT kind,body FROM ledger')]
   calls=[body for kind,body in events if kind=='model_call'];self.assertEqual(len(calls),1);self.assertTrue(calls[0]['response_rejected'])
   observation=next(body for kind,body in events if kind=='transport_observation');self.assertEqual(observation['outcome'],'transport_error');self.assertEqual(observation['done_reason'],'length');engine.close()
