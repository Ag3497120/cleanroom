import tempfile,unittest,sqlite3
from pathlib import Path
from precedent.policy import decide
from precedent.store import Store
from precedent.execution import apply_files,run_tests

def rule(action='FORK',status='ACTIVE'):
 return {'id':'test','scope':{'repository':'/repo','event':'NEW_DEPENDENCY'},'when':{'small':True},'action':action,'evidence_required':['diff'],'exceptions':[],'expires':None,'examples':['small dependency'],'counterexamples':['large dependency'],'status':status,'version':1}
class Policy(unittest.TestCase):
 def test_draft_never_executes(self):self.assertEqual(decide([rule(status='DRAFT')],'/repo','NEW_DEPENDENCY',{'small':True},{'diff':'hash'})['action'],'ESCALATE')
 def test_shadow_only_predicts(self):
  d=decide([rule(status='SHADOW')],'/repo','NEW_DEPENDENCY',{'small':True},{'diff':'hash'});self.assertEqual(d['action'],'ESCALATE');self.assertEqual(d['shadow'][0]['action'],'FORK')
 def test_scoped_evidence(self):self.assertEqual(decide([rule()],'/repo','NEW_DEPENDENCY',{'small':True},{'diff':'hash'})['action'],'FORK')
 def test_missing_evidence(self):self.assertEqual(decide([rule()],'/repo','NEW_DEPENDENCY',{'small':True},{})['action'],'DEFER')
 def test_unknown_not_false(self):self.assertEqual(decide([rule()],'/repo','NEW_DEPENDENCY',{}, {'diff':'x'})['action'],'DEFER')
 def test_conflict(self):self.assertEqual(decide([rule(),rule('APPLY')],'/repo','NEW_DEPENDENCY',{'small':True},{'diff':'x'})['action'],'ESCALATE')
 def test_authority(self):
  r=rule('APPLY');r['scope']['event']='IRREVERSIBLE_ACTION';self.assertEqual(decide([r],'/repo','IRREVERSIBLE_ACTION',{'small':True},{'diff':'x'})['action'],'ESCALATE')
 def test_expiry(self):
  r=rule();r['expires']='2000-01-01T00:00:00+00:00';self.assertEqual(decide([r],'/repo','NEW_DEPENDENCY',{'small':True},{'diff':'x'})['action'],'ESCALATE')
 def test_unknown_shadow_does_not_block_confirmed_active_rule(self):
  for changes in ({'when':{'unknown':True}},{'evidence_required':['absent']},{'exceptions':[{'unknown':True}]}):
   shadow=rule('STOP','SHADOW');shadow.update(id='shadow',**changes)
   d=decide([rule('APPLY'),shadow],'/repo','NEW_DEPENDENCY',{'small':True},{'diff':'hash'})
   self.assertEqual(d['action'],'APPLY');self.assertEqual(d['shadow'][0]['action'],'DEFER');self.assertEqual(d['shadow'][0]['proposed_action'],'STOP')
 def test_unknown_shadow_alone_does_not_become_applicable_rule(self):
  shadow=rule(status='SHADOW');shadow['when']={'missing':True}
  d=decide([shadow],'/repo','NEW_DEPENDENCY',{},{});self.assertEqual(d['action'],'ESCALATE');self.assertEqual(d['rules'],[]);self.assertEqual(d['shadow'][0]['action'],'DEFER')
