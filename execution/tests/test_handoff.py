"""Real Git and test processes; model verdicts are explicit test doubles."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from precedent.engine import Engine
from precedent.execution import git
from precedent.adapters import capsule,import_response

TEST='import unittest\nfrom x import f\nclass Test(unittest.TestCase):\n def test_value(self):self.assertEqual(f(9),9)\n'
class Handoff(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.repo=self.root/'repo';self.repo.mkdir()
  (self.repo/'x.py').write_text('def f(x):return 0\n');(self.repo/'test_x.py').write_text(TEST)
  git(self.repo,'init');git(self.repo,'add','.');git(self.repo,'-c','user.name=Test','-c','user.email=test@example.test','commit','-m','base')
  self.e=Engine(self.root/'state')
  self.rule={'id':'identity','scope':{'repository':str(self.repo),'event':'AMBIGUOUS_REQUIREMENT'},'when':{},'action':'STAGE','evidence_required':[],'exceptions':[],'expires':None,'examples':['identity'],'counterexamples':['not identity'],'status':'ACTIVE','version':1}
  self.e.store.save_rule(self.rule,'ACTIVE')
  self.task={'id':'identity','event':'AMBIGUOUS_REQUIREMENT','editable':['x.py'],'tests':['test_x.py'],'requirement':'f(x) returns x.'}
  self.run=self.e.create({'repository':str(self.repo),'tasks':[self.task]})
  self.export=capsule(self.e.store,self.run,'claude-desktop');self.body=json.loads(Path(self.export['capsule']).read_text())
  self.response={'schema':'precedent-response/1','handoff':self.body['id'],'base':self.body['base'],'task':'identity','option':'Implement the requirement','files':{'x.py':'def f(x):return x\n'}}
  self.path=self.root/'response.json'
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def send(self):
  self.path.write_text(json.dumps(self.response));return import_response(self.e,self.path)
 def test_full_import_and_exact_replay(self):
  with patch.object(self.e,'model',side_effect=[{'tests':TEST},{'verdict':'PASS','findings':[]},{'verdict':'PASS','findings':[]}]) as model:
   result=self.send();self.assertEqual(result['state'],'verified');self.assertEqual(model.call_count,3)
   self.assertEqual(self.send(),result);self.assertEqual(model.call_count,3)
  self.assertEqual(git(self.repo,'status','--porcelain'),'')
  item=self.e.store.candidate(result['verified'][0]);self.assertTrue(item['public']['passed']);self.assertTrue(item['holdout']['passed'])
  self.assertEqual(item['handoff'],self.body['id'])
  self.response['files']['x.py']='def f(x):return 4\n'
  with self.assertRaisesRegex(ValueError,'consumed'):self.send()
 def test_rejects_wrong_base_and_scope_before_model(self):
  for field,value in [('base','wrong'),('task','other'),('option','invented'),('files',{'test_x.py':'pass'})]:
   old=self.response[field];self.response[field]=value
   with patch.object(self.e,'model') as model:
    with self.assertRaises(ValueError):self.send()
    model.assert_not_called()
   self.response[field]=old
 def test_held_rule_not_overridden(self):
  state=self.e.store.run(self.run);state['rule_snapshot'][0]['action']='DEFER';self.e.store.run(self.run,state)
  export=capsule(self.e.store,self.run,'claude-desktop');self.response['handoff']=json.loads(Path(export['capsule']).read_text())['id']
  with self.assertRaisesRegex(ValueError,'does not authorize'):self.send()
 def test_failed_tests_never_invoke_builder_or_reviewer(self):
  self.response['files']['x.py']='def f(x):return 3\n'
  with patch.object(self.e,'model',side_effect=[{'tests':TEST},{'verdict':'PASS','findings':[]}]) as model:
   result=self.send();self.assertEqual(result['verified'],[]);self.assertEqual(model.call_count,2)
  self.assertEqual(self.e.store.run(self.run)['status']['identity'],'deferred')
  self.assertEqual(self.e.store.candidate(result['candidates'][0])['state'],'rejected')
 def test_interrupted_receipt_does_not_repeat(self):
  from precedent.store import encode,sha
  self.e.store.db.execute('UPDATE handoffs SET response_digest=? WHERE id=?',(sha(encode(self.response)),self.body['id']));self.e.store.db.commit()
  self.assertEqual(self.send()['state'],'interrupted')
 def test_task_id_cannot_escape_artifact_folder(self):
  self.task['id']='../escape'
  with self.assertRaisesRegex(ValueError,'Invalid task'):self.e.create({'repository':str(self.repo),'tasks':[self.task]})
 def test_changed_main_is_preserved(self):
  (self.repo/'x.py').write_text('human edit\n')
  with self.assertRaisesRegex(RuntimeError,'HUMAN_EDIT_CONFLICT'):self.send()
  self.assertEqual((self.repo/'x.py').read_text(),'human edit\n')
 def test_export_has_exact_frozen_context_without_holdout(self):
  context=self.body['contexts']['identity']
  self.assertEqual(context['source'],{'x.py':'def f(x):return 0\n'})
  self.assertEqual(context['public_tests'],{'test_x.py':TEST})
  self.assertTrue(self.body['eligibility']['identity']['eligible'])
  self.assertNotIn('holdout',context)
 def test_held_execution_has_no_source_and_cannot_import(self):
  state=self.e.store.run(self.run);state['status']['identity']='deferred';self.e.store.run(self.run,state)
  export=capsule(self.e.store,self.run,'claude-desktop');body=json.loads(Path(export['capsule']).read_text())
  self.assertEqual(body['contexts'],{});self.assertFalse(body['eligibility']['identity']['eligible'])
  self.response['handoff']=body['id']
  with self.assertRaisesRegex(ValueError,'held'):self.send()
 def test_export_rejects_changed_main_and_over_budget(self):
  state=self.e.store.run(self.run);state['limits']['max_source_bytes']=1;self.e.store.run(self.run,state)
  with self.assertRaisesRegex(ValueError,'context budget'):capsule(self.e.store,self.run,'claude-desktop')
  (self.repo/'x.py').write_text('changed\n')
  with self.assertRaisesRegex(RuntimeError,'HUMAN_EDIT_CONFLICT'):capsule(self.e.store,self.run,'claude-desktop')
 def test_dispatch_round_trip_is_idempotent(self):
  from precedent.adapters import dispatch
  export=capsule(self.e.store,self.run,'pi');key=json.loads(Path(export['capsule']).read_text())['id']
  with patch('precedent.adapters.require_inference'),patch.object(self.e,'model',side_effect=[{'files':self.response['files']},{'tests':TEST},{'verdict':'PASS','findings':[]},{'verdict':'PASS','findings':[]}]) as model:
   result=dispatch(self.e,key,'identity');self.assertEqual(result['state'],'verified');self.assertEqual(model.call_count,4)
   self.assertEqual(model.call_args_list[0].kwargs['adapter'],'pi')
   self.assertEqual(dispatch(self.e,key,'identity'),result);self.assertEqual(model.call_count,4)
 def test_uncertain_delivery_never_regenerates(self):
  from precedent.adapters import dispatch
  export=capsule(self.e.store,self.run,'pi');key=json.loads(Path(export['capsule']).read_text())['id']
  with patch('precedent.adapters.require_inference'),patch.object(self.e,'model',side_effect=RuntimeError('Disconnected')) as model:
   self.assertEqual(dispatch(self.e,key,'identity')['state'],'interrupted')
   self.assertEqual(dispatch(self.e,key,'identity')['state'],'interrupted');self.assertEqual(model.call_count,1)
 def test_desktop_cannot_be_dispatched_as_cli(self):
  from precedent.adapters import dispatch
  with self.assertRaises(RuntimeError):dispatch(self.e,self.body['id'],'identity')
 def interrupted_candidate(self):
  with patch.object(self.e,'model',side_effect=[{'tests':TEST},{'verdict':'PASS','findings':[]},ValueError('Malformed JSON')]):result=self.send()
  item=self.e.store.candidate(result['candidates'][0]);self.assertEqual(item['state'],'review_required');return item
 def test_resume_review_keeps_source_and_does_not_build(self):
  item=self.interrupted_candidate()
  with patch.object(self.e,'model',return_value={'verdict':'PASS','findings':[]}) as model:
   result=self.e.resume_review(self.run,item['id']);self.assertEqual(result['state'],'verified');self.assertEqual(model.call_count,1)
   self.assertEqual(self.e.resume_review(self.run,item['id']),result);self.assertEqual(model.call_count,1)
  after=self.e.store.candidate(item['id']);self.assertEqual(after['source_digest'],item['source_digest']);self.assertEqual(len(self.e.store.candidates(self.run)),1)
 def test_resume_rejects_modified_candidate_and_extra_files(self):
  item=self.interrupted_candidate();tree=Path(item['worktree']);(tree/'extra.py').write_text('x=1\n')
  with patch.object(self.e,'model') as model:
   with self.assertRaisesRegex(ValueError,'gained'):self.e.resume_review(self.run,item['id'])
   model.assert_not_called()
  (tree/'extra.py').unlink();(tree/'x.py').write_text('def f(x):return 4\n')
  with self.assertRaisesRegex(ValueError,'changed'):self.e.resume_review(self.run,item['id'])
 def test_resume_rejects_changed_harness(self):
  item=self.interrupted_candidate();path=Path(item['harness_path']);path.chmod(0o600);path.write_text('changed')
  with self.assertRaisesRegex(ValueError,'harness'):self.e.resume_review(self.run,item['id'])
 def test_completed_negative_review_cannot_be_retried_to_pass(self):
  item=self.interrupted_candidate();item['cloud']={'verdict':'FAIL','findings':['wrong']};self.e.store.candidate(item['id'],self.run,item)
  with self.assertRaisesRegex(ValueError,'completed verdict'):self.e.resume_review(self.run,item['id'])
 def test_expired_review_does_not_reset_budget(self):
  item=self.interrupted_candidate();state=self.e.store.run(self.run);state['deadline']=1;self.e.store.run(self.run,state)
  with self.assertRaisesRegex(ValueError,'expired'):self.e.resume_review(self.run,item['id'])
  self.assertEqual(self.e.store.run(self.run)['usage'],state['usage'])
 def test_window_renewal_preserves_all_other_state(self):
  state=self.e.store.run(self.run);state['deadline']=1;state['usage']['local_calls']=2;state['usage']['cloud_calls']=3;self.e.store.run(self.run,state)
  result=self.e.renew_window(self.run,60,1);after=self.e.store.run(self.run)
  self.assertFalse(result['execution_started']);self.assertEqual(result['remaining_calls']['cloud_calls'],state['limits']['cloud_calls']-3)
  for key in state:
   if key!='deadline':self.assertEqual(after[key],state[key])
  with self.assertRaisesRegex(ValueError,'changed'):self.e.renew_window(self.run,60,1)
 def test_window_rejects_active_stopped_and_changed_main(self):
  state=self.e.store.run(self.run)
  with self.assertRaisesRegex(ValueError,'active'):self.e.renew_window(self.run,60,state['deadline'])
  state['deadline']=1;state['stopped']=True;self.e.store.run(self.run,state)
  with self.assertRaisesRegex(ValueError,'Stopped'):self.e.renew_window(self.run,60,1)
  state.pop('stopped');self.e.store.run(self.run,state);(self.repo/'x.py').write_text('human changed')
  with self.assertRaisesRegex(RuntimeError,'HUMAN_EDIT_CONFLICT'):self.e.renew_window(self.run,60,1)
 def test_window_does_not_replenish_exhausted_calls(self):
  state=self.e.store.run(self.run);state['deadline']=1
  for key in ['local_calls','cloud_calls']:state['usage'][key]=state['limits'][key]
  self.e.store.run(self.run,state)
  with self.assertRaisesRegex(ValueError,'No inference'):self.e.renew_window(self.run,60,1)
 def test_window_duration_is_bounded(self):
  state=self.e.store.run(self.run);state['deadline']=1;self.e.store.run(self.run,state)
  for seconds in [0,-1,True,state['limits']['seconds']+1]:
   with self.assertRaises(ValueError):self.e.renew_window(self.run,seconds,1)
 def test_reopen_runs_only_pending_tasks_and_preserves_verified_candidate(self):
  with patch.object(self.e,'model',side_effect=[{'tests':TEST},{'verdict':'PASS','findings':[]},{'verdict':'PASS','findings':[]}]):result=self.send()
  candidate=self.e.store.candidate(result['verified'][0]);state=self.e.store.run(self.run)
  state['tasks'].append({**self.task,'id':'later'});state['status']['later']='pending';self.e.store.run(self.run,state)
  self.e.close();self.e=Engine(self.root/'state')
  with patch.object(self.e,'build_task',return_value=['fixture-second-result']) as build:self.e.execute(self.run)
  self.assertEqual(build.call_count,1);self.assertEqual(build.call_args.args[1]['id'],'later');self.assertEqual(self.e.store.candidate(candidate['id']),candidate)
 def test_expired_resume_keeps_pending_state_and_usage(self):
  state=self.e.store.run(self.run);state['deadline']=1;self.e.store.run(self.run,state)
  with patch.object(self.e,'model') as model:
   with self.assertRaisesRegex(ValueError,'pending tasks were preserved'):self.e.execute(self.run)
  model.assert_not_called();self.assertEqual(self.e.store.run(self.run),state)
 def test_interrupted_task_not_silently_repeated(self):
  state=self.e.store.run(self.run);state['status']['identity']='running';self.e.store.run(self.run,state)
  with patch.object(self.e,'build_task') as build:self.e.execute(self.run)
  build.assert_not_called();self.assertEqual(self.e.store.run(self.run)['status']['identity'],'deferred')
 def test_new_judgment_is_scoped_to_unbuilt_held_task(self):
  from precedent.reconsider import reconsider,task_rules
  state=self.e.store.run(self.run);state['status']['identity']='escalate';state['tasks'].append({**self.task,'id':'other'});state['status']['other']='pending';self.e.store.run(self.run,state)
  revised={**self.rule,'action':'FORK'};self.e.store.save_rule(revised,'ACTIVE')
  before=self.e.store.run(self.run);result=reconsider(self.e,self.run,'identity');after=self.e.store.run(self.run)
  self.assertEqual(result['state'],'pending');self.assertFalse(result['execution_started']);self.assertEqual(after['usage'],before['usage']);self.assertEqual(after['deadline'],before['deadline']);self.assertEqual(after['rule_snapshot'],before['rule_snapshot'])
  self.assertEqual(task_rules(after,'identity')[0]['action'],'FORK');self.assertEqual(task_rules(after,'other')[0]['action'],'STAGE')
  with patch.object(self.e,'build_task',return_value=['test-result']) as build:self.e.execute(self.run)
  self.assertEqual([call.args[2] for call in build.call_args_list],['FORK','STAGE'])
 def test_reconsider_does_not_activate_draft_or_touch_candidates(self):
  from precedent.reconsider import reconsider
  state=self.e.store.run(self.run);state['status']['identity']='escalate';self.e.store.run(self.run,state)
  self.e.store.save_rule({**self.rule,'action':'FORK'})
  result=reconsider(self.e,self.run,'identity');self.assertEqual(result['state'],'escalate')
  self.e.store.candidate('existing',self.run,{'id':'existing','task':'identity'})
  with self.assertRaisesRegex(ValueError,'Existing candidates'):reconsider(self.e,self.run,'identity')
 def test_old_handoff_cannot_cross_reconsideration(self):
  from precedent.reconsider import reconsider
  from precedent.adapters import dispatch
  state=self.e.store.run(self.run);state['status']['identity']='escalate';self.e.store.run(self.run,state)
  self.e.store.save_rule({**self.rule,'action':'FORK'},'ACTIVE');reconsider(self.e,self.run,'identity')
  with patch.object(self.e,'model') as model:
   with self.assertRaisesRegex(ValueError,'changed'):dispatch(self.e,self.body['id'],'identity')
  model.assert_not_called()
 def test_reconsider_stopped_run_is_rejected(self):
  from precedent.reconsider import reconsider
  state=self.e.store.run(self.run);state['status']['identity']='deferred';state['stopped']=True;self.e.store.run(self.run,state)
  with self.assertRaisesRegex(ValueError,'Stopped'):reconsider(self.e,self.run,'identity')

 def test_resumed_test_failure_applies_stop_without_another_model_call(self):
  item=self.interrupted_candidate();state=self.e.store.run(self.run);before=state['usage'].copy()
  state['rule_snapshot'].append({**self.rule,'id':'stop-tests','scope':{'repository':str(self.repo),'event':'FAILED_VERIFICATION'},'when':{'tests_failed':True},'action':'STOP'})
  self.e.store.run(self.run,state)
  with patch('precedent.engine.run_tests',return_value={'passed':False,'output':'controlled retest failure'}),patch.object(self.e,'model') as model:
   result=self.e.resume_review(self.run,item['id']);model.assert_not_called()
  state=self.e.store.run(self.run);self.assertEqual(result['state'],'rejected');self.assertTrue(state['stopped']);self.assertEqual(state['status']['identity'],'stop');self.assertEqual(state['usage'],before)
 def test_import_preserves_review_stop_decision_and_replay(self):
  state=self.e.store.run(self.run);state['rule_snapshot'].append({**self.rule,'id':'stop-review','scope':{'repository':str(self.repo),'event':'FAILED_VERIFICATION'},'when':{'review_failed':True},'action':'STOP'});self.e.store.run(self.run,state)
  export=capsule(self.e.store,self.run,'claude-desktop');self.response['handoff']=json.loads(Path(export['capsule']).read_text())['id']
  with patch.object(self.e,'model',side_effect=[{'tests':TEST},{'verdict':'PASS','findings':[]},{'verdict':'FAIL','findings':['controlled review failure']}]) as model:
   result=self.send();self.assertEqual(self.send(),result);self.assertEqual(model.call_count,3)
  state=self.e.store.run(self.run);self.assertTrue(state['stopped']);self.assertEqual(state['status']['identity'],'stop');self.assertEqual(result['failure_decision']['action'],'STOP');self.assertEqual(result['verified'],[])
