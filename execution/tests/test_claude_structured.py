import json,unittest
from unittest.mock import patch
from types import SimpleNamespace
from precedent.models import claude_result,invoke
from precedent.transport_health import response_schema,contract

class ClaudeStructured(unittest.TestCase):
 def envelope(self):return {'type':'result','subtype':'success','is_error':False,'result':'','structured_output':{'verdict':'FAIL','findings':['bad code']},'num_turns':2,'usage':{'input_tokens':10,'output_tokens':5}}
 def test_reads_structured_output_not_empty_or_unrelated_text(self):
  value=self.envelope();value['result']='some prose';self.assertEqual(json.loads(claude_result(value,True))['verdict'],'FAIL')
 def test_incomplete_missing_or_invalid_never_falls_back(self):
  for update in [{'subtype':'error_max_turns'},{'is_error':True},{'structured_output':None},{'structured_output':[]},{'type':'assistant'}]:
   value={**self.envelope(),**update,'result':'{"verdict":"PASS","findings":[]}'}
   with self.assertRaises(RuntimeError):claude_result(value,True)
 def test_cli_schema_and_turn_usage(self):
  schema=response_schema('reviewer','candidate:x')
  with patch('precedent.models.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(self.envelope()),stderr='')) as process:
   raw,usage=invoke({'provider':'claude-cli','response_schema':schema},'review')
  argv=process.call_args.args[0];self.assertEqual(json.loads(argv[argv.index('--json-schema')+1]),schema);self.assertEqual(usage['cli_reported_turns'],2);self.assertEqual(usage['tokens'],15);contract(json.loads(raw),'reviewer',None)
 def test_role_schemas_separate_generation_and_audit(self):
  self.assertEqual(response_schema('builder',None)['required'],['files']);self.assertEqual(response_schema('test_designer','task:x')['required'],['tests']);self.assertEqual(response_schema('test_designer','harness:x')['required'],['verdict','findings'])