class Persistence(unittest.TestCase):
 def test_lifecycle_and_history(self):
  with tempfile.TemporaryDirectory() as home:
   s=Store(home);s.save_rule(rule())
   with self.assertRaises(ValueError):s.transition('test','ACTIVE')
   s.transition('test','CONFIRMED');s.transition('test','ACTIVE');self.assertEqual(s.rules()[0]['version'],3)
   with self.assertRaises(sqlite3.IntegrityError):s.db.execute('DELETE FROM ledger')
   s.close()
 def test_paths(self):
  with tempfile.TemporaryDirectory() as home:
   root=Path(home).resolve()
   with self.assertRaises(ValueError):apply_files(root,{'../escape':'bad'},['../escape'])
   with self.assertRaises(ValueError):apply_files(root,{'test.py':'pass'},['impl.py'])
   (root/'alias').symlink_to('/tmp')
   with self.assertRaises(ValueError):apply_files(root,{'alias/escape':'bad'},['alias/escape'])
 def test_real_harness(self):
  with tempfile.TemporaryDirectory() as home:
   root=Path(home).resolve();(root/'impl.py').write_text('def f(x):return 4\n');test=root/'test.py';test.write_text('import unittest\nfrom impl import f\nclass Test(unittest.TestCase):\n def test_input(self):self.assertEqual(f(9),9)\n')
   self.assertFalse(run_tests(root,[test])['passed'])
   (root/'impl.py').write_text('def f(x):return x\n');self.assertTrue(run_tests(root,[test])['passed'])
 def test_isolation(self):
  with tempfile.TemporaryDirectory() as home,tempfile.NamedTemporaryFile() as secret:
   root=Path(home).resolve();test=root/'test.py';test.write_text('import unittest,socket\nclass Test(unittest.TestCase):\n def test_read(self):\n  with self.assertRaises(PermissionError):open('+repr(secret.name)+').read()\n def test_network(self):\n  with self.assertRaises(PermissionError):socket.create_connection(("127.0.0.1",11434),1)\n')
   self.assertTrue(run_tests(root,[test])['passed'])
if __name__=='__main__':unittest.main()

class RuntimeFlow(unittest.TestCase):
 def test_defer_continues_independent_and_keeps_dependency_held(self):
  from unittest.mock import patch
  import subprocess
  from precedent.engine import Engine
  with tempfile.TemporaryDirectory() as root:
   repo=(Path(root)/'repo').resolve();repo.mkdir();(repo/'x.py').write_text('x=1\n');(repo/'test_x.py').write_text('import unittest\n')
   for args in [('init',),('add','.'),('-c','user.name=Test','-c','user.email=test@example.test','commit','-m','base')]:subprocess.run(['git','-C',str(repo),*args],capture_output=True,check=True)
   e=Engine(Path(root)/'state')
   try:
    for event,action in [('TEST_SPEC_CONFLICT','DEFER'),('PUBLIC_API_CHANGE','APPLY')]:
     r=rule(action);r['id']=event;r['scope']={'repository':str(repo),'event':event};r['when']={};r['evidence_required']=[];e.store.save_rule(r);e.store.transition(r['id'],'CONFIRMED');e.store.transition(r['id'],'ACTIVE')
    common={'editable':['x.py'],'tests':['test_x.py'],'requirement':'Example'}
    run=e.create({'repository':str(repo),'tasks':[{**common,'id':'held','event':'TEST_SPEC_CONFLICT'},{**common,'id':'free','event':'PUBLIC_API_CHANGE'},{**common,'id':'child','event':'PUBLIC_API_CHANGE','depends_on':['held']}]})
    with patch.object(e,'build_task',return_value=['verified-test-double']) as builder:
     result=e.execute(run);self.assertEqual(builder.call_count,1);self.assertEqual(builder.call_args.args[1]['id'],'free')
    self.assertEqual(result['status'],{'held':'defer','free':'ready','child':'deferred'})
   finally:e.close()
 def test_detector_observes_api_and_dependency_changes(self):
  from precedent.detector import detect
  events=detect({'a.py':'def f(x):return x\n'},{'a.py':'import nonexistent_external\ndef f(x,y):return x\n'})
  self.assertEqual({e['event'] for e in events},{'PUBLIC_API_CHANGE','NEW_DEPENDENCY'})

class Adapters(unittest.TestCase):
 def test_handoff_is_not_inference(self):
  from precedent.adapters import require_inference
  with self.assertRaises(RuntimeError):require_inference('claude-desktop')
 def test_binding_keeps_decisions_and_budget(self):
  from precedent.adapters import bind
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as home:
   s=Store(home)
   try:
    s.run('r',{'usage':{'cloud_calls':3},'base':'sha','decisions':{'x':'DEFER'}})
    with patch('precedent.adapters.require_inference',return_value={'id':'codex-cli'}):bind(s,'r','reviewer','codex-cli')
    result=s.run('r');self.assertEqual(result['usage'],{'cloud_calls':3});self.assertEqual(result['decisions'],{'x':'DEFER'});self.assertEqual(result['bindings']['reviewer'],'codex-cli')
   finally:s.close()
