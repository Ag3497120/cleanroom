import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from precedent.engine import Engine
from precedent.execution import git

class SyntaxRepair(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name).resolve();self.repo=root/'repo';self.repo.mkdir();(self.repo/'x.py').write_text('def f(x):return 0\n');(self.repo/'test_x.py').write_text('import unittest\nfrom x import f\nclass Test(unittest.TestCase):\n def test_identity(self):self.assertEqual(f(9),9)\n')
  git(self.repo,'init');git(self.repo,'add','.');git(self.repo,'-c','user.name=Test','-c','user.email=test@example.test','commit','-m','base')
  self.e=Engine(root/'state');rule={'id':'demo','scope':{'repository':str(self.repo),'event':'AMBIGUOUS_REQUIREMENT'},'when':{},'action':'STAGE','evidence_required':[],'exceptions':[],'expires':None,'examples':['identity'],'counterexamples':['other'],'status':'DRAFT','version':1};self.e.store.save_rule(rule);self.e.store.transition('demo','CONFIRMED');self.e.store.transition('demo','ACTIVE')
  self.bad='def f(x):\\n return x\\n';self.prompts=[]
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def execute(self,local_calls=2,independent=False):
  manifest={'repository':str(self.repo),'limits':{'local_calls':local_calls},'tasks':[{'id':'identity','event':'AMBIGUOUS_REQUIREMENT','requirement':'Integer identity','editable':['x.py'],'tests':['test_x.py']}]}
  if independent:manifest['tasks'].append({**manifest['tasks'][0],'id':'independent'})
  run=self.e.create(manifest)
  answers=[{'tests':'import unittest\nfrom x import f\nclass Hidden(unittest.TestCase):\n def test_hidden(self):self.assertEqual(f(19),19)\n'},{'verdict':'PASS','findings':[]},{'files':{'x.py':self.bad}},{'files':{'x.py':'def f(x):\n return x\n'}},{'verdict':'PASS','findings':[]}]
  if independent:answers[3:3]=answers[:2]
  def invoke(binding,prompt):self.prompts.append(prompt);return json.dumps(answers.pop(0)),{'tokens':1,'elapsed_seconds':0}
  with patch('precedent.engine.invoke',side_effect=invoke):self.e.execute(run)
  return run
 def test_exact_bad_source_is_retained_and_repaired_in_new_candidate(self):
  run=self.execute();items=self.e.store.candidates(run);self.assertEqual(len(items),2)
  rejected=next(c for c in items if c['state']=='rejected');self.assertEqual(rejected['syntax_failure']['source'],self.bad);self.assertEqual(rejected['syntax_failure']['file'],'x.py');self.assertEqual((Path(rejected['worktree'])/'x.py').read_text(),'def f(x):return 0\n')
  self.assertEqual(next(c for c in items if c['state']=='verified')['repair_of'],rejected['id'])
  self.assertEqual(sum(c['state']=='verified' for c in items),1);self.assertIn('syntax_failure',self.prompts[3]);self.assertNotIn('test_hidden',self.prompts[3]);self.assertEqual(self.e.store.run(run)['usage']['local_calls'],2);self.assertEqual(git(self.repo,'status','--porcelain'),'')
 def test_repair_does_not_replenish_exhausted_local_budget(self):
  run=self.execute(local_calls=1);self.assertEqual(len(self.prompts),3);self.assertEqual(self.e.store.run(run)['usage']['local_calls'],1);self.assertFalse(any(c['state']=='verified' for c in self.e.store.candidates(run)))

 def test_oversized_repair_source_is_not_replayed_or_erased(self):
  from precedent.engine import repair_feedback
  item={'id':'candidate','syntax_failure':{'file':'x.py','line':1,'message':'bad source','source':'x'*1000},'files':{'y.py':'y'*1000}}
  before=json.loads(json.dumps(item));feedback=repair_feedback(item,100)
  self.assertIsNone(feedback['prior_files']);self.assertNotIn('source',feedback['syntax_failure']);self.assertIn('source_omitted',feedback);self.assertEqual(item,before);self.assertEqual(feedback['syntax_failure']['line'],1)
 def test_small_repair_source_is_replayed_exactly(self):
  from precedent.engine import repair_feedback
  item={'id':'candidate','syntax_failure':{'file':'x.py','source':self.bad}}
  feedback=repair_feedback(item,1000);self.assertEqual(feedback['syntax_failure']['source'],self.bad);self.assertNotIn('source_omitted',feedback)

 def test_explicit_failure_defer_prevents_syntax_retry(self):
  rule=self.e.store.rules()[0];rule.update(id='hold-failure',scope={'repository':str(self.repo),'event':'FAILED_VERIFICATION'},action='DEFER',when={'syntax_failed':True})
  self.e.store.save_rule(rule);self.e.store.transition(rule['id'],'CONFIRMED');self.e.store.transition(rule['id'],'ACTIVE')
  run=self.execute();self.assertEqual(len(self.prompts),3);self.assertEqual(self.e.store.run(run)['status']['identity'],'defer');self.assertEqual(len(self.e.store.candidates(run)),1)
 def test_explicit_failure_stop_stops_run(self):
  rule=self.e.store.rules()[0];rule.update(id='stop-failure',scope={'repository':str(self.repo),'event':'FAILED_VERIFICATION'},action='STOP',when={})
  self.e.store.save_rule(rule);self.e.store.transition(rule['id'],'CONFIRMED');self.e.store.transition(rule['id'],'ACTIVE')
  run=self.execute();state=self.e.store.run(run);self.assertTrue(state['stopped']);self.assertEqual(state['status']['identity'],'stop');self.assertEqual(len(self.prompts),3)

 def test_unknown_shadow_failure_rule_does_not_stop_default_repair(self):
  rule=self.e.store.rules()[0];rule.update(id='shadow-failure',scope={'repository':str(self.repo),'event':'FAILED_VERIFICATION'},action='STOP',when={'missing':True})
  self.e.store.save_rule(rule);self.e.store.transition(rule['id'],'SHADOW')
  run=self.execute();self.assertEqual(self.e.store.run(run)['status']['identity'],'ready');self.assertEqual(self.e.store.run(run)['usage']['local_calls'],2)
  failed=next(c for c in self.e.store.candidates(run) if c['state']=='rejected');self.assertEqual(failed['failure_decision']['rules'],[]);self.assertEqual(failed['failure_decision']['shadow'][0]['action'],'DEFER')

 def test_failure_defer_preserves_independent_progress(self):
  rule=self.e.store.rules()[0];rule.update(id='hold-failure',scope={'repository':str(self.repo),'event':'FAILED_VERIFICATION'},action='DEFER',when={'syntax_failed':True})
  self.e.store.save_rule(rule);self.e.store.transition(rule['id'],'CONFIRMED');self.e.store.transition(rule['id'],'ACTIVE')
  run=self.execute(independent=True);state=self.e.store.run(run)
  self.assertEqual(state['status'],{'identity':'defer','independent':'ready'});self.assertEqual(state['usage']['local_calls'],2);self.assertEqual(state['usage']['cloud_calls'],5)
  candidates=self.e.store.candidates(run);self.assertEqual(len(candidates),2);self.assertEqual(next(c for c in candidates if c['state']=='verified')['task'],'independent');self.assertEqual(git(self.repo,'status','--porcelain'),'')
 def test_failure_stop_keeps_independent_task_pending_without_calls(self):
  rule=self.e.store.rules()[0];rule.update(id='stop-failure',scope={'repository':str(self.repo),'event':'FAILED_VERIFICATION'},action='STOP',when={})
  self.e.store.save_rule(rule);self.e.store.transition(rule['id'],'CONFIRMED');self.e.store.transition(rule['id'],'ACTIVE')
  run=self.execute(independent=True);state=self.e.store.run(run)
  self.assertTrue(state['stopped']);self.assertEqual(state['status'],{'identity':'stop','independent':'pending'});self.assertEqual(len(self.prompts),3);self.assertEqual(len(self.e.store.candidates(run)),1)
  self.e.execute(run);self.assertEqual(self.e.store.run(run)['usage'],state['usage']);self.assertEqual(self.e.store.run(run)['status'],state['status'])
