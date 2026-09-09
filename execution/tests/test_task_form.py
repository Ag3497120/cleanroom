import copy,tempfile,unittest
from pathlib import Path
from precedent.task_form import assemble
from precedent.execution import git
from precedent.engine import Engine

class TaskDraft(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.repo=Path(self.tmp.name).resolve()/'repo';self.repo.mkdir()
  (self.repo/'x.py').write_text('def f(x):return x\n');(self.repo/'test_x.py').write_text('import unittest\nclass Test(unittest.TestCase):\n def test_one(self):self.assertTrue(True)\n')
  git(self.repo,'init');git(self.repo,'add','.');git(self.repo,'-c','user.name=Test','-c','user.email=test@example.test','commit','-m','base')
  self.values={'folder':str(self.repo),'name':'one','requirement':'identity','editable':'x.py','tests':'test_x.py','options':'direct\nother','depends':'','event':'要望の解釈が複数ある','model':'qwen2.5:3b','facts':[('count','整数','2')],'evidence':'spec'}
 def tearDown(self):self.tmp.cleanup()
 def test_ready_manifest_retains_choices_and_does_not_execute(self):
  manifest=assemble({},**self.values);e=Engine(Path(self.tmp.name)/'state')
  try:
   run=e.create(manifest);state=e.store.run(run);self.assertEqual(state['usage']['local_calls'],0);self.assertEqual(state['usage']['cloud_calls'],0);self.assertEqual(state['tasks'][0]['options'],['direct','other']);self.assertEqual(state['tasks'][0]['facts'],{'count':2});self.assertEqual(state['status'],{'one':'pending'})
  finally:e.close()
 def test_append_preserves_limits_bindings_and_input(self):
  original=assemble({},**self.values);original.update(limits={'cloud_calls':4},bindings={'reviewer':'codex-cli'});before=copy.deepcopy(original)
  values={**self.values,'name':'two','depends':'one'};result=assemble(original,**values)
  self.assertEqual(original,before);self.assertEqual(result['limits'],before['limits']);self.assertEqual(result['bindings'],before['bindings']);self.assertEqual(result['tasks'][1]['depends_on'],['one'])
  with self.assertRaises(ValueError):assemble(original,**{**values,'model':'different'})
 def test_invalid_paths_tests_and_dependencies(self):
  for fields in [{'editable':'../outside.py'},{'editable':'test_x.py'},{'tests':'missing.py'},{'depends':'unknown'},{'requirement':''},{'name':'../bad'},{'options':'one\ntwo\nthree'}]:
   with self.assertRaises(ValueError):assemble({},**{**self.values,**fields})
 def test_existing_task_files_cannot_become_new_frozen_tests(self):
  original=assemble({},**self.values)
  with self.assertRaises(ValueError):assemble(original,**{**self.values,'name':'two','editable':'y.py','tests':'x.py'})
