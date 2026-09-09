import json,unittest
from precedent.opencode_transport import parse_events,profile


def events():return [{'type':'step_start','sessionID':'s','part':{'messageID':'m'}},{'type':'text','sessionID':'s','part':{'messageID':'m','text':'{"ok":true}'}},{'type':'step_finish','sessionID':'s','part':{'messageID':'m','reason':'stop','tokens':{'total':14}}}]
def parse(items):return parse_events('\n'.join(json.dumps(i) for i in items))
class OpenCodeProtocol(unittest.TestCase):
 def test_success_and_usage(self):self.assertEqual(parse(events()),('{"ok":true}',14))
 def test_missing_text_rejected(self):
  e=events();e.pop(1)
  with self.assertRaises(RuntimeError):parse(e)
 def test_truncation_or_error_rejected(self):
  for reason in ['length','error','tool-calls']:
   e=events();e[-1]['part']['reason']=reason
   with self.assertRaises(RuntimeError):parse(e)
 def test_extra_step_tool_and_mixed_identity_rejected(self):
  variants=[events()+[events()[0]],events()+[{'type':'tool_use'}],events()]
  variants[-1][1]['part']['messageID']='other'
  for e in variants:
   with self.assertRaises(RuntimeError):parse(e)
 def test_malformed_and_incomplete_rejected(self):
  for raw in ['no json','[]','{}',json.dumps(events()[0])]:
   with self.assertRaises(RuntimeError):parse_events(raw)
 def test_local_only_profile(self):
  p=profile('model');self.assertEqual(p['enabled_providers'],['precedent-local']);self.assertEqual(p['permission'],{'*':'deny'});self.assertEqual(p['share'],'disabled');self.assertFalse(p['compaction']['auto'])
 def test_engine_counts_opencode_as_local(self):
  import tempfile
  from unittest.mock import patch
  from precedent.engine import Engine
  with tempfile.TemporaryDirectory() as home:
   e=Engine(home)
   try:
    state={'bindings':{'builder':'opencode'},'base':'saved','decisions':{'held':'DEFER'},'usage':{'local_calls':1,'cloud_calls':2,'tokens_observed':0,'model_seconds':0},'limits':{'local_calls':3,'cloud_calls':4},'deadline':9999999999,'local_model':'qwen2.5:3b'};e.store.run('r',state)
    with patch('precedent.adapters.require_inference'),patch('precedent.engine.invoke',return_value=('{"files":{"x.py":"pass"}}',{'tokens':15,'elapsed_seconds':.1})) as call:e.model('r','ollama','test')
    self.assertEqual(call.call_args.args[0],{'provider':'opencode','model':'qwen2.5:3b'})
    actual=e.store.run('r');self.assertEqual(actual['usage']['local_calls'],2);self.assertEqual(actual['usage']['cloud_calls'],2);self.assertEqual(actual['decisions'],state['decisions']);self.assertEqual(actual['base'],'saved')
   finally:e.close()
