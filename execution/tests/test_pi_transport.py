import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from precedent.pi_transport import parse_events
from precedent.engine import Engine


def stream(message=None,extra=None):
 message=message or {'role':'assistant','content':[{'type':'text','text':'{"ok":true}'}],'stopReason':'stop','usage':{'totalTokens':12},'model':'test'}
 events=[{'type':'message_end','message':message},{'type':'agent_end'}]
 if extra:events.append(extra)
 return '\n'.join(json.dumps(e) for e in events)

class PiProtocol(unittest.TestCase):
 def test_final_only_and_usage(self):self.assertEqual(parse_events(stream()),('{"ok":true}',12,'test'))
 def test_partial_or_malformed_never_accepted(self):
  for raw in ['{}','not json',json.dumps({'type':'agent_end'}),'[]']:
   with self.assertRaises(RuntimeError):parse_events(raw)
 def test_tools_and_hidden_extra_calls_rejected(self):
  for event in ['tool_execution_start','compaction_start','auto_retry_start']:
   with self.assertRaises(RuntimeError):parse_events(stream(extra={'type':event}))
 def test_length_stop_never_accepted(self):
  with self.assertRaises(RuntimeError):parse_events(stream({'role':'assistant','content':[{'type':'text','text':'{}'}],'stopReason':'length'}))
 def test_pi_rebinding_charges_local_and_preserves_state(self):
  with tempfile.TemporaryDirectory() as root:
   engine=Engine(root)
   try:
    original={'base':'unchanged','decisions':{'held':{'action':'DEFER'}},'bindings':{'builder':'pi'},'usage':{'local_calls':2,'cloud_calls':3,'tokens_observed':10,'model_seconds':0},'limits':{'local_calls':4,'cloud_calls':5},'deadline':9999999999,'local_model':'qwen2.5:3b'}
    engine.store.run('r',original)
    with patch('precedent.adapters.require_inference'),patch('precedent.engine.invoke',return_value=('{"files":{"x.py":"pass"}}',{'tokens':7,'elapsed_seconds':.1})) as broker:engine.model('r','ollama','test',owner='candidate:x')
    self.assertEqual(broker.call_args.args[0],{'provider':'pi','model':'qwen2.5:3b'})
    state=engine.store.run('r');self.assertEqual(state['usage']['local_calls'],3);self.assertEqual(state['usage']['cloud_calls'],3);self.assertEqual(state['decisions'],original['decisions']);self.assertEqual(state['base'],original['base'])
   finally:engine.close()
 def test_failed_pi_call_is_charged(self):
  with tempfile.TemporaryDirectory() as root:
   engine=Engine(root)
   try:
    state={'bindings':{'builder':'pi'},'usage':{'local_calls':0,'cloud_calls':0},'limits':{'local_calls':1,'cloud_calls':1},'deadline':9999999999,'local_model':'x'};engine.store.run('r',state)
    with patch('precedent.adapters.require_inference'),patch('precedent.engine.invoke',side_effect=RuntimeError('offline')):
     with self.assertRaises(RuntimeError):engine.model('r','ollama','test')
    self.assertEqual(engine.store.run('r')['usage']['local_calls'],1)
   finally:engine.close()
