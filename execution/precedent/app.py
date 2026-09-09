"""Local desktop client. Background work never touches Tk from a worker."""
import json,queue,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox,simpledialog
from .engine import Engine,compile_precedent
from .store import Store,encode

class App:
    def __init__(self,home):
        self.home=Path(home).resolve();self.queue=queue.Queue();self.root=tk.Tk();self.root.title('Precedent — 同じ判断を、二度説明しない');self.root.geometry('1080x760')
        self.run_id=None;self.rule_ids=[];self.candidate_ids=[];self.busy=False
        header=ttk.Frame(self.root,padding=16);header.pack(fill='x')
        ttk.Label(header,text='Precedent',font=('Helvetica',25,'bold')).pack(side='left')
        self.status=ttk.Label(header,text='判断を登録 → 分岐を実装 → まとめて確認');self.status.pack(side='right')
        tabs=ttk.Notebook(self.root);self.tabs=tabs;tabs.pack(fill='both',expand=True,padx=16,pady=8)
        calibration=ttk.Frame(tabs,padding=14);work=ttk.Frame(tabs,padding=14);review=ttk.Frame(tabs,padding=14)
        tabs.add(calibration,text='1  判断の登録');tabs.add(work,text='2  実行');tabs.add(review,text='3  一括レビュー')
        ttk.Button(calibration,text='入力フォームで事前判断を登録',command=self.new_rule_form).pack(anchor='w',pady=4)
        ttk.Button(calibration,text='表示中の判断を日本語で確認',command=self.review_rule_summary).pack(anchor='w',pady=4)
        ttk.Label(calibration,text='例：新しい依存が必要になったら、2案を別々に実装して後で比較したい。').pack(anchor='w')
        self.chat=tk.Text(calibration,height=4,wrap='word');self.chat.pack(fill='x',pady=8)
        ttk.Button(calibration,text='ローカルLLMで規則の下書き',command=self.compile).pack(anchor='w')
        self.rules=tk.Listbox(calibration,height=5);self.rules.pack(fill='x',pady=8);self.rules.bind('<<ListboxSelect>>',self.show_rule)
        self.rule=tk.Text(calibration,height=8,wrap='word');self.rule.pack(fill='both',expand=True)
        actions=ttk.Frame(calibration);actions.pack(fill='x',pady=8)
        for title,fn in [('編集を下書き保存',self.save_rule),('SHADOWで試す',lambda:self.transition('SHADOW')),('規則と反例を確認',lambda:self.transition('CONFIRMED')),('有効化',lambda:self.transition('ACTIVE')),('廃止',lambda:self.transition('RETIRED'))]:ttk.Button(actions,text=title,command=fn).pack(side='left',padx=3)
        ttk.Label(work,text='仕事をフォームで追加するか、保存済みの実行内容を読み込みます。').pack(anchor='w')
        ttk.Button(work,text='入力フォームで仕事を追加',command=self.new_task_form).pack(anchor='w',pady=4)
        ttk.Button(work,text='実行内容をファイル保存',command=self.save_manifest).pack(anchor='w',pady=4)
        ttk.Button(work,text='実行マニフェストを開く',command=self.load_manifest).pack(anchor='w',pady=8)
        self.manifest=tk.Text(work,wrap='none');self.manifest.pack(fill='both',expand=True)
        ttk.Button(work,text='事前判断に従って実行',command=self.run).pack(anchor='w',pady=10)
        toolbar=ttk.Frame(review);toolbar.pack(fill='x',pady=6)
        self.past=ttk.Combobox(toolbar,width=24,state='readonly');self.past.pack(side='left')
        ttk.Button(toolbar,text='保存済み実行を表示',command=self.load_run).pack(side='left')
        store=Store(self.home)
        self.past['values']=[r[0] for r in store.db.execute('SELECT id FROM runs ORDER BY rowid DESC')]
        store.close()
        self.candidates=tk.Listbox(review,height=7);self.candidates.pack(fill='x');self.candidates.bind('<<ListboxSelect>>',self.show_candidate)
        review_actions=ttk.Frame(review);review_actions.pack(fill='x',pady=5)
        actions=[('作業履歴と確認対象を表示',self.show_activity),('保留仕事に最新の判断を適用',self.reconsider_task),('未着手の仕事を再開',self.resume_pending),('先の仕事の案を選び、続きを実行',self.continue_dependencies),('残り予算で実行時間を再設定',self.renew_window),('未完了のレビューを再開',self.resume_review),('選んだ検証済み案をpatchとして保存',self.select)]
        for index,(title,callback) in enumerate(actions):ttk.Button(review_actions,text=title,command=callback).grid(row=index//2,column=index%2,sticky='ew',padx=3,pady=3)
        review_actions.columnconfigure(0,weight=1);review_actions.columnconfigure(1,weight=1)
        self.detail=tk.Text(review,height=12,wrap='word');self.detail.pack(fill='both',expand=True,pady=8)
        connections=ttk.Frame(tabs,padding=14);tabs.add(connections,text='4  アプリ接続')
        ttk.Label(connections,text='判断・仕事・予算を保ったまま接続先を交換します。画面引渡しは自動推論と区別します。').pack(anchor='w')
        self.adapter_list=tk.Listbox(connections,height=8);self.adapter_list.pack(fill='x',pady=12)
        self.refresh_adapters()
        ttk.Button(connections,text='接続状態を更新',command=self.refresh_adapters).pack(anchor='w',pady=3)
        ttk.Button(connections,text='モデルとの組合せを確認',command=self.check_adapter).pack(anchor='w',pady=3)
        self.binding_role=ttk.Combobox(connections,values=['builder','test_designer','reviewer'],state='readonly');self.binding_role.set('reviewer');self.binding_role.pack(anchor='w')
        ttk.Button(connections,text='現在と選択中の接続先の自動切替を設定',command=self.configure_routing).pack(anchor='w',pady=3)
        ttk.Button(connections,text='この実行の自動切替を停止',command=lambda:self.configure_routing(disable=True)).pack(anchor='w',pady=3)
        ttk.Button(connections,text='履歴から接続候補を選ぶ',command=self.recommend_adapter).pack(anchor='w',pady=3)
        ttk.Button(connections,text='選択中の実行の接続先を交換',command=self.bind_adapter).pack(anchor='w',pady=3)
        ttk.Button(connections,text='アプリ向けの引継ぎ資料を作成',command=self.prepare_handoff).pack(anchor='w')
        ttk.Button(connections,text='先の仕事から引き継ぐ案を選択',command=lambda:self.continue_dependencies(execute=False)).pack(anchor='w',pady=3)
        ttk.Button(connections,text='選択した接続先に実装を任せて検証',command=self.dispatch_handoff).pack(anchor='w',pady=3)
        ttk.Button(connections,text='引継ぎ先の回答を取り込み・検証',command=self.import_handoff).pack(anchor='w',pady=3)
        ttk.Label(connections,text='資料作成だけでは送信しません。実装を任せる操作で、対応済みの接続先へ渡します。').pack(anchor='w',pady=12)
        from .profile_panel import ProfilePanel
        settings=ttk.Frame(tabs,padding=14);tabs.add(settings,text='5  ローカルAI設定')
        self.profile_panel=ProfilePanel(self,settings)
        tabs.bind('<<NotebookTabChanged>>',lambda event:self.profile_panel.refresh() if tabs.index(tabs.select())==4 else None)
        self.refresh_rules()
        if self.past['values']:
            self.past.current(0);self.load_run();tabs.select(review)
        self.root.after(100,self.poll)
    def refresh_adapters(self):
        from .adapters import discover
        entries=discover(self.home);self.adapter_ids=[e['id'] for e in entries];self.adapter_list.delete(0,'end')
        labels={'auth_required':'要再ログイン','control_unavailable':'操作経路を利用できません','identity_unverified':'画面種別は未確認','observed_input':'入力欄を観測・自動接続未検証','stale':'観測期限切れ','identity_changed':'アプリの識別情報が変更'}
        for entry in entries:
            state='推論接続' if entry['automatic_inference'] else '引渡し準備' if entry['available'] else '未検出・未接続'
            observations=entry.get('desktop_observations',[])
            if observations:state=labels[observations[0]['effective_status']]
            self.adapter_list.insert('end',f'[{state}] {entry["name"]}  /  {entry["id"]}')
    def background(self,fn,kind):
        if self.busy:return messagebox.showinfo('実行中','現在の処理が完了するまでお待ちください。')
        self.busy=True;self.status.config(text='処理中：'+kind)
        def worker():
            try:self.queue.put((kind,fn(),None))
            except Exception as e:self.queue.put((kind,None,str(e)))
        threading.Thread(target=worker,daemon=True).start()
    def poll(self):
        try:
            kind,result,error=self.queue.get_nowait();self.busy=False
            if kind=='ローカル設定':self.profile_panel.refresh()
            if error:self.status.config(text='保留：'+error);messagebox.showerror('処理結果',error)
            elif kind=='規則の下書き':self.refresh_rules();self.rule.delete('1.0','end');self.rule.insert('end',json.dumps(result,ensure_ascii=False,indent=2));self.status.config(text='下書きです。範囲・条件・反例を確認してから有効化してください。')
            elif kind=='回答の検証':
                self.run_id=result['run'];self.refresh_candidates();self.tabs.select(2);self.status.config(text='回答の検証：'+result['state']+(' — '+result['error'] if result.get('error') else ''))
            elif kind in {'候補の実装','先の案を引き継いで実装','保存した仕事の続き'}:
                self.run_id=result;self.refresh_candidates();self.tabs.select(2);self.status.config(text='実行結果を更新しました。検証結果と保留事項を確認できます。')
            else:self.status.config(text='処理結果を受け取りました：'+kind)
        except queue.Empty:pass
        self.root.after(100,self.poll)
    def new_rule_form(self):
        from .rule_form import RuleForm
        RuleForm(self.root,self.save_form_rule)
    def save_form_rule(self,rule):
        store=Store(self.home)
        try:
            if any(r['id']==rule['id'] for r in store.rules()):raise ValueError('同じ名前の判断があります。新しい名前を付けてください。')
            saved=store.save_rule(rule)
        finally:store.close()
        self.refresh_rules();self.rule.delete('1.0','end');self.rule.insert('end',json.dumps(saved,ensure_ascii=False,indent=2));self.status.config(text='事前判断を下書き保存しました。内容を確認してから有効化できます。')
    def review_rule_summary(self):
        from .rule_form import summary
        try:messagebox.showinfo('判断の内容',summary(json.loads(self.rule.get('1.0','end'))))
        except Exception as error:messagebox.showerror('判断の内容',str(error))
    def compile(self):
        text=self.chat.get('1.0','end').strip()
        if not text:return
        def task():
            rule,usage=compile_precedent(text);store=Store(self.home)
            try:rule=store.save_rule(rule);store.event('calibration',{'utterance':text,'usage':usage});return rule
            finally:store.close()
        self.background(task,'規則の下書き')
    def refresh_rules(self):
        store=Store(self.home)
        try:rules=store.rules()
        finally:store.close()
        self.rules.delete(0,'end');self.rule_ids=[]
        for r in rules:self.rules.insert('end',f'{r["id"]}   v{r["version"]}   {r["status"]}   {r["action"]}');self.rule_ids.append(r['id'])
    def show_rule(self,event=None):
        if not self.rules.curselection():return
        key=self.rule_ids[self.rules.curselection()[0]];store=Store(self.home)
        try:r=next(r for r in store.rules() if r['id']==key)
        finally:store.close()
        self.rule.delete('1.0','end');self.rule.insert('end',json.dumps(r,ensure_ascii=False,indent=2))
    def save_rule(self):
        store=Store(self.home)
        try:
            r=store.save_rule(json.loads(self.rule.get('1.0','end')));self.refresh_rules();self.rule.delete('1.0','end');self.rule.insert('end',json.dumps(r,ensure_ascii=False,indent=2))
        except Exception as e:messagebox.showerror('規則',str(e))
        finally:store.close()
    def transition(self,status):
        store=Store(self.home)
        try:
            edited=json.loads(self.rule.get('1.0','end'));key=edited['id']
            if edited!=next(r for r in store.rules() if r['id']==key):raise ValueError('編集した規則を先に下書き保存してください。')
            r=store.transition(key,status);self.refresh_rules();self.rule.delete('1.0','end');self.rule.insert('end',json.dumps(r,ensure_ascii=False,indent=2))
        except Exception as e:messagebox.showerror('規則',str(e))
        finally:store.close()
    def new_task_form(self):
        from .task_form import TaskForm
        try:
            text=self.manifest.get('1.0','end').strip();current=json.loads(text) if text else {}
            if not isinstance(current,dict):raise ValueError('実行内容はオブジェクトで指定してください。')
            TaskForm(self.root,current,self.set_manifest)
        except Exception as error:messagebox.showerror('実行内容',str(error))
    def set_manifest(self,manifest):
        self.manifest.delete('1.0','end');self.manifest.insert('end',json.dumps(manifest,ensure_ascii=False,indent=2));self.status.config(text=str(len(manifest['tasks']))+'件の仕事を準備しました。まだ実行していません。')
    def save_manifest(self):
        try:
            body=json.loads(self.manifest.get('1.0','end'))
            path=filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('実行内容','*.json')])
            if path:Path(path).write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n')
        except Exception as error:messagebox.showerror('実行内容を保存できません',str(error))
    def load_manifest(self):
        path=filedialog.askopenfilename(filetypes=[('JSON','*.json')])
        if path:self.manifest.delete('1.0','end');self.manifest.insert('end',Path(path).read_text())
    def run(self):
        try:manifest=json.loads(self.manifest.get('1.0','end'))
        except Exception as e:return messagebox.showerror('マニフェスト',str(e))
        def task():
            engine=Engine(self.home)
            try:key=engine.create(manifest);engine.execute(key);return key
            finally:engine.close()
        self.background(task,'候補の実装')
    def load_run(self):
        if self.past.get():self.run_id=self.past.get();self.refresh_candidates()
    def refresh_candidates(self):
        engine=Engine(self.home)
        try:
            bundle=engine.bundle(self.run_id)
            self.past['values']=[r[0] for r in engine.store.db.execute('SELECT id FROM runs ORDER BY rowid DESC')]
            self.past.set(self.run_id)
        finally:engine.close()
        self.candidates.delete(0,'end');self.candidate_ids=[]
        for c in sorted(bundle['candidates'],key=lambda c:c['state']!='verified'):self.candidates.insert('end',f'[{c["state"]}] {c["task"]} | {c["option"][:85]}');self.candidate_ids.append(c['id'])
        lines=[f'実行 {self.run_id}',f'確認できた仕事: {bundle["metrics"]["ready_tasks"]}   保留: {bundle["metrics"]["held_tasks"]}   不採用候補: {bundle["metrics"]["rejected_candidates"]}',f'ローカル呼出し: {bundle["usage"]["local_calls"]}/{bundle["limits"]["local_calls"]}   クラウド呼出し: {bundle["usage"]["cloud_calls"]}/{bundle["limits"]["cloud_calls"]}','元の作業木への自動反映: なし','', '判断と保留事項']
        for key,status in bundle['status'].items():
            d=bundle['decisions'].get(key,{})
            lines += [f'\n{key}  —  {d.get("action",status)}',d.get('reason',''),d.get('execution_error','')]
        lines += ['', 'この実行は停止されています。未着手の仕事も再開しません。' if bundle.get('stopped') else '未着手: '+str(sum(v=='pending' for v in bundle['status'].values()))+'件。再開すると、この部分だけを実行します。']
        lines += ['','現在の接続先']
        for role in ['builder','test_designer','reviewer']:
            lines.append(role+': '+bundle.get('bindings',{}).get(role,'ollama' if role=='builder' else 'claude-cli'))
        if bundle.get('routing_switches'):lines.append('自動切替の累計: '+str(len(bundle['routing_switches'])))
        lines += ['','上の候補を選ぶと、差分と検査結果を確認できます。','金額・監視時間・やり直し時間の削減率は未測定です。']
        self.detail.delete('1.0','end');self.detail.insert('end','\n'.join(lines))
    def show_activity(self):
        from .attention import Recorder
        from .activity_window import ActivityWindow
        if not self.run_id:return messagebox.showinfo('作業履歴','保存済みの実行を選択してください。')
        if not hasattr(self,'attention_recorder'):self.attention_recorder=Recorder()
        view=ActivityWindow(self,self.run_id);view.window.activity_view=view;return view.window
    def show_candidate(self,event=None):
        if not self.candidates.curselection():return
        store=Store(self.home)
        try:c=store.candidate(self.candidate_ids[self.candidates.curselection()[0]])
        finally:store.close()
        lines=[f'候補 {c["id"]} — {c["state"]}',c['option'],'',f'公開テスト: {(c.get("public") or {}).get("passed","未実行")}',f'追加テスト: {(c.get("holdout") or {}).get("passed","未実行")}',f'クラウドレビュー: {(c.get("cloud") or {}).get("verdict","未実行")}',c.get('error',''),c.get('review_error',''),'']
        if c.get('failure_decision'):
            decision=c['failure_decision'];lines += ['失敗後の判断: '+decision['action']+' / '+decision['reason'] if decision['rules'] else '適用する失敗時の判断なし。既定の修正上限に従います。']
        if c.get('repair_of'):lines += ['修正元の候補: '+c['repair_of']]
        if c.get('syntax_failure'):
            failure=c['syntax_failure'];lines += ['','書込み前に構文エラーとなった原文',str(failure['file'])+' / 行 '+str(failure.get('line'))+': '+failure['message'],failure['source']]
        lines += (c.get('cloud') or {}).get('findings',[])
        if c.get('dependency_reports'):
            lines += ['','先の仕事の再検証']
            lines += [r['candidate']+': '+('合格' if r['passed'] else '不合格') for r in c['dependency_reports']]
        lines += ['','差分',c.get('patch') or '差分なし']
        self.detail.delete('1.0','end');self.detail.insert('end','\n'.join(lines))
    def continue_dependencies(self,execute=True):
        if self.busy or not self.run_id:return
        engine=Engine(self.home)
        try:
            state=engine.store.run(self.run_id);items=engine.store.candidates(self.run_id)
            tasks=[t for t in state['tasks'] if t.get('depends_on') and not any(c['task']==t['id'] for c in items)]
            if not tasks:raise ValueError('案の引継ぎを待っている仕事はありません。')
            number=simpledialog.askinteger('続ける仕事','\n'.join(str(i+1)+': '+t['id'] for i,t in enumerate(tasks)),minvalue=1,maxvalue=len(tasks))
            if number is None:return
            task=tasks[number-1];selections={}
            for parent in task['depends_on']:
                choices=[c for c in items if c['task']==parent and c['state']=='verified']
                if not choices:raise ValueError(parent+' に検証済みの案がありません。')
                number=simpledialog.askinteger('引き継ぐ案: '+parent,'\n'.join(str(i+1)+': '+c['option']+' ['+c['id']+']' for i,c in enumerate(choices)),minvalue=1,maxvalue=len(choices))
                if number is None:return
                selections[parent]=choices[number-1]['id']
            from .dependencies import bind
            bind(engine,self.run_id,task['id'],selections)
        except Exception as error:messagebox.showerror('続きを実行できません',str(error));return
        finally:engine.close()
        if not execute:
            self.refresh_candidates();self.status.config(text='引き継ぐ案を保存しました。接続先を選んで実装を任せられます。');return
        run=self.run_id
        def work():
            e=Engine(self.home)
            try:e.execute(run);return run
            finally:e.close()
        self.background(work,'先の案を引き継いで実装')
    def renew_window(self):
        if self.busy or not self.run_id:return
        engine=Engine(self.home)
        try:
            state=engine.store.run(self.run_id)
            result=engine.renew_window(self.run_id,state['limits']['seconds'],state['deadline'])
            self.status.config(text='実行可能時間を'+str(result['seconds'])+'秒に再設定しました。使用済み予算は保持されています。')
            self.refresh_candidates()
        except Exception as error:messagebox.showerror('実行時間を変更できません',str(error))
        finally:engine.close()
    def reconsider_task(self):
        if self.busy or not self.run_id:return
        from .reconsider import reconsider
        engine=Engine(self.home)
        try:
            state=engine.store.run(self.run_id);built={c['task'] for c in engine.store.candidates(self.run_id)}
            choices=[key for key,status in state['status'].items() if status in {'defer','deferred','escalate'} and key not in built]
            if not choices:raise ValueError('候補をまだ作っていない保留仕事はありません。')
            number=simpledialog.askinteger('最新の判断を適用する仕事','\n'.join(str(i+1)+': '+key for i,key in enumerate(choices)),minvalue=1,maxvalue=len(choices))
            if number is None:return
            result=reconsider(engine,self.run_id,choices[number-1]);self.refresh_candidates();self.status.config(text='判断を更新しました：'+result['state']+'。実装はまだ開始していません。')
        except Exception as error:messagebox.showerror('判断を適用できません',str(error))
        finally:engine.close()
    def resume_pending(self):
        if self.busy or not self.run_id:return
        run=self.run_id
        def work():
            engine=Engine(self.home)
            try:engine.execute(run);return run
            finally:engine.close()
        self.background(work,'保存した仕事の続き')
    def resume_review(self):
        if self.busy or not self.run_id or not self.candidates.curselection():return
        run=self.run_id;candidate=self.candidate_ids[self.candidates.curselection()[0]]
        def task():
            engine=Engine(self.home)
            try:return engine.resume_review(run,candidate)
            finally:engine.close()
        self.background(task,'回答の検証')
    def select(self):
        if not self.candidates.curselection():return
        engine=Engine(self.home)
        try:path=engine.select(self.run_id,self.candidate_ids[self.candidates.curselection()[0]]);messagebox.showinfo('保存',str(path))
        except Exception as e:messagebox.showerror('選択できません',str(e))
        finally:engine.close()
    def check_adapter(self):
        if not self.run_id or not self.adapter_list.curselection():return
        from .capabilities import check
        store=Store(self.home)
        try:
            state=store.run(self.run_id);result=check(self.adapter_ids[self.adapter_list.curselection()[0]],state['local_model'])
            labels={'compatible':'文脈長の要件を満たしています','incompatible':'文脈長が不足しています','unverified':'モデルの文脈長を確認できませんでした','no_declared_model_requirement':'この接続先には今回検査する文脈長要件がありません'}
            messagebox.showinfo('組合せの確認',labels[result['status']]+'\nモデル: '+state['local_model']+'\nこの確認では推論を実行していません。認証や実際の処理成功は別の確認が必要です。')
        except Exception as error:messagebox.showerror('組合せの確認',str(error))
        finally:store.close()
    def configure_routing(self,disable=False):
        if self.busy or not self.run_id:return
        if not disable and not self.adapter_list.curselection():return
        from .routing import configure
        engine=Engine(self.home)
        try:
            state=engine.store.run(self.run_id);rules=dict(state.get('routing',{}).get('rules',{}))
            role=self.binding_role.get();current=state.get('bindings',{}).get(role,'ollama' if role=='builder' else 'claude-cli')
            if disable:rules={}
            else:
                selected=self.adapter_ids[self.adapter_list.curselection()[0]]
                rules[role]={'allowed':list(dict.fromkeys([current,selected])),'min_valid_responses':2,'max_switches':2}
            configure(engine,self.run_id,rules)
            messagebox.showinfo('自動切替', '自動切替を停止しました。' if disable else '設定しました。回答形式の成功実績が2件以上ある候補へ、接続・形式の失敗後に最大2回切り替えます。失敗した呼出しは自動再送しません。')
        except Exception as error:messagebox.showerror('自動切替',str(error))
        finally:engine.close()
    def recommend_adapter(self):
        if not self.run_id:return
        from .transport_health import recommendations
        store=Store(self.home)
        try:
            report=recommendations(store,self.run_id,self.binding_role.get())
            self.refresh_adapters()
            if report['suggested'] in self.adapter_ids:
                index=self.adapter_ids.index(report['suggested']);self.adapter_list.selection_set(index);self.adapter_list.see(index)
            lines=[x['adapter']+': 正しい回答形式 '+str(x['valid_responses'])+'/'+str(x['samples'])+'件' for x in report['alternatives']]
            messagebox.showinfo('接続履歴', '\n'.join(lines)+'\n候補: '+str(report['suggested'] or '利用可能な候補なし')+'\n候補を選択しました。接続先の交換は下のボタンで行えます。\nコードの正しさや現在の認証状態を示す成績ではありません。')
        except Exception as error:messagebox.showerror('接続履歴',str(error))
        finally:store.close()
    def bind_adapter(self):
        if not self.run_id or not self.adapter_list.curselection():return
        from .adapters import bind
        store=Store(self.home)
        try:
            result=bind(store,self.run_id,self.binding_role.get(),self.adapter_ids[self.adapter_list.curselection()[0]])
            messagebox.showinfo('接続先を保存',json.dumps(result,ensure_ascii=False))
        except Exception as e:messagebox.showerror('接続',str(e))
        finally:store.close()
    def prepare_handoff(self):
        if not self.run_id or not self.adapter_list.curselection():return
        from .adapters import capsule
        store=Store(self.home)
        try:
            result=capsule(store,self.run_id,self.adapter_ids[self.adapter_list.curselection()[0]])
            messagebox.showinfo('引継ぎ資料を保存',result['readable'])
        except Exception as e:messagebox.showerror('引継ぎ',str(e))
        finally:store.close()
    def dispatch_handoff(self):
        if self.busy or not self.run_id or not self.adapter_list.curselection():return
        from .adapters import handoff_eligibility,require_inference,capsule,dispatch
        adapter=self.adapter_ids[self.adapter_list.curselection()[0]];run=self.run_id
        store=Store(self.home)
        try:
            require_inference(adapter);state=store.run(run)
            choices=[(t,option) for t in state['tasks'] if handoff_eligibility(state,t)['eligible'] for option in t.get('options',['Implement the requirement'])]
            if not choices:raise ValueError('現在、引き継いで実装できる仕事はありません。')
        except Exception as error:messagebox.showerror('引継ぎ',str(error));return
        finally:store.close()
        selected=1 if len(choices)==1 else simpledialog.askinteger('実装する案を選択','番号を選んでください。\n'+'\n'.join(str(i+1)+'. '+t['id']+' — '+option for i,(t,option) in enumerate(choices)),minvalue=1,maxvalue=len(choices))
        if selected is None:return
        chosen,option=choices[selected-1]
        def task():
            engine=Engine(self.home)
            try:
                export=capsule(engine.store,run,adapter);key=json.loads(Path(export['capsule']).read_text())['id']
                return dispatch(engine,key,chosen['id'],option)
            finally:engine.close()
        self.background(task,'回答の検証')
    def import_handoff(self):
        path=filedialog.askopenfilename(filetypes=[('JSON','*.json')])
        if not path:return
        def task():
            from .adapters import import_response
            engine=Engine(self.home)
            try:return import_response(engine,path)
            finally:engine.close()
        self.background(task,'回答の検証')
    def main(self):self.root.mainloop()
