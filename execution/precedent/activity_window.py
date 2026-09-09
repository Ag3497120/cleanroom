"""Evidence viewer and explicit interval controls, without inferred focus tracking."""
import json,tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
from .store import Store
from .activity import report,describe
from .attention import CATEGORIES,intervals

class ActivityWindow:
    def __init__(self,app,run):
        self.app=app;self.run=run;self.body=None
        self.window=tk.Toplevel(app.root);self.window.title('作業履歴と確認対象');self.window.geometry('900x680')
        ttk.Label(self.window,text='明示的に開始・終了した区間の経過時間を記録します。離席中も含むため、人間が見ていた時間の証明にはなりません。',wraplength=850).pack(anchor='w',padx=12,pady=8)
        actions=ttk.Frame(self.window);actions.pack(fill='x',padx=12)
        self.category=ttk.Combobox(actions,values=list(CATEGORIES.values()),state='readonly',width=8);self.category.set('確認');self.category.pack(side='left')
        self.buttons={}
        for label,callback in [('計測開始',self.start),('終了して記録',self.finish),('時間不明で閉じる',lambda:self.finish(True)),('履歴を更新',self.refresh),('履歴を保存',self.save)]:
            button=ttk.Button(actions,text=label,command=callback);button.pack(side='left',padx=3);self.buttons[label]=button
        self.state=ttk.Label(self.window,wraplength=850);self.state.pack(anchor='w',padx=12,pady=8)
        frame=ttk.Frame(self.window);frame.pack(fill='both',expand=True,padx=12,pady=8)
        self.text=tk.Text(frame,wrap='word');scroll=ttk.Scrollbar(frame,command=self.text.yview);self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.text.pack(fill='both',expand=True);self.refresh()
    def refresh(self):
        store=Store(self.app.home)
        try:
            self.body=report(store,self.run);available=self.body.get('summary_available',True);opened=next((r for r in intervals(store) if r['state']=='open'),None) if available else None
        finally:store.close()
        self.state.config(text=('未終了の計測: 実行 '+opened['run']+' / '+CATEGORIES[opened['category']]+'。画面を閉じても自動終了しません。' if opened else '現在、計測していません。')+' 履歴は更新時点の表示です。')
        for label in ('計測開始','終了して記録','時間不明で閉じる'):self.buttons[label].configure(state='normal' if available else 'disabled')
        if not available:self.state.config(text='保存履歴の不整合のため、計測操作を停止しています。診断の表示・保存は利用できます。')
        self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('end',describe(self.body));self.text.configure(state='disabled')
    def start(self):
        store=Store(self.app.home)
        try:self.app.attention_recorder.start(store,self.run,next(k for k,v in CATEGORIES.items() if v==self.category.get()))
        except Exception as error:messagebox.showerror('計測を開始できません',str(error),parent=self.window)
        finally:store.close()
        self.refresh()
    def finish(self,abandon=False):
        store=Store(self.app.home)
        try:
            opened=next((r for r in intervals(store) if r['run']==self.run and r['state']=='open'),None)
            if not opened:raise ValueError('この実行に未終了の計測はありません。')
            self.app.attention_recorder.close(store,self.run,opened['interval'],abandon)
        except Exception as error:messagebox.showerror('計測を終了できません',str(error),parent=self.window)
        finally:store.close()
        self.refresh()
    def save(self):
        path=filedialog.asksaveasfilename(parent=self.window,defaultextension='.json',filetypes=[('作業履歴','*.json')])
        if path:
            try:Path(path).write_text(json.dumps(self.body,ensure_ascii=False,indent=2)+'\n')
            except Exception as error:messagebox.showerror('保存できません',str(error),parent=self.window)
