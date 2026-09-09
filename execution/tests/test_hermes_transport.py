import unittest
from precedent.hermes_transport import profile,parse_response

def usage():return {'failed':False,'completed':True,'api_calls':1,'model':'m','provider':'custom','total_tokens':24}
class HermesProtocol(unittest.TestCase):
 def test_response_and_usage(self):self.assertEqual(parse_response('{}',usage(),'m'),('{}',24,'m'))
 def test_failure_extra_calls_and_changed_model(self):
  for key,value in [('failed',True),('completed',False),('api_calls',2),('model','other'),('provider','openrouter')]:
   u=usage();u[key]=value
   with self.assertRaises(RuntimeError):parse_response('{}',u,'m')
 def test_missing_usage_or_output(self):
  for text,u in [('',usage()),('{}',None),('{}',{})]:
   with self.assertRaises(RuntimeError):parse_response(text,u,'m')
 def test_no_tools_or_background_in_profile(self):
  p=profile('m');self.assertEqual(p['platform_toolsets']['cli'],[]);self.assertFalse(p['compression']['enabled']);self.assertFalse(p['memory']['memory_enabled']);self.assertEqual(p['plugins']['enabled'],[]);self.assertEqual(p['mcp_servers'],{});self.assertEqual(p['agent']['max_turns'],1)
