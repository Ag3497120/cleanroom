import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from precedent.engine import Engine
from precedent.dependencies import bind
from precedent.execution import git

X='import unittest\nfrom x import f\nclass Test(unittest.TestCase):\n def test_value(self):self.assertEqual(f(9),9)\n'
Y='import unittest\nfrom y import g\nclass Test(unittest.TestCase):\n def test_value(self):self.assertEqual(g(9),10)\n'
class Dependencies(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.repo=self.root/'repo';self.repo.mkdir()
  for name,body in {'x.py':'def f(x):return 0\n','y.py':'from x import f\ndef g(x):return f(x)\n','test_x.py':X,'test_y.py':Y}.items():(self.repo/name).write_text(body)
  git(self.repo,'init');git(self.repo,'add','.');git(self.repo,'-c','user.name=Test','-c','user.email=test@example.test','commit','-m','base')
  self.e=Engine(self.root/'state')
  self.e.store.save_rule({'id':'rule','scope':{'repository':str(self.repo),'event':'AMBIGUOUS_REQUIREMENT'},'when':{},'action':'STAGE','evidence_required':[],'exceptions':[],'expires':None,'examples':['same contract'],'counterexamples':['new contract'],'status':'ACTIVE','version':1},'ACTIVE')
  self.tasks=[{'id':'a','event':'AMBIGUOUS_REQUIREMENT','editable':['x.py'],'tests':['test_x.py'],'requirement':'f returns its argument'},{'id':'b','depends_on':['a'],'event':'AMBIGUOUS_REQUIREMENT','editable':['y.py'],'tests':['test_y.py'],'requirement':'g returns its argument plus one'}]
  self.run=self.e.create({'repository':str(self.repo),'tasks':self.tasks})
  with patch.object(self.e,'model',side_effect=[{'tests':X},{'verdict':'PASS'},{'files':{'x.py':'def f(x):return x\n'}},{'verdict':'PASS','findings':[]}]):self.e.execute(self.run)
  self.parent=self.e.store.candidates(self.run)[0]
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def test_composed_run_patch_and_budget(self):
  before=self.e.store.run(self.run);self.assertEqual(before['status']['b'],'deferred')
  bind(self.e,self.run,'b',{'a':self.parent['id']})
  self.assertEqual(self.e.store.run(self.run)['usage'],before['usage'])
  with patch.object(self.e,'model',side_effect=[{'tests':Y},{'verdict':'PASS'},{'files':{'y.py':'from x import f\ndef g(x):return f(x)+1\n'}},{'verdict':'PASS','findings':[]}]) as model:self.e.execute(self.run)
  item=next(c for c in self.e.store.candidates(self.run) if c['task']=='b')
  self.assertEqual(item['state'],'verified');self.assertTrue(item['dependency_reports'][0]['passed'])
  self.assertIn('return x',model.call_args_list[2].args[2]);self.assertIn('x.py',item['files'])
  path=self.e.select(self.run,item['id']);git(self.repo,'apply','--check',str(path));self.assertEqual(git(self.repo,'status','--porcelain'),'')
  with self.assertRaisesRegex(ValueError,'frozen'):bind(self.e,self.run,'b',{'a':self.parent['id']})
 def test_selection_rejects_missing_wrong_and_tampered(self):
  for selection in [{},{'a':'missing'},{'z':self.parent['id']}]:
   with self.assertRaises(ValueError):bind(self.e,self.run,'b',selection)
  (Path(self.parent['worktree'])/'x.py').write_text('def f(x):return 2\n')
  with self.assertRaisesRegex(ValueError,'changed'):bind(self.e,self.run,'b',{'a':self.parent['id']})
  self.assertNotIn('b',self.e.store.run(self.run).get('dependency_bindings',{}))
 def test_regression_to_parent_prevents_review(self):
  state=self.e.store.run(self.run);state['tasks'][1]['editable'].append('x.py');self.e.store.run(self.run,state)
  bind(self.e,self.run,'b',{'a':self.parent['id']})
  with patch.object(self.e,'model',side_effect=[{'tests':Y},{'verdict':'PASS'},{'files':{'y.py':'from x import f\ndef g(x):return 10\n','x.py':'def f(x):return 0\n'}}]) as model:self.e.execute(self.run)
  item=next(c for c in self.e.store.candidates(self.run) if c['task']=='b')
  self.assertEqual(item['state'],'rejected');self.assertFalse(item['dependency_reports'][0]['passed']);self.assertEqual(model.call_count,3)
 def test_frozen_test_cannot_be_editable_in_other_task(self):
  self.tasks[1]['editable'].append('test_x.py')
  with self.assertRaisesRegex(ValueError,'frozen test'):self.e.create({'repository':str(self.repo),'tasks':self.tasks})

 def test_conflicting_inputs_do_not_persist_selection(self):
  from precedent.store import encode,sha
  state=self.e.store.run(self.run);state['tasks'].append({**self.tasks[0],'id':'other'});state['tasks'][1]['depends_on'].append('other');self.e.store.run(self.run,state)
  other={**self.parent,'id':'other-candidate','task':'other','files':{'x.py':'def f(x):return x+1\n'}};other['source_digest']=sha(encode(other['files']));self.e.store.candidate(other['id'],self.run,other)
  # Structural conflict is tested separately from actual worktree tamper checks above.
  with patch.object(self.e,'_check_candidate_files'):
   with self.assertRaisesRegex(ValueError,'Conflicting'):bind(self.e,self.run,'b',{'a':self.parent['id'],'other':other['id']})
  self.assertNotIn('b',self.e.store.run(self.run).get('dependency_bindings',{}))
 def test_changed_parent_after_binding_blocks_generation(self):
  bind(self.e,self.run,'b',{'a':self.parent['id']});(Path(self.parent['worktree'])/'x.py').write_text('def f(x):return 2\n')
  with patch.object(self.e,'model') as model:self.e.execute(self.run)
  model.assert_not_called();self.assertEqual(self.e.store.run(self.run)['status']['b'],'deferred')
 def dependent_capsule(self):
  from precedent.adapters import capsule
  bind(self.e,self.run,'b',{'a':self.parent['id']})
  return json.loads(Path(capsule(self.e.store,self.run,'ollama')['capsule']).read_text())
 def test_dependency_dispatch_preserves_context_and_replay(self):
  from precedent.adapters import dispatch
  body=self.dependent_capsule();context=body['contexts']['b']
  self.assertEqual(context['dependencies']['files']['x.py'],'def f(x):return x\n')
  self.assertNotIn('harness',json.dumps(context));self.assertNotIn('dependency_checks',json.dumps(context))
  with patch.object(self.e,'model',side_effect=[{'files':{'y.py':'from x import f\ndef g(x):return f(x)+1\n'}},{'tests':Y},{'verdict':'PASS'},{'verdict':'PASS','findings':[]}]) as model:
   result=dispatch(self.e,body['id'],'b');self.assertEqual(result['state'],'verified');self.assertEqual(model.call_count,4)
   self.assertEqual(dispatch(self.e,body['id'],'b'),result);self.assertEqual(model.call_count,4)
  item=self.e.store.candidate(result['verified'][0]);self.assertTrue(item['dependency_reports'][0]['passed']);self.assertEqual(item['origin'],'inference_transport_return')
  git(self.repo,'apply','--check',str(self.e.select(self.run,item['id'])))
 def test_changed_selection_rejected_before_dispatch(self):
  from precedent.adapters import dispatch
  body=self.dependent_capsule();other={**self.parent,'id':'second-parent'};self.e.store.candidate(other['id'],self.run,other)
  bind(self.e,self.run,'b',{'a':other['id']})
  with patch.object(self.e,'model') as model:
   with self.assertRaisesRegex(ValueError,'selection changed'):dispatch(self.e,body['id'],'b')
  model.assert_not_called()
 def test_import_revalidates_parent_before_consuming_response(self):
  from precedent.adapters import import_response
  body=self.dependent_capsule();path=self.root/'reply.json';path.write_text(json.dumps({'schema':'precedent-response/1','handoff':body['id'],'base':body['base'],'task':'b','option':'Implement the requirement','files':{'y.py':'from x import f\ndef g(x):return f(x)+1\n'}}))
  (Path(self.parent['worktree'])/'x.py').write_text('def f(x):return 2\n')
  with patch.object(self.e,'model') as model:
   with self.assertRaisesRegex(ValueError,'changed'):import_response(self.e,path)
  model.assert_not_called();self.assertIsNone(self.e.store.db.execute('SELECT response_digest FROM handoffs WHERE id=?',(body['id'],)).fetchone()[0])
 def test_unbound_dependency_is_excluded(self):
  from precedent.adapters import capsule
  body=json.loads(Path(capsule(self.e.store,self.run,'ollama')['capsule']).read_text())
  self.assertNotIn('b',body['contexts']);self.assertFalse(body['eligibility']['b']['eligible'])
