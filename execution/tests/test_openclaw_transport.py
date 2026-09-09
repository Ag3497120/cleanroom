import json,unittest
from precedent.openclaw_transport import parse_response,profile

def envelope():return {'payloads':[{'text':'{"ok":true}'}],'meta':{'aborted':False,'stopReason':'stop','agentMeta':{'provider':'ollama','model':'m','usage':{'total':19}},'executionTrace':{'fallbackUsed':False,'attempts':[{'result':'success'}]},'systemPromptReport':{'tools':{'entries':[]},'skills':{'entries':[]}},'finalAssistantVisibleText':'{"ok":true}'}}
class OpenClawProtocol(unittest.TestCase):
 def test_complete_response(self):self.assertEqual(parse_response(json.dumps(envelope()),'m'),('{"ok":true}',19,'m'))
 def test_abort_length_and_model_switch_rejected(self):
  for mutate in [lambda m:m.update(aborted=True),lambda m:m.update(stopReason='length'),lambda m:m['agentMeta'].update(model='other'),lambda m:m['executionTrace'].update(fallbackUsed=True)]:
   body=envelope();mutate(body['meta'])
   with self.assertRaises(RuntimeError):parse_response(json.dumps(body),'m')
 def test_added_tools_skills_or_attempts_rejected(self):
  for key in ['tools','skills']:
   body=envelope();body['meta']['systemPromptReport'][key]['entries']=['unexpected']
   with self.assertRaises(RuntimeError):parse_response(json.dumps(body),'m')
  body=envelope();body['meta']['executionTrace']['attempts'].append({'result':'success'})
  with self.assertRaises(RuntimeError):parse_response(json.dumps(body),'m')
 def test_missing_and_mismatched_payloads_rejected(self):
  for payload in [[],[{'text':''}],[{'text':'different'}],[{'text':'{"ok":true}','mediaUrl':'https://example.test'}]]:
   body=envelope();body['payloads']=payload
   with self.assertRaises(RuntimeError):parse_response(json.dumps(body),'m')
 def test_profile_has_no_delivery_or_tools(self):
  p=profile('m','/tmp/own-workspace');self.assertEqual(p['tools']['deny'],['*']);self.assertNotIn('channels',p);self.assertEqual(p['agents']['defaults']['model']['fallbacks'],[]);self.assertEqual(p['skills']['allowBundled'],['precedent-no-bundled-skills'])
 def test_local_budget_preserved(self):
  import tempfile
  from unittest.mock import patch
  from precedent.engine import Engine
  with tempfile.TemporaryDirectory() as home:
   e=Engine(home)
   try:
    state={'bindings':{'builder':'openclaw'},'usage':{'local_calls':1,'cloud_calls':2,'tokens_observed':0,'model_seconds':0},'limits':{'local_calls':3,'cloud_calls':3},'deadline':9999999999,'local_model':'m','decisions':{'x':'DEFER'}};e.store.run('r',state)
    with patch('precedent.adapters.require_inference'),patch('precedent.engine.invoke',return_value=('{"files":{"x.py":"pass"}}',{'tokens':19,'elapsed_seconds':.1})) as model:e.model('r','ollama','test')
    self.assertEqual(model.call_args.args[0],{'provider':'openclaw','model':'m'});self.assertEqual(e.store.run('r')['usage']['local_calls'],2);self.assertEqual(e.store.run('r')['usage']['cloud_calls'],2);self.assertEqual(e.store.run('r')['decisions'],state['decisions'])
   finally:e.close()
