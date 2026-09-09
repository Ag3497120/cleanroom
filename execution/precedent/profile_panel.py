"""Human controls for persisted, bounded local settings trials."""
import json
import tkinter as tk
from tkinter import ttk,messagebox
from .engine import Engine
from .store import Store
from . import profiles

class ProfilePanel:
    def __init__(self,app,parent):
        self.app=app;self.reports=[];self.fields={}
        ttk.Label(parent,text='選択中の実行でOllamaの設定を比較します。比較はローカル呼出しを4回使用します。').pack(anchor='w')
        self.context=ttk.Label(parent,text='一括レビューで実行を選択してください。',wraplength=960);self.context.pack(anchor='w',pady=8)
        form=ttk.Frame(parent);form.pack(fill='x')
        for row,(key,label) in enumerate([('temperature','回答のばらつき（0〜1）'),('num_predict','出力の上限（512〜8192）'),('num_ctx','文脈の上限（4096〜32768）')]):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',pady=3)
            field=ttk.Entry(form,width=18);field.insert(0,str(profiles.DEFAULT[key]));field.grid(row=row,column=1);self.fields[key]=field
        ttk.Button(parent,text='履歴から設定案を入力',command=self.suggest).pack(anchor='w',pady=4)
        actions=ttk.Frame(parent);actions.pack(fill='x',pady=8)
        for label,callback in [('状態と履歴を更新',self.refresh),('この設定を比較（4回）',self.compare),('選んだ比較の設定を適用',self.activate),('既定の設定へ戻す',self.reset)]:ttk.Button(actions,text=label,command=callback).pack(side='left',padx=3)
        ttk.Label(parent,text='適用・復元は、この保存場所で同じモデルを使うOllama呼出し全体に次回から反映されます。再起動は不要です。',wraplength=960).pack(anchor='w')
        self.history=tk.Listbox(parent,height=5);self.history.pack(fill='x',pady=8);self.history.bind('<<ListboxSelect>>',self.show)
        self.detail=tk.Text(parent,height=10,wrap='word');self.detail.pack(fill='both',expand=True)
    def refresh(self):
        store=Store(self.app.home)
        try:
            state=store.run(self.app.run_id) if self.app.run_id else None
            self.reports=[];self.history.delete(0,'end');self.detail.delete('1.0','end')
            if not state:self.context.config(text='一括レビューで実行を選択してください。');return
            model=state['local_model'];current=profiles.stored(store,model)
            self.context.config(text=f"実行: {self.app.run_id} / モデル: {model}\n残りローカル呼出し: {state['limits']['local_calls']-state['usage']['local_calls']} / 保存中の設定: {current['options']}\nモデルの同一性は比較・適用・推論時に確認します。")
            for row in store.db.execute("SELECT body FROM ledger WHERE kind='profile_trial' ORDER BY seq DESC"):
                report=json.loads(row[0])
                if report['run']==self.app.run_id:self.reports.append(report);self.history.insert('end',report['id']+' / '+('固定課題に合格' if report['eligible'] else '不合格・適用不可'))
            if self.reports:self.history.selection_set(0);self.show()
        finally:store.close()
    def show(self,event=None):
        if not self.history.curselection():return
        report=self.reports[self.history.curselection()[0]]
        lines=[f"比較: {report['id']}",f"元の設定: {report['baseline']}",f"候補の設定: {report['options']}",'適用状況は上の「保存中の設定」で確認してください。']
        for case in report['cases']:
            lines.append(f"{case['profile']} / {case['case']}: {'合格' if case['passed'] else '不合格'} / {case['seconds']:.2f}秒 / {case['tokens_observed']}トークン"+(' / '+case['error'] if case.get('error') else ''))
        lines.append('固定した整数関数2種類だけの試験です。合格は速度向上や未知の仕事の成功を保証しません。実行順序やキャッシュによる時間差は未除去です。')
        self.detail.delete('1.0','end');self.detail.insert('end','\n'.join(lines))
    def suggest(self):
        store=Store(self.app.home)
        try:
            if not self.app.run_id:raise ValueError('一括レビューで実行を選択してください。')
            result=profiles.suggest(store,self.app.run_id)
            if result['proposed']:
                for key,value in result['options'].items():self.fields[key].delete(0,'end');self.fields[key].insert(0,str(value))
            self.detail.delete('1.0','end');self.detail.insert('end',result['reason']+'\n根拠の記録番号: '+', '.join(str(row['seq']) for row in result['evidence'])+'\nこの操作は入力欄だけを変更します。比較・適用はまだ行っていません。モデル名の一致は過去の重みの同一性を証明しません。')
        except Exception as error:messagebox.showerror('設定案',str(error))
        finally:store.close()
    def submit(self,operation):
        def work():
            engine=Engine(self.app.home)
            try:return operation(engine)
            finally:engine.close()
        self.app.background(work,'ローカル設定')
    def compare(self):
        try:
            if not self.app.run_id:raise ValueError('一括レビューで実行を選択してください。')
            options=profiles.validate({key:(float(field.get()) if key=='temperature' else int(field.get())) for key,field in self.fields.items()});run=self.app.run_id
            self.submit(lambda engine:profiles.evaluate(engine,run,options))
        except Exception as error:messagebox.showerror('設定の比較',str(error))
    def activate(self):
        if not self.history.curselection():return messagebox.showinfo('設定の適用','比較結果を選択してください。')
        trial=self.reports[self.history.curselection()[0]]['id'];self.submit(lambda engine:profiles.activate(engine,trial))
    def reset(self):
        store=Store(self.app.home)
        try:state=store.run(self.app.run_id) if self.app.run_id else None
        finally:store.close()
        if not state:return messagebox.showinfo('設定の復元','一括レビューで実行を選択してください。')
        model=state['local_model'];self.submit(lambda engine:profiles.reset(engine,model))
