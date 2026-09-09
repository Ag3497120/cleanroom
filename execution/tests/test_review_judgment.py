import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from precedent.engine import Engine

class ReviewJudgment(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.e=Engine(Path(self.tmp.name));self.task={'id':'task','requirement':'identity','editable':['x.py']};self.item={'id':'candidate','task':'task','option':'identity','files':{'x.py':'def f(x):return x'},'patch':'diff','public':{'passed':True},'holdout':{'passed':True},'cloud':None}
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def setup_rule(self,action,when,status='ACTIVE'):
  rule={'id':'failure','scope':{'repository':'/repo','event':'FAILED_VERIFICATION'},'when':when,'action':action,'evidence_required':[],'exceptions':[],'expires':None,'examples':['failure'],'counterexamples':['success'],'status':status,'version':1}
  self.e.store.run('r',{'repository':'/repo','rule_snapshot':[rule],'status':{'task':'running','other':'pending'},'decisions':{'task':{'action':'STAGE'}},'usage':{'cloud_calls':3}})
 def test_failed_review_applies_stop_without_discarding_verdict(self):
  self.setup_rule('STOP',{'review_failed':True})
  with patch.object(self.e,'model',return_value={'verdict':'FAIL','findings':['wrong result']}):self.e._review('r',self.task,self.item,{})
  state=self.e.store.run('r');self.assertTrue(state['stopped']);self.assertEqual(state['status']['task'],'stop');self.assertEqual(self.item['cloud']['verdict'],'FAIL');self.assertEqual(state['usage']['cloud_calls'],3)
 def test_unknown_and_transport_error_can_hold_without_becoming_fail(self):
  for kind in ('unknown','error'):
   self.setup_rule('DEFER',{'review_unknown' if kind=='unknown' else 'review_error':True})
   self.item['cloud']=None
   with patch.object(self.e,'model',side_effect=RuntimeError('offline') if kind=='error' else None,return_value={'verdict':'UNKNOWN','findings':[]}):self.e._review('r',self.task,self.item,{})
   self.assertEqual(self.e.store.run('r')['status']['task'],'defer');self.assertEqual(self.item['cloud'],None if kind=='error' else {'verdict':'UNKNOWN','findings':[]})
 def test_shadow_does_not_stop_review_and_pass_stays_verified(self):
  self.setup_rule('STOP',{'review_failed':True},status='SHADOW')
  with patch.object(self.e,'model',return_value={'verdict':'FAIL','findings':[]}):self.e._review('r',self.task,self.item,{})
  self.assertEqual(self.e.store.run('r')['status']['task'],'running')
  with patch.object(self.e,'model',return_value={'verdict':'PASS','findings':[]}):self.e._review('r',self.task,self.item,{})
  self.assertEqual(self.item['state'],'verified');self.assertNotIn('failure_decision',self.item)
