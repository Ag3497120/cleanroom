"""Real Tk result delivery; no live model calls or external app control."""
import queue,tempfile,unittest
from pathlib import Path
from precedent.app import App
from precedent.engine import Engine
from precedent.execution import git

class AppResults(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name).resolve();repo=root/'repo';repo.mkdir()
  (repo/'x.py').write_text('def f(x):return x\n');(repo/'test_x.py').write_text('import unittest\nclass Test(unittest.TestCase):\n def test_one(self):self.assertTrue(True)\n')
  git(repo,'init');git(repo,'add','.');git(repo,'-c','user.name=Test','-c','user.email=test@example.test','commit','-m','base')
  self.home=root/'state';self.e=Engine(self.home);self.manifest={'repository':str(repo),'tasks':[{'id':'task','event':'AMBIGUOUS_REQUIREMENT','editable':['x.py'],'tests':['test_x.py'],'requirement':'identity'}]}
  self.app=App(self.home);self.app.root.update()
 def tearDown(self):
  for job in self.app.root.tk.call('after','info'):self.app.root.after_cancel(job)
  self.app.root.destroy();self.e.close();self.tmp.cleanup()
 def test_dependency_result_updates_view_and_history(self):
  run=self.e.create(self.manifest)
  self.e.store.candidate('candidate',run,{'id':'candidate','worktree':self.manifest['repository'],'task':'task','state':'review_required','option':'identity','review_error':'format failure','dependency_reports':[{'candidate':'parent','passed':False}]})
  self.app.busy=True;self.app.status.config(text='処理中');self.app.queue.put(('先の案を引き継いで実装',run,None));self.app.poll();self.app.root.update()
  self.assertFalse(self.app.busy);self.assertEqual(self.app.run_id,run);self.assertEqual(self.app.past.get(),run);self.assertIn(run,self.app.past['values']);self.assertEqual(self.app.candidate_ids,['candidate'])
  self.assertNotIn('処理中',self.app.status.cget('text'));self.assertNotIn('完了',self.app.status.cget('text'))
  self.app.candidates.selection_set(0);self.app.show_candidate();self.assertIn('parent: 不合格',self.app.detail.get('1.0','end'));self.assertIn('format failure',self.app.detail.get('1.0','end'))
 def test_review_response_selects_returned_run_and_refreshes(self):
  run=self.e.create(self.manifest);self.app.busy=True;self.app.queue.put(('回答の検証',{'run':run,'state':'review_required'},None));self.app.poll()
  self.assertFalse(self.app.busy);self.assertEqual(self.app.past.get(),run);self.assertIn('review_required',self.app.status.cget('text'))
 def test_form_saves_draft_without_model_or_activation(self):
  from precedent.rule_form import RuleForm
  from unittest.mock import patch
  form=RuleForm(self.app.root,self.app.save_form_rule)
  form.fields['folder'].insert(0,self.manifest['repository']);form.fields['name'].insert(0,'human-choice');form.fields['examples'].insert('1.0','ambiguous');form.fields['counterexamples'].insert('1.0','clear')
  with patch('precedent.engine.invoke') as invoke:form.save()
  invoke.assert_not_called();saved=self.e.store.rules()[0];self.assertEqual(saved['status'],'DRAFT');self.assertEqual(saved['id'],'human-choice');self.assertIn('human-choice',self.app.rule.get('1.0','end'))
  with self.assertRaises(ValueError):self.app.save_form_rule(saved)
 def test_task_form_only_prepares_manifest(self):
  from precedent.task_form import TaskForm
  from unittest.mock import patch
  import json
  form=TaskForm(self.app.root,{},self.app.set_manifest)
  for key,value in [('folder',self.manifest['repository']),('name','task')]:form.fields[key].insert(0,value)
  for key,value in [('requirement','identity'),('editable','x.py'),('tests','test_x.py')]:form.fields[key].insert('1.0',value)
  with patch('precedent.engine.invoke') as invoke:form.save()
  invoke.assert_not_called();body=json.loads(self.app.manifest.get('1.0','end'));self.assertEqual(body['tasks'][0]['id'],'task');self.assertEqual(self.e.store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],0)
 def test_restart_and_pending_resume_callback(self):
  from unittest.mock import patch
  run=self.e.create(self.manifest);self.app.past['values']=[run];self.app.past.set(run);self.app.load_run()
  with patch.object(self.app,'background') as background:self.app.resume_pending()
  work,kind=background.call_args.args;self.assertEqual(kind,'保存した仕事の続き')
  with patch('precedent.app.Engine.execute',return_value={}):self.assertEqual(work(),run)
  self.app.busy=True;self.app.queue.put((kind,run,None));self.app.poll();self.assertFalse(self.app.busy);self.assertEqual(self.app.run_id,run);self.assertIn('未着手: 1件',self.app.detail.get('1.0','end'))
 def test_held_task_adopts_registered_judgment_without_starting(self):
  from unittest.mock import patch
  from precedent.rule_form import draft
  run=self.e.create(self.manifest);self.e.execute(run);self.app.run_id=run
  rule=draft('registered',self.manifest['repository'],False,'要望の解釈が複数ある','1案を確認用に残す',[],[],'','identity','other','')
  self.e.store.save_rule(rule);self.e.store.transition(rule['id'],'CONFIRMED');self.e.store.transition(rule['id'],'ACTIVE')
  with patch('precedent.app.simpledialog.askinteger',return_value=1),patch('precedent.engine.invoke') as invoke:self.app.reconsider_task()
  invoke.assert_not_called();state=self.e.store.run(run);self.assertEqual(state['status']['task'],'pending');self.assertEqual(state['usage']['cloud_calls'],0);self.assertEqual(state['rule_snapshot'],[]);self.assertIn('task',state['task_rule_snapshots'])

 def test_all_review_actions_are_visible_at_default_window_size(self):
  self.app.tabs.select(2);self.app.root.update();frame=self.app.tabs.nametowidget(self.app.tabs.select());buttons=[]
  def walk(widget):
   if widget.winfo_class()=='TButton':buttons.append(widget)
   for child in widget.winfo_children():walk(child)
  walk(frame);self.assertEqual(len(buttons),8)
  for button in buttons:
   self.assertTrue(button.winfo_viewable(),button.cget('text'));self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),self.app.root.winfo_rooty()+self.app.root.winfo_height())

 def test_profile_controls_preserve_trial_and_use_explicit_actions(self):
  from unittest.mock import patch
  from precedent.profiles import DEFAULT
  run=self.e.create(self.manifest);self.app.run_id=run;panel=self.app.profile_panel
  report={'id':'trial','run':run,'model':'model','baseline':DEFAULT,'options':dict(DEFAULT,num_ctx=12288),'eligible':True,'cases':[]}
  self.e.store.event('profile_trial',report);panel.refresh()
  self.assertEqual(panel.reports,[report]);self.assertIn('保証しません',panel.detail.get('1.0','end'))
  with patch.object(self.app,'background') as background:
   panel.compare();work,kind=background.call_args.args
  with patch('precedent.profiles.evaluate',return_value=report) as evaluate:
   self.assertEqual(work(),report);self.assertEqual(evaluate.call_args.args[1:],(run,DEFAULT))
  self.app.queue.put((kind,report,None));self.app.poll()
  self.assertEqual(self.e.store.db.execute("SELECT COUNT(*) FROM ledger WHERE kind='profile_activated'").fetchone()[0],0)
  with patch.object(self.app,'background') as background:panel.activate();work,_=background.call_args.args
  with patch('precedent.profiles.activate') as activate:work();self.assertEqual(activate.call_args.args[1],'trial')
  with patch.object(self.app,'background') as background:panel.reset();work,_=background.call_args.args
  work();self.assertEqual(self.e.store.db.execute("SELECT COUNT(*) FROM ledger WHERE kind='profile_activated'").fetchone()[0],1)
  self.app.tabs.select(4);self.app.root.update()
  def walk(widget):
   for child in widget.winfo_children():
    if child.winfo_class()=='TButton':
     self.assertTrue(child.winfo_viewable());self.assertLessEqual(child.winfo_rootx()+child.winfo_width(),self.app.root.winfo_rootx()+self.app.root.winfo_width())
    walk(child)
  walk(self.app.tabs.nametowidget(self.app.tabs.select()))

 def test_activity_window_reads_persisted_state_without_inference(self):
  from unittest.mock import patch
  run=self.e.create(self.manifest);self.app.run_id=run
  self.e.store.event('adapter_replaced',{'run':run,'role':'reviewer','new':'codex-cli'})
  before=self.e.store.db.execute('SELECT COUNT(*) FROM ledger').fetchone()[0]
  with patch('precedent.engine.invoke') as invoke:window=self.app.show_activity();self.app.root.update()
  invoke.assert_not_called()
  texts=[]
  def walk(widget):
   if widget.winfo_class()=='Text':texts.append(widget.get('1.0','end'))
   for child in widget.winfo_children():walk(child)
  walk(window);self.assertIn('記録された明示操作: 1件',texts[0]);self.assertIn('監視時間・やり直し時間・削減率は未測定',texts[0]);window.destroy()
  self.assertEqual(before,self.e.store.db.execute('SELECT COUNT(*) FROM ledger').fetchone()[0])

 def test_attention_controls_persist_completed_and_unknown_intervals(self):
  from unittest.mock import patch
  from precedent.attention import Recorder,summary
  run=self.e.create(self.manifest);self.app.run_id=run;window=self.app.show_activity();view=window.activity_view
  with patch('precedent.engine.invoke') as invoke:
   view.start();view.finish();view.category.set('修正');view.start()
  invoke.assert_not_called();body=summary(self.e.store,run);self.assertEqual(body['unfinished_count'],1);self.assertIsNotNone(body['completed_elapsed_seconds'])
  window.destroy();self.app.attention_recorder=Recorder();window=self.app.show_activity();view=window.activity_view
  with patch('precedent.activity_window.messagebox.showerror') as error:view.finish();error.assert_called_once()
  view.finish(True);self.assertEqual(summary(self.e.store,run)['abandoned_count'],1);self.assertIn('時間不明',view.text.get('1.0','end'));window.destroy()

 def test_corrupt_ledger_diagnostic_can_be_viewed_and_exported(self):
  from unittest.mock import patch
  import json
  run=self.e.create(self.manifest);self.app.run_id=run
  self.e.store.db.execute('DROP TRIGGER immutable_ledger_update');self.e.store.db.execute("UPDATE ledger SET body='not json' WHERE seq=1");self.e.store.db.commit()
  window=self.app.show_activity();view=window.activity_view;self.app.root.update()
  self.assertIn('問題の記録番号: 1',view.text.get('1.0','end'));self.assertFalse(view.body['summary_available']);self.assertEqual(str(view.buttons['計測開始'].cget('state')),'disabled')
  path=Path(self.tmp.name)/'diagnostic.json'
  with patch('precedent.activity_window.filedialog.asksaveasfilename',return_value=str(path)):view.save()
  saved=json.loads(path.read_text());self.assertFalse(saved['ledger_consistency']['valid']);self.assertNotIn('recorded_control_operations',saved)
  self.assertEqual(self.e.store.db.execute('SELECT body FROM ledger WHERE seq=1').fetchone()[0],'not json');window.destroy()

 def test_profile_suggestion_fills_fields_without_inference_or_activation(self):
  from precedent.profiles import DEFAULT
  from unittest.mock import patch
  run=self.e.create(self.manifest);self.app.run_id=run;model=self.e.store.run(run)['local_model']
  for _ in range(2):self.e.store.event('model_call',{'run':run,'provider':'ollama','model':model,'profile_options':DEFAULT,'done_reason':'length','response_rejected':True})
  before=self.e.store.db.execute('SELECT COUNT(*) FROM ledger').fetchone()[0]
  with patch('precedent.engine.invoke') as invoke:self.app.profile_panel.suggest()
  invoke.assert_not_called();self.assertEqual(self.app.profile_panel.fields['num_predict'].get(),'8192');self.assertIn('改善は未検証',self.app.profile_panel.detail.get('1.0','end'));self.assertEqual(before,self.e.store.db.execute('SELECT COUNT(*) FROM ledger').fetchone()[0])
