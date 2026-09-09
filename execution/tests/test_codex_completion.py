import json,unittest
from precedent.models import codex_result

class CodexCompletion(unittest.TestCase):
 def events(self):return [{'type':'thread.started','thread_id':'t'},{'type':'turn.started'},{'type':'item.completed','item':{'type':'agent_message','text':'{"ok":true}'}},{'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':4}}]
 def parse(self,events,result='{"ok":true}'):return codex_result('\n'.join(json.dumps(e) for e in events),result)
 def test_valid_completed_response_retains_usage(self):
  tokens,extra,error=self.parse(self.events());self.assertEqual(tokens,14);self.assertIsNone(error);self.assertEqual(extra['cli_reported_turns'],1)
 def test_missing_failed_duplicate_or_mismatched_completion_rejected(self):
  cases=[self.events()[:-1],self.events()+[{'type':'turn.failed'}],self.events()+[self.events()[-1]],self.events()[:2]+[{'type':'error'}]+self.events()[2:]]
  for events in cases:self.assertIsNotNone(self.parse(events)[2])
  self.assertIsNotNone(self.parse(self.events(),'different')[2])
  events=self.events();events[-1]['usage']['output_tokens']=None;self.assertIsNone(self.parse(events)[0])
 def test_unexpected_tool_and_unknown_event_rejected(self):
  for kind in ('command_execution','file_change','mcp_tool_call','web_search','unknown','error'):
   events=self.events();events.insert(2,{'type':'item.completed','item':{'type':kind}});self.assertIsNotNone(self.parse(events)[2])
  events=self.events();events.insert(2,{'type':'new_event'});self.assertIsNotNone(self.parse(events)[2])
 def test_malformed_and_oversized_output_rejected(self):
  for text in ('not json','[]',' '*1000001):
   with self.assertRaises((ValueError,RuntimeError)):codex_result(text,'x')
 def test_broker_rejects_failed_trace_even_with_answer_file(self):
  from unittest.mock import patch
  from types import SimpleNamespace
  from pathlib import Path
  from precedent.models import invoke,ModelResponseError
  def run(argv,**kwargs):
   self.assertIn('suppress_unstable_features_warning=true',argv)
   Path(argv[argv.index('-o')+1]).write_text('{"ok":true}')
   return SimpleNamespace(returncode=0,stderr='',stdout='\n'.join(json.dumps(e) for e in self.events()+[{'type':'turn.failed'}]))
  with patch('precedent.models.subprocess.run',side_effect=run):
   with self.assertRaises(ModelResponseError) as caught:invoke({'provider':'codex-cli'},'test')
  self.assertEqual(caught.exception.usage['tokens'],14)
